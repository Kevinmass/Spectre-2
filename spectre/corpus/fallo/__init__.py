"""Del tomo al fallo: índice de partes, segmentación, estructura y citas.

Hoy solo `index_parser` (PR-06). `segmenter`, `structure` y `citations` llegan
en PR-07 a PR-10.
"""

from spectre.corpus.fallo.index_parser import (
    EntradaIndice,
    ResumenIndice,
    analizar_indice,
    localizar_indice_partes,
    parsear_indice,
)

__all__ = [
    "EntradaIndice",
    "ResumenIndice",
    "analizar_indice",
    "localizar_indice_partes",
    "parsear_indice",
]
