"""Cola de trabajos durable de Spectre. Todo pasa por `runner`; `pipeline`
(PR-19) es el pipeline completo de ingesta armado como una cadena de jobs."""

from spectre.jobs.pipeline import (
    ETAPAS,
    correr_pipeline,
    encolar_siguiente_etapa,
    iniciar_tomo,
    progreso,
    registrar_handlers,
    siguiente_etapa,
)
from spectre.jobs.runner import (
    EN_PROCESO,
    FALLIDO,
    HECHO,
    PENDIENTE,
    TERMINALES,
    Handler,
    Job,
    Runner,
)

__all__ = [
    "EN_PROCESO",
    "ETAPAS",
    "FALLIDO",
    "HECHO",
    "PENDIENTE",
    "TERMINALES",
    "Handler",
    "Job",
    "Runner",
    "correr_pipeline",
    "encolar_siguiente_etapa",
    "iniciar_tomo",
    "progreso",
    "registrar_handlers",
    "siguiente_etapa",
]
