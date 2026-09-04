"""Índice vectorial sobre LanceDB (decisión D-5 del plan).

Los vectores de los chunks van en un archivo LanceDB al lado de la base SQLite
(`data/vectors/`). Sin Docker, sin servicio: un backup es copiar la carpeta.

La tabla tiene una fila por chunk: `chunk_id` (la PK de `chunks` en SQLite),
`modelo` (qué `EmbeddingModel` produjo el vector, D-7) y `vector`
(`fixed_size_list<float32>` de la dimensión del modelo).

**Reanudable** (criterio de PR-13): `upsert` usa `merge_insert` sobre
`chunk_id`, así que volver a correr una indexación cortada no duplica ni pisa mal
nada. Qué chunks rehacer lo decide `Repo.chunks_pendientes_de_embedding` (PR-12)
en SQLite; este índice solo tiene que ser idempotente.

`lancedb` se importa perezoso. Es dependencia del proyecto, pero si por lo que
sea falta, revienta con un mensaje claro (D-05), no finge indexar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_TABLA = "chunks"
_FALTA_LANCEDB = (
    "lancedb no está instalado. Es dependencia del proyecto: "
    'corré `pip install -e ".[dev]"` en el venv del repo.'
)


@dataclass(frozen=True, slots=True)
class Vecino:
    """Un resultado de búsqueda. `distancia` es coseno: 0 = misma dirección,
    1 = ortogonal, 2 = opuesta."""

    chunk_id: int
    distancia: float


class IndiceVectorial:
    """Envuelve una tabla LanceDB. Perezoso: no abre nada hasta que se usa."""

    def __init__(
        self, ruta: Path | str, *, dimension: int | None = None, tabla: str = _TABLA
    ) -> None:
        self.ruta = Path(ruta)
        self.tabla = tabla
        self._dimension = int(dimension) if dimension is not None else None
        self._db = None
        self._t = None

    # -- plumbing ---------------------------------------------------- #

    @staticmethod
    def _modulos():
        try:
            import lancedb
            import pyarrow as pa
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(_FALTA_LANCEDB) from e
        return lancedb, pa

    def _conexion(self):
        if self._db is None:
            lancedb, _ = self._modulos()
            self.ruta.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.ruta)
        return self._db

    @staticmethod
    def _nombres_de_tabla(db) -> list[str]:
        """`db.list_tables()` devuelve una lista plana en versiones viejas y un
        objeto con `.tables` en las nuevas; se cubren las dos."""
        res = db.list_tables()
        return list(res.tables) if hasattr(res, "tables") else list(res)

    def _schema(self):
        if self._dimension is None:
            raise ValueError(
                "no sé la dimensión del índice: pasala al construir "
                "`IndiceVectorial(..., dimension=N)` o abrí una tabla ya creada"
            )
        _, pa = self._modulos()
        return pa.schema(
            [
                pa.field("chunk_id", pa.int64()),
                pa.field("modelo", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._dimension)),
            ]
        )

    def _tabla_abierta(self, *, crear: bool):
        if self._t is not None:
            return self._t
        db = self._conexion()
        if self.tabla in self._nombres_de_tabla(db):
            self._t = db.open_table(self.tabla)
            dim = self._t.schema.field("vector").type.list_size
            if self._dimension is None:
                self._dimension = dim
            elif self._dimension != dim:
                raise ValueError(
                    f"la tabla {self.tabla!r} tiene dimensión {dim}, "
                    f"no {self._dimension}"
                )
        elif crear:
            self._t = db.create_table(self.tabla, schema=self._schema())
        return self._t

    # -- API ------------------------------------------------------------ #

    @property
    def dimension(self) -> int | None:
        """La dimensión del índice: la que se pasó al construir, o la de la
        tabla si ya existe, o `None` si no hay ni una ni otra."""
        if self._dimension is None:
            self._tabla_abierta(crear=False)
        return self._dimension

    def upsert(self, filas: Iterable[tuple[int, Sequence[float], str]]) -> int:
        """Inserta o reemplaza por `chunk_id`. Cada fila es
        `(chunk_id, vector, modelo)`. Idempotente: correrlo dos veces deja lo
        mismo. Devuelve cuántas filas escribió."""
        # dedup por chunk_id conservando el último: LanceDB rechaza un
        # merge_insert con claves repetidas en la entrada, y "el último gana" es
        # lo que espera un reintento (misma cadena reprocesada).
        por_id: dict[int, dict] = {}
        for chunk_id, vector, modelo in filas:
            vec = [float(x) for x in vector]
            if self._dimension is not None and len(vec) != self._dimension:
                raise ValueError(
                    f"chunk {chunk_id}: vector de {len(vec)} componentes, "
                    f"el índice es de {self._dimension}"
                )
            por_id[int(chunk_id)] = {
                "chunk_id": int(chunk_id),
                "modelo": str(modelo),
                "vector": vec,
            }
        datos = list(por_id.values())
        if not datos:
            return 0
        if self._dimension is None:
            self._dimension = len(datos[0]["vector"])
        tabla = self._tabla_abierta(crear=True)
        (
            tabla.merge_insert("chunk_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(datos)
        )
        return len(datos)

    def buscar(self, vector: Sequence[float], *, k: int = 10) -> list[Vecino]:
        """Los `k` chunks más cercanos por coseno. Lista vacía si el índice no
        existe todavía o está vacío."""
        tabla = self._tabla_abierta(crear=False)
        if tabla is None or tabla.count_rows() == 0:
            return []
        filas = (
            tabla.search([float(x) for x in vector]).metric("cosine").limit(k).to_list()
        )
        return [Vecino(int(f["chunk_id"]), float(f["_distance"])) for f in filas]

    def contar(self) -> int:
        tabla = self._tabla_abierta(crear=False)
        return int(tabla.count_rows()) if tabla is not None else 0

    def ids(self) -> set[int]:
        """Los `chunk_id` que ya están en el índice (para saber qué falta)."""
        tabla = self._tabla_abierta(crear=False)
        if tabla is None:
            return set()
        return {int(x) for x in tabla.to_arrow().column("chunk_id").to_pylist()}

    def modelos(self) -> dict[str, int]:
        """Cuántas filas hay por modelo. Si hay más de uno, algo quedó a medio
        reindexar."""
        tabla = self._tabla_abierta(crear=False)
        if tabla is None:
            return {}
        cuenta: dict[str, int] = {}
        for m in tabla.to_arrow().column("modelo").to_pylist():
            cuenta[m] = cuenta.get(m, 0) + 1
        return cuenta

    def vaciar(self) -> None:
        """Borra la tabla entera. Para rehacer el índice desde cero cuando
        cambió el modelo y no querés mezclar dimensiones/versiones."""
        db = self._conexion()
        if self.tabla in self._nombres_de_tabla(db):
            db.drop_table(self.tabla)
        self._t = None
