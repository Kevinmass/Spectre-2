"""Del tomo al fallo: índice de partes, segmentación, estructura, secciones y
citas.

Hoy `index_parser` (PR-06), `segmenter` (PR-07), `structure` (PR-08),
`sections` (PR-09), `citations` (PR-10) y `partes` (PR-C5: clasifica actor /
demandado en persona_fisica / empresa / estado / organismo).
"""

from spectre.corpus.fallo.citations import (
    CitaExtraida,
    contar_referencias,
    extraer_citas,
)
from spectre.corpus.fallo.index_parser import (
    EntradaIndice,
    ResumenIndice,
    analizar_indice,
    localizar_indice_partes,
    parsear_indice,
)
from spectre.corpus.fallo.partes import clasificar_parte
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
    texto_del_fallo_paginado,
)

__all__ = [
    "CitaExtraida",
    "EntradaIndice",
    "FalloSegmentado",
    "MetadatosFallo",
    "ResumenIndice",
    "ResumenSegmentacion",
    "SeccionFallo",
    "analizar_indice",
    "clasificar_parte",
    "contar_referencias",
    "extraer_citas",
    "extraer_metadatos",
    "localizar_indice_partes",
    "parsear_indice",
    "partir_secciones",
    "segmentar",
    "segmentar_desde_indice",
    "segmentar_por_delimitadores",
    "texto_del_fallo",
    "texto_del_fallo_paginado",
]
