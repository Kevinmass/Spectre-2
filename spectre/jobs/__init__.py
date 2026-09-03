"""Cola de trabajos durable de Spectre. Todo pasa por `runner`."""

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
    "FALLIDO",
    "HECHO",
    "PENDIENTE",
    "TERMINALES",
    "Handler",
    "Job",
    "Runner",
]
