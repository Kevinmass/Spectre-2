"""Sincronización de los sumarios oficiales de la CSJN al corpus local (PR-C2b).

`corpus/csjn/sumarios.py` (PR-C2a) sabe *bajar* los sumarios de la Secretaría de
Jurisprudencia; su docstring dice explícitamente que **no persiste nada** (regla
de dependencias: `corpus/` no toca la base salvo por `db/repo.py`, y ese módulo
la mantiene pura para poder testear el parseo sin red). Este paquete es el que
compone las dos mitades —el cliente HTTP y `db/repo.py`— igual que `search/`
compone `index/` + `db/`.

No es una etapa del pipeline (`jobs/pipeline.py`): el corpus ya está indexado, y
una etapa nueva obligaría a reindexar y ataría la ingesta a un sitio con WAF que
puede cortar a mitad. La sincronización se dispara aparte —`spectre sumarios
sync <tomo>` o el botón de la Biblioteca (`POST /api/tomos/{n}/sumarios/sync`)—
y es reejecutable: `reemplazar_sumarios_de_fallo` borra y reinserta, así una
segunda corrida no duplica.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass

from spectre.corpus.csjn.sumarios import Sumario, TransporteHTTP, buscar_sumarios
from spectre.db import Repo


@dataclass(frozen=True, slots=True)
class ResumenSync:
    """Lo que dejó una corrida de `sincronizar_tomo`."""

    tomo: int
    fallos_consultados: int
    fallos_con_sumario: int
    sumarios_totales: int
    voces_distintas: int


def _persistir(repo: Repo, fallo_id: int, sumarios: list[Sumario]) -> None:
    repo.reemplazar_sumarios_de_fallo(
        fallo_id,
        [
            (i, s.texto, s.voces, s.materia, s.id_documento)
            for i, s in enumerate(sumarios)
        ],
    )


def sincronizar_fallo(
    conn: sqlite3.Connection,
    fallo_id: int,
    *,
    transporte: TransporteHTTP | None = None,
) -> int:
    """Trae los sumarios del fallo `fallo_id` desde la CSJN y los persiste
    (reemplazando los que hubiera). Devuelve cuántos guardó. `0` si el fallo no
    tiene página de inicio o la Secretaría no lo sumarió."""
    repo = Repo(conn)
    fallo = repo.get_fallo(fallo_id)
    if fallo is None or fallo.pagina_inicio is None:
        return 0
    tomo = repo.get_tomo(fallo.tomo_id)
    if tomo is None:
        return 0
    sumarios = buscar_sumarios(tomo.numero, fallo.pagina_inicio, transporte=transporte)
    _persistir(repo, fallo_id, sumarios)
    return len(sumarios)


def sincronizar_tomo(
    conn: sqlite3.Connection,
    numero: int,
    *,
    transporte: TransporteHTTP | None = None,
    pausa: float = 0.5,
    log: Callable[[str], None] | None = None,
) -> ResumenSync:
    """Sincroniza los sumarios de todos los fallos de un tomo ya segmentado.

    Reusa **una** sesión HTTP (`transporte`) para todos los fallos —el flujo de
    la CSJN es *stateful* por cookies— y espera `pausa` segundos entre fallos
    para no martillar el sitio. `log`, si se pasa, recibe una línea de progreso
    por fallo. Reejecutable: cada fallo se reemplaza, no se acumula.
    """
    repo = Repo(conn)
    tomo = repo.get_tomo_por_numero(numero)
    if tomo is None:
        raise ValueError(f"no existe el tomo {numero} en la base")

    tr = transporte or TransporteHTTP()
    fallos = [
        f
        for f in repo.list_fallos(tomo.id)
        if f.pagina_inicio is not None and f.cita is not None
    ]

    con_sumario = 0
    total = 0
    for i, f in enumerate(fallos, 1):
        sumarios = buscar_sumarios(numero, f.pagina_inicio, transporte=tr)
        _persistir(repo, f.id, sumarios)
        if sumarios:
            con_sumario += 1
            total += len(sumarios)
        if log is not None:
            log(f"[{i}/{len(fallos)}] {f.cita}: {len(sumarios)} sumario(s)")
        if pausa and i < len(fallos):
            time.sleep(pausa)

    voces_distintas = int(
        conn.execute(
            "SELECT count(DISTINCT fv.voz_id) FROM fallo_voces fv"
            " JOIN fallos f ON f.id = fv.fallo_id WHERE f.tomo_id = ?",
            (tomo.id,),
        ).fetchone()[0]
    )
    return ResumenSync(
        tomo=numero,
        fallos_consultados=len(fallos),
        fallos_con_sumario=con_sumario,
        sumarios_totales=total,
        voces_distintas=voces_distintas,
    )


__all__ = [
    "ResumenSync",
    "sincronizar_fallo",
    "sincronizar_tomo",
]
