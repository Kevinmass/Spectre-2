"""Búsqueda de Spectre: fusión de los índices léxico y vectorial (D-6).

`hybrid` — RRF sobre `IndiceLexico` (FTS5) e `IndiceVectorial` (LanceDB), con
filtros de metadatos (año, tribunal, tipo de sección) resueltos vía
`db/repo.py`. Este paquete no importa `corpus/`.
"""

from spectre.search.hybrid import ResultadoHibrido, buscar_hibrido

__all__ = ["ResultadoHibrido", "buscar_hibrido"]
