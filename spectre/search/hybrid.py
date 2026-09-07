"""Búsqueda híbrida: fusión RRF de léxico + vectorial (D-6 del plan).

`search/` no importa `corpus/`: recibe una conexión ya migrada (para
`Repo`/`IndiceLexico`, que viven en la base SQLite), un `IndiceVectorial` ya
construido (LanceDB, PR-13) y el vector ya embebido de la consulta — embeber
texto es cosa de `embed/`, este módulo no sabe de modelos.

**RRF** (Reciprocal Rank Fusion, Cormack et al. 2009): cada chunk suma
`1 / (k_rrf + rango + 1)` por cada lista en la que aparece (rango 0-based);
se fusiona por rango, no por el puntaje crudo de cada índice — bm25 (FTS5) y
distancia coseno (LanceDB) no son comparables en la misma escala, y RRF evita
tener que normalizarlos. `k_rrf = 60` es la constante estándar de la
literatura (Elasticsearch, Weaviate la usan de default); no hay nada en este
corpus que pida otra. El reranker semántico queda fuera del MVP (D-6): esto
es la fusión de dos listas, no un reordenamiento por relevancia real.

**Los filtros se aplican después de traer candidatos de cada índice**
(`candidatos` por lista, no `k`): ni LanceDB ni FTS5 saben de año / tribunal /
tipo de sección, esos metadatos viven en `fallos` / `secciones`.
`Repo.filtrar_chunks` hace ese cruce; acá solo se descartan los `chunk_id` que
no pasan el filtro, conservando el rango relativo de cada lista para RRF.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from spectre.db import Repo
from spectre.index import IndiceLexico, IndiceVectorial

_K_RRF = 60


@dataclass(frozen=True, slots=True)
class ResultadoHibrido:
    """Un resultado fusionado. `rank_lexico` / `rank_vectorial` son la
    posición (0 = primero) en cada lista de candidatos ya filtrada, o `None`
    si ese índice no lo trajo — sirve para mostrar en qué lista apareció."""

    chunk_id: int
    score: float
    rank_lexico: int | None
    rank_vectorial: int | None


def _rrf(
    listas: Sequence[Sequence[int]], *, k: int = _K_RRF
) -> list[tuple[int, float]]:
    puntajes: dict[int, float] = {}
    for lista in listas:
        for rango, chunk_id in enumerate(lista):
            puntajes[chunk_id] = puntajes.get(chunk_id, 0.0) + 1.0 / (k + rango + 1)
    return sorted(puntajes.items(), key=lambda par: par[1], reverse=True)


def buscar_hibrido(
    conn: sqlite3.Connection,
    idx_vectorial: IndiceVectorial,
    consulta_texto: str,
    vector_consulta: Sequence[float] | None,
    *,
    k: int = 10,
    candidatos: int = 50,
    anio_desde: int | None = None,
    anio_hasta: int | None = None,
    tribunal_origen: str | None = None,
    tipo_seccion: str | None = None,
    voz: str | None = None,
    materia: str | None = None,
) -> list[ResultadoHibrido]:
    """Fusiona léxico + vectorial y devuelve los `k` mejores `ResultadoHibrido`.

    `vector_consulta` en `None` corre en modo léxico puro (sin embedding
    disponible) — no es un error, D-6 no ata la búsqueda a que el modelo real
    esté instalado."""
    lexicos = IndiceLexico(conn).buscar(consulta_texto, k=candidatos)
    vecinos = (
        idx_vectorial.buscar(vector_consulta, k=candidatos)
        if vector_consulta is not None
        else []
    )

    candidatos_ids = {r.chunk_id for r in lexicos} | {v.chunk_id for v in vecinos}
    permitidos = Repo(conn).filtrar_chunks(
        candidatos_ids,
        anio_desde=anio_desde,
        anio_hasta=anio_hasta,
        tribunal_origen=tribunal_origen,
        tipo_seccion=tipo_seccion,
        voz=voz,
        materia=materia,
    )

    lista_lex = [r.chunk_id for r in lexicos if r.chunk_id in permitidos]
    lista_vec = [v.chunk_id for v in vecinos if v.chunk_id in permitidos]
    rango_lex = {cid: i for i, cid in enumerate(lista_lex)}
    rango_vec = {cid: i for i, cid in enumerate(lista_vec)}

    fusion = _rrf([lista_lex, lista_vec])
    return [
        ResultadoHibrido(cid, score, rango_lex.get(cid), rango_vec.get(cid))
        for cid, score in fusion[:k]
    ]
