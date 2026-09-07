"""Backfill de la clasificación de partes sobre el corpus ya indexado (PR-C5).

La etapa `estructurar` del pipeline persiste actor / demandado y su tipo para
los tomos nuevos. Este módulo reclasifica los que ya estaban: recomputa
`_partes(caratula)` + `clasificar_parte` a partir de `fallos.caratula` —que ya
está en la base—, **sin abrir un solo PDF**. Reejecutable: correrlo de nuevo
(por ejemplo tras afinar las reglas de `corpus/fallo/partes.py`) reescribe.

Compone `corpus/fallo` (funciones puras) con `db/repo.py`, como `spectre/
sumarios/`. No importa `index/` ni `embed/`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from spectre.corpus.fallo import clasificar_parte
from spectre.corpus.fallo.structure import _partes
from spectre.db import Repo


@dataclass(frozen=True, slots=True)
class ResumenReclasificacion:
    fallos: int
    con_actor_tipo: int
    con_demandado_tipo: int
    por_tipo: dict[str, int] = field(default_factory=dict)


def reclasificar_partes(
    conn: sqlite3.Connection, *, tomo: int | None = None
) -> ResumenReclasificacion:
    """Recalcula `actor` / `actor_tipo` / `demandado` / `demandado_tipo` de cada
    fallo (o de los de `tomo`) desde su carátula. Devuelve el resumen de
    cobertura."""
    repo = Repo(conn)
    tomo_id = None
    if tomo is not None:
        t = repo.get_tomo_por_numero(tomo)
        if t is None:
            raise ValueError(f"no existe el tomo {tomo} en la base")
        tomo_id = t.id

    n = 0
    for f in repo.iter_fallos(tomo_id=tomo_id):
        actor, demandado = _partes(f.caratula)
        repo.actualizar_fallo(
            f.id,
            actor=actor,
            actor_tipo=clasificar_parte(actor),
            demandado=demandado,
            demandado_tipo=clasificar_parte(demandado),
        )
        n += 1

    cob = repo.cobertura_partes(tomo_id=tomo_id)
    return ResumenReclasificacion(
        fallos=n,
        con_actor_tipo=cob["con_actor_tipo"],
        con_demandado_tipo=cob["con_demandado_tipo"],
        por_tipo=cob["por_tipo"],
    )


__all__ = ["ResumenReclasificacion", "reclasificar_partes"]
