"""Configuración de Spectre.

Regla dura (defecto D-02 del proyecto anterior): las rutas se resuelven contra
la raíz del proyecto, **nunca** contra el directorio de trabajo. Una ruta
relativa pasada por env se ancla a `PROJECT_ROOT`; el CWD no entra en la cuenta
en ningún momento.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .../Spectre/spectre/config.py -> .../Spectre/spectre -> .../Spectre
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


class Settings(BaseSettings):
    """Config del motor. Se puebla desde variables `SPECTRE_*` y un `.env`
    opcional en la raíz del proyecto."""

    model_config = SettingsConfigDict(
        env_prefix="SPECTRE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Carpeta raíz de datos locales. Todo lo demás cuelga de acá.
    data_dir: Path = PROJECT_ROOT / "data"

    # D-7: modelo multilingüe chico (384 dim, CPU). Provisional hasta PR-12,
    # que fija la implementación y el registro por chunk.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    @field_validator("data_dir")
    @classmethod
    def _anclar_al_root(cls, v: Path) -> Path:
        v = Path(v)
        return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()

    @property
    def tomos_dir(self) -> Path:
        """PDFs de tomos descargados o subidos a mano."""
        return self.data_dir / "tomos"

    @property
    def db_path(self) -> Path:
        """SQLite: tomos, fallos, secciones, chunks, jobs, FTS5."""
        return self.data_dir / "spectre.db"

    @property
    def vectors_dir(self) -> Path:
        """Índice vectorial LanceDB, al lado de la base."""
        return self.data_dir / "vectors"

    def ensure_dirs(self) -> None:
        """Crea las carpetas de datos. No se llama al importar: solo cuando
        alguien va a escribir de verdad (evita el otro costado de D-02)."""
        for d in (self.data_dir, self.tomos_dir, self.vectors_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Punto de acceso único a la config para el resto del paquete."""
    return Settings()
