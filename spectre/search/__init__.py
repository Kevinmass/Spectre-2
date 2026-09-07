"""Búsqueda de Spectre: fusión de los índices léxico y vectorial (D-6).

`hybrid` — RRF sobre `IndiceLexico` (FTS5) e `IndiceVectorial` (LanceDB), con
filtros de metadatos (año, tribunal, tipo de sección) resueltos vía
`db/repo.py`. `agrupar` (PR-A1) colapsa esos chunks a una lista de fallos con
sus pasajes anidados. Este paquete no importa `corpus/`.
"""

from spectre.search.agrupar import FalloAgrupado, Pasaje, agrupar_por_fallo
from spectre.search.hybrid import ResultadoHibrido, buscar_hibrido
from spectre.search.palabras_vacias import PALABRAS_VACIAS

__all__ = [
    "PALABRAS_VACIAS",
    "FalloAgrupado",
    "Pasaje",
    "ResultadoHibrido",
    "agrupar_por_fallo",
    "buscar_hibrido",
]
