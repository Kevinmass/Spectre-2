"""
Módulo de configuración del sistema.

Contiene la configuración centralizada para todo el sistema.
"""

from .settings import get_config, BaseConfig, Environment

__all__ = ['get_config', 'BaseConfig', 'Environment']
__version__ = "1.0.0"