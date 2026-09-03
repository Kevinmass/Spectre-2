"""Del tomo al fallo: índice de partes, segmentación, estructura y citas.

Hoy `index_parser` (PR-06), `segmenter` (PR-07), `structure` (PR-08) y
`sections` (PR-09). `citations` llega en PR-10.
"""

from spectre.corpus.fallo.index_parser import (
    EntradaIndice,
    ResumenIndice,
    analizar_indice,
    localizar_indice_partes,
    parsear_indice,
)
from spectre.corpus.fallo.sections import SeccionFallo, partir_secciones
from spectre.corpus.fallo.segmenter import (
    FalloSegmentado,
    ResumenSegmentacion,
    segmentar,
    segmentar_desde_indice,
    segmentar_por_delimitadores,
)
from spectre.corpus.fallo.structure import (
    MetadatosFallo,
    extraer_metadatos,
    texto_del_fallo,
)

__all__ = [
    "EntradaIndice",
    "FalloSegmentado",
    "MetadatosFallo",
    "ResumenIndice",
    "ResumenSegmentacion",
    "SeccionFallo",
    "analizar_indice",
    "extraer_metadatos",
    "localizar_indice_partes",
    "parsear_indice",
    "partir_secciones",
    "segmentar",
    "segmentar_desde_indice",
    "segmentar_por_delimitadores",
    "texto_del_fallo",
]
