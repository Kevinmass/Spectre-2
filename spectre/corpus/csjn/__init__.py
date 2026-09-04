"""Fuente CSJN de la colección Fallos (D-9): catálogo y descarga de tomos.

`catalog` lista qué tomos hay (número, volumen, año, id de la CSJN) leyendo
el sitio oficial de la Secretaría de Jurisprudencia. `download` baja el PDF de
un tomo (por su `csjn_tomo_id`) con reintentos y caché en disco.
"""

from spectre.corpus.csjn.catalog import EntradaCatalogo, listar_catalogo, parsear_pagina
from spectre.corpus.csjn.download import Descarga, descargar_tomo, descargar_varios

__all__ = [
    "Descarga",
    "EntradaCatalogo",
    "descargar_tomo",
    "descargar_varios",
    "listar_catalogo",
    "parsear_pagina",
]
