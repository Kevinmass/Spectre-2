"""Fragmentación del fallo en chunks para embeber (PR-11).

`chunking/` consume `corpus/fallo` (secciones + texto por página) y produce los
`Chunk` que `embed/` y `index/` van a usar. No importa `embed/` ni `index/`.
"""

from spectre.chunking.chunker import (
    OBJETIVO_PALABRAS,
    SOLAPE_PALABRAS,
    Chunk,
    fragmentar_fallo,
    fragmentar_seccion,
    normalizar_espacios,
    ubicar_pagina,
    ventanas,
)

__all__ = [
    "OBJETIVO_PALABRAS",
    "SOLAPE_PALABRAS",
    "Chunk",
    "fragmentar_fallo",
    "fragmentar_seccion",
    "normalizar_espacios",
    "ubicar_pagina",
    "ventanas",
]
