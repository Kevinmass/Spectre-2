"""Índices de búsqueda de Spectre.

`vectors` — índice vectorial en LanceDB (D-5). `lexical` — índice léxico FTS5
sobre la propia base SQLite (D-6). `search/` fusiona los dos (PR-15). Este
paquete recibe vectores / texto ya listos; no importa `corpus/`.
"""

from spectre.index.lexical import IndiceLexico, Resultado
from spectre.index.vectors import IndiceVectorial, Vecino

__all__ = ["IndiceLexico", "IndiceVectorial", "Resultado", "Vecino"]
