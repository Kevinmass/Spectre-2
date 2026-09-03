"""Lectura de PDFs de tomos: texto por página y paginación oficial."""

from spectre.corpus.pdf.extract import (
    PaginaTexto,
    ResultadoOffset,
    calcular_offset,
    detectar_pagina_oficial,
    extraer_texto,
    persistir,
)

__all__ = [
    "PaginaTexto",
    "ResultadoOffset",
    "calcular_offset",
    "detectar_pagina_oficial",
    "extraer_texto",
    "persistir",
]
