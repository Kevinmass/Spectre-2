"""Fuente CSJN de la colección Fallos (D-9): catálogo de tomos disponibles.

`catalog` lista qué tomos hay (número, volumen, año, id de la CSJN) leyendo
el sitio oficial de la Secretaría de Jurisprudencia. `download` (descargar los
PDFs) es PR-17.
"""

from spectre.corpus.csjn.catalog import EntradaCatalogo, listar_catalogo, parsear_pagina

__all__ = ["EntradaCatalogo", "listar_catalogo", "parsear_pagina"]
