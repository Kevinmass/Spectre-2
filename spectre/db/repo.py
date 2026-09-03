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


def _tomo(row: sqlite3.Row | None) -> Tomo | None:
    return Tomo(**row) if row is not None else None


def _pagina(row: sqlite3.Row | None) -> Pagina | None:
    return Pagina(**row) if row is not None else None


def _fallo(row: sqlite3.Row | None) -> Fallo | None:
    return Fallo(**row) if row is not None else None


# --------------------------------------------------------------------------- #
# Repositorio
# --------------------------------------------------------------------------- #


class Repo:
    """Operaciones de datos sobre una conexión ya migrada.

    Cada escritura hace `commit()` por su cuenta: todavía no hay un job runner
    que quiera agrupar varias en una transacción (eso llega en PR-03).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

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
        self.conn.commit()
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
        self.conn.commit()

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
        self.conn.commit()
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
        self.conn.commit()
        return len(datos)

    def borrar_paginas(self, tomo_id: int) -> int:
        """Borra todas las páginas del tomo. Devuelve cuántas borró."""
        cur = self.conn.execute("DELETE FROM paginas WHERE tomo_id = ?", (tomo_id,))
        self.conn.commit()
        return cur.rowcount

    def set_texto_limpio(self, filas: Iterable[tuple[int, str]]) -> int:
        """Actualiza `texto_limpio` en lote. Cada fila es `(pagina_id, texto)`.
        Devuelve cuántas filas tocó."""
        datos = [(texto, pagina_id) for pagina_id, texto in filas]
        self.conn.executemany("UPDATE paginas SET texto_limpio = ? WHERE id = ?", datos)
        self.conn.commit()
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
        self.conn.commit()
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
