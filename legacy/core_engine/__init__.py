#!/usr/bin/env python3
"""
Document Semantic Search - Core Engine Package

Este paquete contiene el motor central del sistema de búsqueda semántica.
"""

__version__ = "1.0.0"
__author__ = "Document Semantic Search Team"
__description__ = "Motor de búsqueda semántica local para documentos PDF"

# Importaciones principales para facilitar el uso
from .config.settings import get_config
from .api.app import app

# Exponer configuración global
config = get_config()

# Hacer disponible la aplicación FastAPI
api_app = app

__all__ = [
    'config',
    'api_app',
    'get_config'
]