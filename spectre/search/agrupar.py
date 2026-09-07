"""PR-A1 — agrupar los resultados de la búsqueda por fallo.

`buscar_hibrido` (PR-15) devuelve chunks sueltos ranqueados por RRF. Para la
interfaz eso son "fragmentos, no fallos": una misma sentencia aparece varias
veces y tapa a las demás (relevamiento del plan v2, §2.1 — 8 consultas → 80
resultados → 42 fallos distintos). Acá se colapsa la lista de chunks a una
lista de fallos, cada uno con sus pasajes anidados.

Regla del plan: **el mejor pasaje por tipo de sección**, no solo el mejor
absoluto. Una mayoría y una disidencia del mismo fallo dicen cosas distintas
y colapsarlas a un solo pasaje perdería la disidencia. Dos votos del mismo
tipo sí se colapsan (se conserva el de más puntaje); `total_pasajes` guarda
cuántos chunks del fallo entraron antes de ese recorte, para el contador
"N pasajes más en este fallo" de la interfaz.

Como `hybrid`, este módulo consulta `db/repo.py` y no importa `corpus/`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field

from spectre.db import Fallo, Repo
from spectre.search.hybrid import ResultadoHibrido


@dataclass(frozen=True, slots=True)
class Pasaje:
    """Un chunk que matcheó, ya ubicado dentro de su fallo. `texto` es el
    chunk entero (~400 palabras); recortar el extracto es cosa de quien
    presenta."""

    chunk_id: int
    score: float
    seccion_tipo: str | None
    seccion_autor: str | None
    pagina_oficial: int | None
    texto: str


@dataclass(frozen=True, slots=True)
class FalloAgrupado:
    """Un resultado = un fallo. `score` es el del mejor de sus pasajes (marca
    su posición en la lista). `total_pasajes` es cuántos chunks del fallo
    trajo la búsqueda; `pasajes` es ese conjunto recortado a uno por tipo de
    sección, de mejor a peor."""

    fallo_id: int
    cita: str | None
    caratula: str | None
    fecha: str | None
    tribunal_origen: str | None
    score: float
    total_pasajes: int
    pasajes: list[Pasaje]


@dataclass(slots=True)
class _Grupo:
    fallo: Fallo | None
    score: float
    total: int = 0
    por_tipo: dict[str | None, Pasaje] = field(default_factory=dict)


def agrupar_por_fallo(
    conn: sqlite3.Connection,
    resultados: Sequence[ResultadoHibrido],
    *,
    limite: int,
) -> list[FalloAgrupado]:
    """Colapsa `resultados` (chunks ranqueados, el mejor primero) a como
    mucho `limite` fallos.

    Conserva el orden de llegada: el primer chunk de cada fallo fija su
    posición y su `score`. Como `resultados` ya viene de mejor a peor, ese
    primer chunk es también el de más puntaje del fallo, y el primero que se
    ve para cada tipo de sección es el que se conserva."""
    repo = Repo(conn)
    orden: list[int] = []
    grupos: dict[int, _Grupo] = {}

    for r in resultados:
        chunk = repo.get_chunk(r.chunk_id)
        if chunk is None:
            continue

        grupo = grupos.get(chunk.fallo_id)
        if grupo is None:
            grupo = _Grupo(fallo=repo.get_fallo(chunk.fallo_id), score=r.score)
            grupos[chunk.fallo_id] = grupo
            orden.append(chunk.fallo_id)

        grupo.total += 1
        seccion = (
            repo.get_seccion(chunk.seccion_id) if chunk.seccion_id is not None else None
        )
        tipo = seccion.tipo if seccion is not None else None
        if tipo not in grupo.por_tipo:
            grupo.por_tipo[tipo] = Pasaje(
                chunk_id=chunk.id,
                score=r.score,
                seccion_tipo=tipo,
                seccion_autor=seccion.autor if seccion is not None else None,
                pagina_oficial=chunk.pagina_oficial,
                texto=chunk.texto,
            )

    agrupados: list[FalloAgrupado] = []
    for fallo_id in orden[:limite]:
        grupo = grupos[fallo_id]
        pasajes = sorted(grupo.por_tipo.values(), key=lambda p: p.score, reverse=True)
        agrupados.append(
            FalloAgrupado(
                fallo_id=fallo_id,
                cita=grupo.fallo.cita if grupo.fallo is not None else None,
                caratula=grupo.fallo.caratula if grupo.fallo is not None else None,
                fecha=grupo.fallo.fecha if grupo.fallo is not None else None,
                tribunal_origen=(
                    grupo.fallo.tribunal_origen if grupo.fallo is not None else None
                ),
                score=grupo.score,
                total_pasajes=grupo.total,
                pasajes=pasajes,
            )
        )
    return agrupados
