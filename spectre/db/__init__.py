"""Acceso a datos de Spectre. Todo pasa por `repo`."""

from spectre.db.repo import (
    Fallo,
    Pagina,
    Repo,
    Tomo,
    ahora_iso,
    connect,
    migraciones_disponibles,
    migrate,
)

__all__ = [
    "Fallo",
    "Pagina",
    "Repo",
    "Tomo",
    "ahora_iso",
    "connect",
    "migraciones_disponibles",
    "migrate",
]
