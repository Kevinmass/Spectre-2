"""Lectura de PDFs de tomos: texto por página, paginación oficial y limpieza."""

from spectre.corpus.pdf.clean import (
    contar_palabras,
    es_versalita,
    limpiar,
    limpiar_tomo,
)
from spectre.corpus.pdf.extract import (
    PaginaTexto,
    ResultadoOffset,
    calcular_offset,
    detectar_pagina_oficial,
    extraer_texto,
    persistir,
)
from spectre.corpus.pdf.quality import ResultadoCalidad, medir_calidad

__all__ = [
    "PaginaTexto",
    "ResultadoCalidad",
    "ResultadoOffset",
    "calcular_offset",
    "contar_palabras",
    "detectar_pagina_oficial",
    "es_versalita",
    "extraer_texto",
    "limpiar",
    "limpiar_tomo",
    "medir_calidad",
    "persistir",
]
