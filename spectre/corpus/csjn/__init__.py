"""Fuente CSJN de la colección Fallos (D-9): catálogo, descarga y sumarios.

`catalog` lista qué tomos hay (número, volumen, año, id de la CSJN) leyendo
el sitio oficial de la Secretaría de Jurisprudencia. `download` baja el PDF de
un tomo (por su `csjn_tomo_id`) con reintentos y caché en disco. `sumarios`
(PR-C2) consulta los sumarios oficiales y sus voces por tomo y página.
"""

from spectre.corpus.csjn.catalog import EntradaCatalogo, listar_catalogo, parsear_pagina
from spectre.corpus.csjn.download import Descarga, descargar_tomo, descargar_varios
from spectre.corpus.csjn.sumarios import (
    Sumario,
    TransporteHTTP,
    Voz,
    buscar_sumarios,
    buscar_voces,
)

__all__ = [
    "Descarga",
    "EntradaCatalogo",
    "Sumario",
    "TransporteHTTP",
    "Voz",
    "buscar_sumarios",
    "buscar_voces",
    "descargar_tomo",
    "descargar_varios",
    "listar_catalogo",
    "parsear_pagina",
]
