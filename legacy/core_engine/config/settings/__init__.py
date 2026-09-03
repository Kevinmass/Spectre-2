"""
Módulo de configuración del sistema.

Contiene la configuración centralizada para todo el sistema.
"""

from .base_config import BaseConfig, get_config
from .environment import Environment

__all__ = ['BaseConfig', 'get_config', 'Environment']
__version__ = "1.0.0"