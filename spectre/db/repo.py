"""Única puerta al almacenamiento de Spectre.

Regla de `CLAUDE.md` / D-12: todo acceso a SQLite pasa por acá. Este módulo
provee la conexión configurada, el runner de migraciones versionadas y las
operaciones de tomo / página / fallo. El estado vive en la base, nunca en JSON
escrito a mano (defecto D-04).

Migraciones: archivos `NNNN_nombre.sql` en `migrations/`, aplicados en orden de
nombre y anotados en la tabla `_migraciones`. `migrate()` es idempotente: lo ya
registrado no se vuelve a correr. El plan §4 nombra un `db/schema.sql`; se lo
realiza como `migrations/0001_initial.sql` para no tener dos fuentes del esquema
que se desincronicen (el mismo PR pide "migraciones versionadas").
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_TOMO_COLS = (
    "numero, volumen, anio, csjn_tomo_id, pdf_path, sha256, calidad, paginas, "
    "offset_pagina, estado, indexado_at"
)
_TOMO_PLACEHOLDERS = ", ".join(["?"] * 11)
_TOMO_CAMPOS_MUTABLES = frozenset(
    {
        "volumen",
        "anio",
        "csjn_tomo_id",
        "pdf_path",
        "sha256",
        "calidad",
        "paginas",
        "offset_pagina",
        "estado",
        "indexado_at",
    }
)
#: Columnas de `fallos` que `actualizar_fallo` puede tocar. `caratula`, `cita`
#: y el rango de página los pone `insert_fallo` (son la identidad del fallo,
#: los fija el segmentador); esto es lo que llena PR-19 al estructurar (fecha
#: / jueces / tribunal / recurso).
_FALLO_CAMPOS_MUTABLES = frozenset(
    {"fecha", "tribunal_origen", "tipo_recurso", "jueces"}
)


def ahora_iso() -> str:
    """Timestamp ISO 8601 en UTC con resolución de segundos: el formato que
    guardan las columnas `*_at` de la base."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Conexión y migraciones
# --------------------------------------------------------------------------- #


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Abre la base con las PRAGMAs del proyecto y `row_factory` de filas por
    nombre. Crea la carpeta contenedora si falta (nunca contra el CWD: el
    llamador pasa una ruta ya anclada por `config`)."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migraciones_disponibles() -> list[Path]:
    """Los `.sql` de `migrations/`, ordenados por nombre (0001, 0002, ...)."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _versiones_aplicadas(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migraciones ("
        " version TEXT PRIMARY KEY,"
        " aplicada_at TEXT NOT NULL)"
    )
    return {row["version"] for row in conn.execute("SELECT version FROM _migraciones")}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Aplica las migraciones pendientes, una transacción por archivo.

    Devuelve las versiones aplicadas en esta llamada (lista vacía si no había
    nada pendiente). Idempotente: llamarla dos veces seguidas no hace nada la
    segunda vez y no es un error.
    """
    aplicadas = _versiones_aplicadas(conn)
    nuevas: list[str] = []
    for path in migraciones_disponibles():
        version = path.stem
        if version in aplicadas:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            # `BEGIN` explícito para que el DDL del archivo y el registro en
            # `_migraciones` caigan o se apliquen juntos. El DDL de SQLite es
            # transaccional, así que un fallo a mitad no deja el esquema a medias.
            conn.executescript("BEGIN;\n" + sql)
            conn.execute(
                "INSERT INTO _migraciones (version, aplicada_at) VALUES (?, ?)",
                (version, ahora_iso()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        nuevas.append(version)
    return nuevas


# --------------------------------------------------------------------------- #
# Filas tipadas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Tomo:
    id: int
    numero: int
    volumen: str | None
    anio: int | None
    csjn_tomo_id: str | None
    pdf_path: str | None
    sha256: str | None
    calidad: str
    paginas: int | None
    offset_pagina: int | None
    estado: str
    indexado_at: str | None


@dataclass(frozen=True, slots=True)
class Pagina:
    id: int
    tomo_id: int
    pdf_page: int
    pagina_oficial: int | None
    texto_crudo: str | None
    texto_limpio: str | None


@dataclass(frozen=True, slots=True)
class Fallo:
    id: int
    tomo_id: int
    caratula: str
    cita: str | None
    pagina_inicio: int | None
    pagina_fin: int | None
    fecha: str | None
    tribunal_origen: str | None
    tipo_recurso: str | None
    jueces: str | None


@dataclass(frozen=True, slots=True)
class Seccion:
    id: int
    fallo_id: int
    tipo: str
    autor: str | None
    orden: int
    texto: str | None


@dataclass(frozen=True, slots=True)
class Chunk:
    """Una fila de `chunks`. `modelo_embedding` / `embedding_at` en `None` = el
    chunk todavía no se embebió (o se embebió con otro modelo y hay que
    rehacerlo)."""

    id: int
    fallo_id: int
    seccion_id: int | None
    orden: int
    texto: str
    pagina_oficial: int | None
    modelo_embedding: str | None
    embedding_at: str | None


@dataclass(frozen=True, slots=True)
class Cita:
    """Una fila de `citas`: una referencia `Fallos: <tomo_citado>:<pagina_citada>`
    hallada en el texto del fallo `fallo_id`. Una cadena con un solo prefijo
    (`Fallos: 301:1149; 302:1078`) da una fila por precedente. La llena la etapa
    `estructurar` del pipeline (PR-C1), con `extraer_citas` (PR-10)."""

    id: int
    fallo_id: int
    tomo_citado: int | None
    pagina_citada: int | None
    contexto: str | None


@dataclass(frozen=True, slots=True)
class CitaEntrante:
    """Un fallo del corpus indexado que cita al fallo consultado. `cita` y
    `caratula` son del fallo *citante*; `pagina_citada` es la página que
    escribió (dentro del rango del fallo consultado); `contexto` es el recorte
    alrededor de la cita en el texto del citante."""

    cita: str | None
    caratula: str
    pagina_citada: int | None
    contexto: str | None


@dataclass(frozen=True, slots=True)
class SumarioGuardado:
    """Una fila de `sumarios`: un sumario oficial de la CSJN ya persistido
    (PR-C2b). `voces` es la tupla de descriptores de ESE sumario (se guarda
    como JSON en la columna, igual que `fallos.jueces`); `materia` es
    `analisisDocumental.materiaSecretaria`. Distinto de
    `corpus.csjn.sumarios.Sumario` (el que baja del sitio): `db/` no importa
    `corpus/`."""

    id: int
    fallo_id: int
    orden: int
    texto: str
    voces: tuple[str, ...]
    materia: str | None
    id_documento: str | None
    sincronizado_at: str


def _sumario(row: sqlite3.Row | None) -> SumarioGuardado | None:
    if row is None:
        return None
    crudo = row["voces"]
    voces = tuple(json.loads(crudo)) if crudo else ()
    return SumarioGuardado(
        id=row["id"],
        fallo_id=row["fallo_id"],
        orden=row["orden"],
        texto=row["texto"],
        voces=voces,
        materia=row["materia"],
        id_documento=row["id_documento"],
        sincronizado_at=row["sincronizado_at"],
    )


def _tomo(row: sqlite3.Row | None) -> Tomo | None:
    return Tomo(**row) if row is not None else None


def _pagina(row: sqlite3.Row | None) -> Pagina | None:
    return Pagina(**row) if row is not None else None


def _fallo(row: sqlite3.Row | None) -> Fallo | None:
    return Fallo(**row) if row is not None else None


def _seccion(row: sqlite3.Row | None) -> Seccion | None:
    return Seccion(**row) if row is not None else None


def _chunk(row: sqlite3.Row | None) -> Chunk | None:
    return Chunk(**row) if row is not None else None


# --------------------------------------------------------------------------- #
# Repositorio
# --------------------------------------------------------------------------- #


class Repo:
    """Operaciones de datos sobre una conexión ya migrada.

    Por default cada escritura hace `commit()` por su cuenta: es el modo
    cómodo para el CLI y la mayoría de los tests. **Dentro de un handler del
    job runner (PR-19) esto está prohibido** (`jobs/runner.py`: "el handler
    ... no llama commit()/rollback(); el Runner es dueño del límite
    transaccional"): un `Repo` que commitea ahí rompe la garantía de "sin
    duplicar" de D-3, porque el `with self.conn:` del runner ya no puede hacer
    rollback de lo que un commit de acá adentro volvió permanente. Por eso
    `auto_commit=False` deja cada escritura pendiente — el runner es quien
    cierra la transacción entera al final del job."""

    def __init__(self, conn: sqlite3.Connection, *, auto_commit: bool = True) -> None:
        self.conn = conn
        self.auto_commit = auto_commit

    def _commit(self) -> None:
        if self.auto_commit:
            self.conn.commit()

    # -- tomos ------------------------------------------------------------ #

    def insert_tomo(
        self,
        numero: int,
        *,
        volumen: str | None = None,
        anio: int | None = None,
        csjn_tomo_id: str | None = None,
        pdf_path: str | None = None,
        sha256: str | None = None,
        calidad: str = "desconocida",
        paginas: int | None = None,
        offset_pagina: int | None = None,
        estado: str = "registrado",
        indexado_at: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            f"INSERT INTO tomos ({_TOMO_COLS}) VALUES ({_TOMO_PLACEHOLDERS})",
            (
                numero,
                volumen,
                anio,
                csjn_tomo_id,
                pdf_path,
                sha256,
                calidad,
                paginas,
                offset_pagina,
                estado,
                indexado_at,
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def get_tomo(self, tomo_id: int) -> Tomo | None:
        return _tomo(
            self.conn.execute("SELECT * FROM tomos WHERE id = ?", (tomo_id,)).fetchone()
        )

    def get_tomo_por_numero(self, numero: int) -> Tomo | None:
        return _tomo(
            self.conn.execute(
                "SELECT * FROM tomos WHERE numero = ?", (numero,)
            ).fetchone()
        )

    def list_tomos(self) -> list[Tomo]:
        return [
            Tomo(**row)
            for row in self.conn.execute("SELECT * FROM tomos ORDER BY numero")
        ]

    def actualizar_tomo(self, tomo_id: int, **campos: object) -> None:
        """Actualiza columnas sueltas del tomo. `numero` es inmutable (es la
        identidad del tomo); intentar tocarlo o pasar una columna inexistente
        es un `ValueError`, no un no-op silencioso."""
        if not campos:
            return
        desconocidos = set(campos) - _TOMO_CAMPOS_MUTABLES
        if desconocidos:
            raise ValueError(f"columnas no actualizables: {sorted(desconocidos)}")
        asignaciones = ", ".join(f"{col} = ?" for col in campos)
        self.conn.execute(
            f"UPDATE tomos SET {asignaciones} WHERE id = ?",
            (*campos.values(), tomo_id),
        )
        self._commit()

    # -- páginas -------------------------------------------------------- #

    def insert_pagina(
        self,
        tomo_id: int,
        pdf_page: int,
        *,
        pagina_oficial: int | None = None,
        texto_crudo: str | None = None,
        texto_limpio: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO paginas (tomo_id, pdf_page, pagina_oficial, texto_crudo,"
            " texto_limpio) VALUES (?, ?, ?, ?, ?)",
            (tomo_id, pdf_page, pagina_oficial, texto_crudo, texto_limpio),
        )
        self._commit()
        return int(cur.lastrowid)

    def insert_paginas(
        self,
        tomo_id: int,
        filas: Iterable[tuple[int, int | None, str | None]],
    ) -> int:
        """Inserta páginas en lote. Cada fila es
        `(pdf_page, pagina_oficial, texto_crudo)`; `texto_limpio` lo completa
        PR-05. Devuelve cuántas insertó."""
        datos = [
            (tomo_id, pdf_page, pagina_oficial, texto_crudo)
            for pdf_page, pagina_oficial, texto_crudo in filas
        ]
        self.conn.executemany(
            "INSERT INTO paginas (tomo_id, pdf_page, pagina_oficial, texto_crudo) "
            "VALUES (?, ?, ?, ?)",
            datos,
        )
        self._commit()
        return len(datos)

    def borrar_paginas(self, tomo_id: int) -> int:
        """Borra todas las páginas del tomo. Devuelve cuántas borró."""
        cur = self.conn.execute("DELETE FROM paginas WHERE tomo_id = ?", (tomo_id,))
        self._commit()
        return cur.rowcount

    def set_texto_limpio(self, filas: Iterable[tuple[int, str]]) -> int:
        """Actualiza `texto_limpio` en lote. Cada fila es `(pagina_id, texto)`.
        Devuelve cuántas filas tocó."""
        datos = [(texto, pagina_id) for pagina_id, texto in filas]
        self.conn.executemany("UPDATE paginas SET texto_limpio = ? WHERE id = ?", datos)
        self._commit()
        return len(datos)

    def get_pagina(self, tomo_id: int, pdf_page: int) -> Pagina | None:
        return _pagina(
            self.conn.execute(
                "SELECT * FROM paginas WHERE tomo_id = ? AND pdf_page = ?",
                (tomo_id, pdf_page),
            ).fetchone()
        )

    def list_paginas(self, tomo_id: int) -> list[Pagina]:
        return [
            Pagina(**row)
            for row in self.conn.execute(
                "SELECT * FROM paginas WHERE tomo_id = ? ORDER BY pdf_page",
                (tomo_id,),
            )
        ]

    def contar_paginas(self, tomo_id: int) -> int:
        return int(
            self.conn.execute(
                "SELECT count(*) FROM paginas WHERE tomo_id = ?", (tomo_id,)
            ).fetchone()[0]
        )

    # -- fallos ------------------------------------------------------------ #

    def insert_fallo(
        self,
        tomo_id: int,
        caratula: str,
        *,
        cita: str | None = None,
        pagina_inicio: int | None = None,
        pagina_fin: int | None = None,
        fecha: str | None = None,
        tribunal_origen: str | None = None,
        tipo_recurso: str | None = None,
        jueces: str | None = None,
    ) -> int:
        """`jueces` se guarda tal cual (se espera JSON en TEXT). Cómo se
        serializa la lista de jueces lo decide PR-08; el repo no lo interpreta."""
        cur = self.conn.execute(
            "INSERT INTO fallos (tomo_id, caratula, cita, pagina_inicio, pagina_fin,"
            " fecha, tribunal_origen, tipo_recurso, jueces)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tomo_id,
                caratula,
                cita,
                pagina_inicio,
                pagina_fin,
                fecha,
                tribunal_origen,
                tipo_recurso,
                jueces,
            ),
        )
        self._commit()
        return int(cur.lastrowid)

    def get_fallo(self, fallo_id: int) -> Fallo | None:
        return _fallo(
            self.conn.execute(
                "SELECT * FROM fallos WHERE id = ?", (fallo_id,)
            ).fetchone()
        )

    def get_fallo_por_cita(self, cita: str) -> Fallo | None:
        return _fallo(
            self.conn.execute("SELECT * FROM fallos WHERE cita = ?", (cita,)).fetchone()
        )

    def list_fallos(self, tomo_id: int) -> list[Fallo]:
        return [
            Fallo(**row)
            for row in self.conn.execute(
                "SELECT * FROM fallos WHERE tomo_id = ? ORDER BY pagina_inicio, id",
                (tomo_id,),
            )
        ]

    def actualizar_fallo(self, fallo_id: int, **campos: object) -> None:
        """Actualiza los metadatos estructurados de un fallo (PR-19: la etapa
        `estructurar`). Columna inexistente o no mutable → `ValueError`, igual
        que `actualizar_tomo`."""
        if not campos:
            return
        desconocidos = set(campos) - _FALLO_CAMPOS_MUTABLES
        if desconocidos:
            raise ValueError(f"columnas no actualizables: {sorted(desconocidos)}")
        asignaciones = ", ".join(f"{col} = ?" for col in campos)
        self.conn.execute(
            f"UPDATE fallos SET {asignaciones} WHERE id = ?",
            (*campos.values(), fallo_id),
        )
        self._commit()

    def borrar_fallos(self, tomo_id: int) -> int:
        """Borra todos los fallos del tomo (y en cascada sus secciones, chunks
        y citas — las FK del esquema). Reprocesar la segmentación de un tomo
        (reintento del job, PR-19) no acumula fallos duplicados. Devuelve
        cuántos borró."""
        cur = self.conn.execute("DELETE FROM fallos WHERE tomo_id = ?", (tomo_id,))
        self._commit()
        return cur.rowcount

    # -- secciones ------------------------------------------------------ #

    def insert_secciones(
        self,
        fallo_id: int,
        filas: Iterable[tuple[str, str | None, int, str]],
    ) -> list[int]:
        """Inserta las secciones de un fallo en orden. Cada fila es `(tipo,
        autor, orden, texto)`. Devuelve los `id` asignados, en el mismo orden
        que `filas` — el llamador (PR-19, etapa `fragmentar`) los necesita
        para mapear `Chunk.seccion_orden` (el índice 0-based que da
        `sections.partir_secciones`) al `seccion_id` real de la base antes de
        `insert_chunks`. `executemany` no da `lastrowid` por fila, así que va
        una inserción por vez."""
        ids = []
        for tipo, autor, orden, texto in filas:
            cur = self.conn.execute(
                "INSERT INTO secciones (fallo_id, tipo, autor, orden, texto)"
                " VALUES (?, ?, ?, ?, ?)",
                (fallo_id, tipo, autor, orden, texto),
            )
            ids.append(int(cur.lastrowid))
        self._commit()
        return ids

    def get_seccion(self, seccion_id: int) -> Seccion | None:
        return _seccion(
            self.conn.execute(
                "SELECT * FROM secciones WHERE id = ?", (seccion_id,)
            ).fetchone()
        )

    def list_secciones_de_fallo(self, fallo_id: int) -> list[Seccion]:
        return [
            Seccion(**row)
            for row in self.conn.execute(
                "SELECT * FROM secciones WHERE fallo_id = ? ORDER BY orden",
                (fallo_id,),
            )
        ]

    def borrar_secciones_de_fallo(self, fallo_id: int) -> int:
        """Borra las secciones de un fallo (y en cascada sus chunks). Mismo
        propósito que `borrar_fallos`: reintentar la etapa `fragmentar` no
        acumula secciones ni chunks duplicados."""
        cur = self.conn.execute("DELETE FROM secciones WHERE fallo_id = ?", (fallo_id,))
        self._commit()
        return cur.rowcount

    # -- chunks -------------------------------------------------------- #

    def insert_chunks(
        self,
        fallo_id: int,
        filas: Iterable[tuple[int | None, int, str, int | None]],
    ) -> int:
        """Inserta chunks de un fallo en lote. Cada fila es
        `(seccion_id, orden, texto, pagina_oficial)`. `modelo_embedding` y
        `embedding_at` arrancan en NULL: los pone el embebido (PR-12+), no la
        inserción. Devuelve cuántos insertó."""
        datos = [
            (fallo_id, seccion_id, orden, texto, pagina_oficial)
            for seccion_id, orden, texto, pagina_oficial in filas
        ]
        self.conn.executemany(
            "INSERT INTO chunks (fallo_id, seccion_id, orden, texto, pagina_oficial)"
            " VALUES (?, ?, ?, ?, ?)",
            datos,
        )
        self._commit()
        return len(datos)

    def get_chunk(self, chunk_id: int) -> Chunk | None:
        return _chunk(
            self.conn.execute(
                "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
        )

    def list_chunks_de_fallo(self, fallo_id: int) -> list[Chunk]:
        return [
            Chunk(**row)
            for row in self.conn.execute(
                "SELECT * FROM chunks WHERE fallo_id = ?"
                " ORDER BY seccion_id, orden, id",
                (fallo_id,),
            )
        ]

    def list_chunks_de_tomo(self, tomo_id: int) -> list[Chunk]:
        """Los chunks de todos los fallos de un tomo (join por `fallo_id`).
        Lo usa PR-19 para acotar la etapa `embeber` a un solo tomo —
        `chunks_pendientes_de_embedding` de abajo mira la base entera."""
        return [
            Chunk(**row)
            for row in self.conn.execute(
                "SELECT c.* FROM chunks c JOIN fallos f ON f.id = c.fallo_id"
                " WHERE f.tomo_id = ? ORDER BY c.fallo_id, c.seccion_id, c.orden",
                (tomo_id,),
            )
        ]

    def chunks_pendientes_de_embedding(
        self, modelo: str, *, limite: int | None = None
    ) -> list[Chunk]:
        """Los chunks que todavía **no** tienen embedding con `modelo`: los que
        nunca se embebieron (`modelo_embedding IS NULL`) y los que se embebieron
        con otro modelo. Esta es la consulta que hace barato cambiar de modelo
        (D-7/D-8): reindexar es rehacer estos, sin tocar un solo PDF."""
        sql = (
            "SELECT * FROM chunks"
            " WHERE modelo_embedding IS NULL OR modelo_embedding <> ?"
            " ORDER BY id"
        )
        params: tuple[object, ...] = (modelo,)
        if limite is not None:
            sql += " LIMIT ?"
            params += (limite,)
        return [Chunk(**row) for row in self.conn.execute(sql, params)]

    def filtrar_chunks(
        self,
        ids: Iterable[int],
        *,
        anio_desde: int | None = None,
        anio_hasta: int | None = None,
        tribunal_origen: str | None = None,
        tipo_seccion: str | None = None,
        voz: str | None = None,
        materia: str | None = None,
    ) -> set[int]:
        """De `ids`, cuáles cumplen los filtros pedidos (rango de años de
        `fallos.fecha`, tribunal de origen exacto, tipo de sección exacto, voz
        del tesauro de la CSJN, materia de la Secretaría).
        `anio_desde`/`anio_hasta` son inclusivos y se pueden usar sueltos (solo
        piso o solo techo); un fallo sin fecha no pasa ningún filtro de año.
        `voz` / `materia` solo dejan pasar fallos con un sumario oficial cargado
        (PR-C2b) que traiga esa voz / esa materia — la comparación de `voz` es
        en mayúsculas (así las guarda la CSJN). Sin filtros, es simplemente
        `set(ids)` — para búsqueda híbrida (PR-15), que filtra *después* de
        traer candidatos de cada índice: ni LanceDB ni FTS5 saben de estos
        metadatos, viven en `fallos`/`secciones`/`sumarios`.
        """
        ids = list(ids)
        if not ids:
            return set()
        condiciones = []
        params: list[object] = []
        if anio_desde is not None:
            condiciones.append("substr(f.fecha, 1, 4) >= ?")
            params.append(f"{anio_desde:04d}")
        if anio_hasta is not None:
            condiciones.append("substr(f.fecha, 1, 4) <= ?")
            params.append(f"{anio_hasta:04d}")
        if tribunal_origen is not None:
            condiciones.append("f.tribunal_origen = ?")
            params.append(tribunal_origen)
        if tipo_seccion is not None:
            condiciones.append("s.tipo = ?")
            params.append(tipo_seccion)
        if voz is not None:
            condiciones.append(
                "c.fallo_id IN (SELECT fv.fallo_id FROM fallo_voces fv"
                " JOIN voces v ON v.id = fv.voz_id WHERE v.valor = ?)"
            )
            params.append(voz.strip().upper())
        if materia is not None:
            condiciones.append(
                "c.fallo_id IN (SELECT fallo_id FROM sumarios WHERE materia = ?)"
            )
            params.append(materia)
        where = (" AND " + " AND ".join(condiciones)) if condiciones else ""
        marcadores = ", ".join("?" * len(ids))
        sql = (
            "SELECT c.id FROM chunks c"
            " JOIN fallos f ON f.id = c.fallo_id"
            " LEFT JOIN secciones s ON s.id = c.seccion_id"
            f" WHERE c.id IN ({marcadores}){where}"
        )
        filas = self.conn.execute(sql, (*ids, *params))
        return {int(row[0]) for row in filas}

    def contar_chunks(self) -> int:
        return int(self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0])

    def contar_chunks_pendientes(self, modelo: str) -> int:
        return int(
            self.conn.execute(
                "SELECT count(*) FROM chunks"
                " WHERE modelo_embedding IS NULL OR modelo_embedding <> ?",
                (modelo,),
            ).fetchone()[0]
        )

    def marcar_chunks_embebidos(self, ids: Iterable[int], modelo: str) -> int:
        """Registra que estos chunks quedaron embebidos con `modelo`, ahora.
        Devuelve cuántas filas tocó."""
        cuando = ahora_iso()
        datos = [(modelo, cuando, chunk_id) for chunk_id in ids]
        self.conn.executemany(
            "UPDATE chunks SET modelo_embedding = ?, embedding_at = ? WHERE id = ?",
            datos,
        )
        self._commit()
        return len(datos)

    # -- citas -------------------------------------------------------- #

    def insert_citas(
        self,
        fallo_id: int,
        filas: Iterable[tuple[int | None, int | None, str | None]],
    ) -> int:
        """Inserta en lote las citas salientes de un fallo. Cada fila es
        `(tomo_citado, pagina_citada, contexto)` — lo que da `extraer_citas`
        (PR-10), un precedente por fila. La llena la etapa `estructurar` del
        pipeline (PR-C1). Devuelve cuántas insertó."""
        datos = [(fallo_id, t, p, c) for t, p, c in filas]
        self.conn.executemany(
            "INSERT INTO citas (fallo_id, tomo_citado, pagina_citada, contexto)"
            " VALUES (?, ?, ?, ?)",
            datos,
        )
        self._commit()
        return len(datos)

    def borrar_citas_de_fallo(self, fallo_id: int) -> int:
        """Borra las citas salientes de un fallo. Reintentar la etapa
        `estructurar` (PR-19/PR-C1) no acumula citas duplicadas. Devuelve
        cuántas borró."""
        cur = self.conn.execute("DELETE FROM citas WHERE fallo_id = ?", (fallo_id,))
        self._commit()
        return cur.rowcount

    def list_citas_de_fallo(self, fallo_id: int) -> list[Cita]:
        """Las citas salientes de un fallo, en orden de aparición (por `id`)."""
        return [
            Cita(**row)
            for row in self.conn.execute(
                "SELECT * FROM citas WHERE fallo_id = ? ORDER BY id", (fallo_id,)
            )
        ]

    def contar_citas_de_tomo(self, tomo_id: int) -> int:
        """Cuántas filas de `citas` cuelgan de los fallos de este tomo. Es el
        número del criterio de aceptación de PR-C1 (medido sobre el Tomo 348)."""
        return int(
            self.conn.execute(
                "SELECT count(*) FROM citas c JOIN fallos f ON f.id = c.fallo_id"
                " WHERE f.tomo_id = ?",
                (tomo_id,),
            ).fetchone()[0]
        )

    def citas_entrantes(self, fallo_id: int) -> list[CitaEntrante]:
        """Qué fallos del corpus indexado citan a `fallo_id`. Cruza
        `citas.tomo_citado` con el *número* del tomo del fallo consultado y
        `citas.pagina_citada` con su rango de páginas (`Fallos: N:P` apunta a la
        página de inicio de un fallo, pero se acepta cualquier página dentro del
        rango: una cita puede señalar un considerando del medio). Excluye la
        auto-cita (un fallo que se cita a sí mismo). Vacío si el fallo no tiene
        página de inicio o no está asociado a un tomo."""
        fallo = self.get_fallo(fallo_id)
        if fallo is None or fallo.pagina_inicio is None:
            return []
        tomo = self.get_tomo(fallo.tomo_id)
        if tomo is None:
            return []
        pagina_fin = (
            fallo.pagina_fin if fallo.pagina_fin is not None else fallo.pagina_inicio
        )
        return [
            CitaEntrante(
                cita=row["cita"],
                caratula=row["caratula"],
                pagina_citada=row["pagina_citada"],
                contexto=row["contexto"],
            )
            for row in self.conn.execute(
                "SELECT f.cita AS cita, f.caratula AS caratula,"
                "       c.pagina_citada AS pagina_citada, c.contexto AS contexto"
                " FROM citas c JOIN fallos f ON f.id = c.fallo_id"
                " WHERE c.tomo_citado = ? AND c.pagina_citada BETWEEN ? AND ?"
                "   AND f.id <> ?"
                " ORDER BY f.cita",
                (tomo.numero, fallo.pagina_inicio, pagina_fin, fallo_id),
            )
        ]

    # -- sumarios / voces (PR-C2b) ------------------------------------- #

    def _upsert_voz(self, valor: str, codigo: int | None = None) -> int:
        valor = valor.strip()
        self.conn.execute(
            "INSERT INTO voces (valor, codigo) VALUES (?, ?) ON CONFLICT (valor)"
            " DO UPDATE SET codigo = COALESCE(codigo, excluded.codigo)",
            (valor, codigo),
        )
        fila = self.conn.execute(
            "SELECT id FROM voces WHERE valor = ?", (valor,)
        ).fetchone()
        return int(fila[0])

    def upsert_voz(self, valor: str, codigo: int | None = None) -> int:
        """Registra una voz del tesauro de la CSJN (o devuelve la que ya
        estaba). `valor` es único (se guarda tal cual lo da la Corte, en
        mayúsculas); si ya existía y ahora llega con `codigo`, se completa sin
        pisar uno previo. Devuelve el `id` de `voces`."""
        voz_id = self._upsert_voz(valor, codigo)
        self._commit()
        return voz_id

    def reemplazar_sumarios_de_fallo(
        self,
        fallo_id: int,
        filas: Iterable[tuple[int, str, Iterable[str], str | None, str | None]],
    ) -> int:
        """Deja los sumarios de un fallo exactamente como `filas` (PR-C2b, el
        sync). Cada fila es `(orden, texto, voces, materia, id_documento)`.
        Borra primero los sumarios y los `fallo_voces` del fallo, así un
        segundo sync no acumula (mismo criterio que `borrar_citas_de_fallo`).
        Registra cada voz en `voces` y arma `fallo_voces`. Devuelve cuántos
        sumarios insertó."""
        cuando = ahora_iso()
        self.conn.execute("DELETE FROM sumarios WHERE fallo_id = ?", (fallo_id,))
        self.conn.execute("DELETE FROM fallo_voces WHERE fallo_id = ?", (fallo_id,))
        n = 0
        for orden, texto, voces, materia, id_documento in filas:
            voces = [v.strip() for v in voces if v and v.strip()]
            self.conn.execute(
                "INSERT INTO sumarios (fallo_id, orden, texto, voces, materia,"
                " id_documento, sincronizado_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fallo_id,
                    orden,
                    texto,
                    json.dumps(voces, ensure_ascii=False) if voces else None,
                    materia,
                    id_documento,
                    cuando,
                ),
            )
            for v in voces:
                voz_id = self._upsert_voz(v)
                self.conn.execute(
                    "INSERT OR IGNORE INTO fallo_voces (fallo_id, voz_id)"
                    " VALUES (?, ?)",
                    (fallo_id, voz_id),
                )
            n += 1
        self._commit()
        return n

    def list_sumarios_de_fallo(self, fallo_id: int) -> list[SumarioGuardado]:
        return [
            _sumario(row)
            for row in self.conn.execute(
                "SELECT * FROM sumarios WHERE fallo_id = ? ORDER BY orden",
                (fallo_id,),
            )
        ]

    def sumarios_por_fallos(
        self, fallo_ids: Iterable[int]
    ) -> dict[int, list[SumarioGuardado]]:
        """Los sumarios de varios fallos de una, para los resultados de
        `/api/buscar`. `fallo_id` sin sumarios no aparece en el dict."""
        ids = list(fallo_ids)
        if not ids:
            return {}
        marcadores = ", ".join("?" * len(ids))
        salida: dict[int, list[SumarioGuardado]] = {}
        for row in self.conn.execute(
            f"SELECT * FROM sumarios WHERE fallo_id IN ({marcadores})"
            " ORDER BY fallo_id, orden",
            ids,
        ):
            salida.setdefault(row["fallo_id"], []).append(_sumario(row))
        return salida

    def buscar_voces_locales(
        self, termino: str, *, limite: int = 20
    ) -> list[tuple[str, int | None]]:
        """Las voces del corpus (tabla `voces`) que contienen `termino`, para
        el autocompletado del filtro. Contra lo local, no contra el tesauro
        vivo de la CSJN: solo tiene sentido ofrecer voces que algún fallo
        indexado trae."""
        patron = f"%{termino.strip().upper()}%"
        return [
            (row["valor"], row["codigo"])
            for row in self.conn.execute(
                "SELECT valor, codigo FROM voces WHERE valor LIKE ?"
                " ORDER BY valor LIMIT ?",
                (patron, limite),
            )
        ]

    def materias_del_corpus(self) -> list[str]:
        """Las materias de la Secretaría presentes en el corpus (para el
        `<select>` de materia de la UI)."""
        return [
            row[0]
            for row in self.conn.execute(
                "SELECT DISTINCT materia FROM sumarios"
                " WHERE materia IS NOT NULL AND materia <> '' ORDER BY materia"
            )
        ]

    def contar_sumarios_de_tomo(self, tomo_id: int) -> int:
        return int(
            self.conn.execute(
                "SELECT count(*) FROM sumarios s JOIN fallos f ON f.id = s.fallo_id"
                " WHERE f.tomo_id = ?",
                (tomo_id,),
            ).fetchone()[0]
        )
