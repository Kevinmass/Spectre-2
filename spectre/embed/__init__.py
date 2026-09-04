"""Embeddings de Spectre (D-7, D-8).

`EmbeddingModel` es la interfaz; `ModeloLocalST` la implementación por defecto
(sentence-transformers, dependencia opcional). `cargar_modelo()` arma el modelo
que dice la config. Este paquete no importa `corpus/` ni `index/`; recibe texto
y devuelve vectores.
"""

from __future__ import annotations

from spectre.embed.base import EmbeddingModel
from spectre.embed.local_st import ModeloLocalST


def cargar_modelo(nombre: str | None = None) -> EmbeddingModel:
    """El modelo de embeddings a usar. Sin argumento, el de la config
    (`embedding_model`). No lo carga todavía: `ModeloLocalST` es perezoso."""
    if nombre is None:
        from spectre.config import get_settings

        nombre = get_settings().embedding_model
    return ModeloLocalST(nombre)


__all__ = [
    "EmbeddingModel",
    "ModeloLocalST",
    "cargar_modelo",
]
