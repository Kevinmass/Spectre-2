"""Índice léxico sobre FTS5 (decisión D-6 del plan).

A diferencia del índice vectorial (`vectors.py`, PR-13, un archivo LanceDB
aparte que hay que abrir), FTS5 vive dentro de la misma base SQLite que
`chunks`: la tabla virtual `chunks_fts` y los triggers que la mantienen
sincronizada están en la migración `0003_chunks_fts.sql`. Este módulo no
gestiona conexión ni esquema — recibe una conexión ya migrada, como `Repo` — y
solo hace lectura: la escritura la resuelven los triggers en cada INSERT /
UPDATE / DELETE sobre `chunks`, sin que este módulo ni `db/repo.py` tengan que
enterarse de que el índice existe.

`unicode61 remove_diacritics 2` (elegido en la migración porque SQLite no trae
un stemmer en español): sin reducir "artículos"/"artículo" a la misma raíz,
pero si matchea con o sin tilde, que es lo que importa para citas legales
("artículo 14 de la ley 48" tiene que encontrarse aunque quien busca no
tipee la tilde).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_TABLA = "chunks_fts"
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class Resultado:
    """Un resultado de búsqueda léxica. `rank` es el bm25 que calcula FTS5:
    más negativo = más relevante (orden ascendente = mejor primero)."""

    chunk_id: int
    rank: float


def _consulta_fts(texto: str) -> str:
    """Arma una consulta `MATCH` segura a partir de texto libre.

    Cada palabra se manda entre comillas dobles (una frase de un solo
    término), así ningún carácter de sintaxis de FTS5 que aparezca en lo que
    tipeó el usuario (`-`, `:`, `*`, `"`, paréntesis...) rompe la consulta.
    Términos separados por espacio son un AND implícito de FTS5: buscar
    "artículo 14 de la ley 48" exige los seis términos en el chunk, en
    cualquier orden.
    """
    tokens = _TOKEN.findall(texto)
    if not tokens:
        raise ValueError("la consulta no tiene ningún término reconocible")
    return " ".join('"' + t.replace('"', '""') + '"' for t in tokens)


class IndiceLexico:
    """Envuelve la tabla virtual `chunks_fts` de una conexión ya migrada."""

    def __init__(self, conn: sqlite3.Connection, *, tabla: str = _TABLA) -> None:
        self.conn = conn
        self.tabla = tabla

    def buscar(self, consulta: str, *, k: int = 10) -> list[Resultado]:
        """Los `k` chunks que mejor matchean `consulta`, mejor primero. Lista
        vacía si ninguno matchea."""
        sql_consulta = _consulta_fts(consulta)
        filas = self.conn.execute(
            f"SELECT rowid AS chunk_id, rank FROM {self.tabla}"
            f" WHERE {self.tabla} MATCH ? ORDER BY rank LIMIT ?",
            (sql_consulta, k),
        )
        return [Resultado(int(f["chunk_id"]), float(f["rank"])) for f in filas]

    def contar(self) -> int:
        """Cuántos chunks tiene **indexados** de verdad `chunks_fts`.

        No es `SELECT count(*) FROM chunks_fts`: en una tabla "external
        content", una consulta sin `MATCH` no toca el índice invertido, lee
        directo de la tabla de respaldo (`chunks`) — daría el mismo número
        aunque el índice estuviera vacío o desincronizado. `<tabla>_docsize`
        es la tabla-sombra que FTS5 sí mantiene por documento indexado (la usa
        para el bm25 de `rank`); contarla es lo que refleja el estado real del
        índice, no el de `chunks`.
        """
        return int(
            self.conn.execute(f"SELECT count(*) FROM {self.tabla}_docsize").fetchone()[
                0
            ]
        )

    def reconstruir(self) -> None:
        """Repuebla el índice desde `chunks` (comando `rebuild` de FTS5). Para
        el caso raro de que se desincronice: un `INSERT`/`UPDATE`/`DELETE`
        sobre `chunks` que saltee los triggers (p. ej. una carga masiva con
        `executescript` que deshabilite triggers a propósito)."""
        self.conn.execute(f"INSERT INTO {self.tabla}({self.tabla}) VALUES ('rebuild')")
        self.conn.commit()
