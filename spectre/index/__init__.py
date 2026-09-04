"""Índices de búsqueda de Spectre.

`vectors` — índice vectorial en LanceDB (D-5). `lexical` (FTS5) llega en PR-14,
`search/` fusiona los dos (PR-15). Este paquete recibe vectores / texto ya
listos; no importa `corpus/`.
"""

from spectre.index.vectors import IndiceVectorial, Vecino

__all__ = ["IndiceVectorial", "Vecino"]
