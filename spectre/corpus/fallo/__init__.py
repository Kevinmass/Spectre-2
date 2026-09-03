"""Del tomo al fallo: índice de partes, segmentación, estructura y citas.

Hoy `index_parser` (PR-06) y `segmenter` (PR-07). `structure` y `citations`
llegan en PR-08 a PR-10.
"""

from spectre.corpus.fallo.index_parser import (
    EntradaIndice,
    ResumenIndice,
    analizar_indice,
    localizar_indice_partes,
    parsear_indice,
)
from spectre.corpus.fallo.segmenter import (
    FalloSegmentado,
    ResumenSegmentacion,
    segmentar,
    segmentar_desde_indice,
    segmentar_por_delimitadores,
)

__all__ = [
    "EntradaIndice",
    "FalloSegmentado",
    "ResumenIndice",
    "ResumenSegmentacion",
    "analizar_indice",
    "localizar_indice_partes",
    "parsear_indice",
    "segmentar",
    "segmentar_desde_indice",
    "segmentar_por_delimitadores",
]
