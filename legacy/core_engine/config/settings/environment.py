"""
Definición de entornos del sistema.

Este módulo define los diferentes entornos en los que puede ejecutarse el sistema.
"""

from enum import Enum

class Environment(Enum):
    """Entornos disponibles para el sistema."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"
    
    @classmethod
    def from_string(cls, env_str: str) -> 'Environment':
        """Convierte un string a un entorno."""
        env_str = env_str.lower().strip()
        if env_str in ['dev', 'development', 'desarrollo']:
            return cls.DEVELOPMENT
        elif env_str in ['test', 'testing', 'pruebas']:
            return cls.TESTING
        elif env_str in ['prod', 'production', 'produccion', 'producción']:
            return cls.PRODUCTION
        else:
            return cls.DEVELOPMENT  # Valor por defecto
    
    def is_development(self) -> bool:
        """Verifica si es entorno de desarrollo."""
        return self == Environment.DEVELOPMENT
    
    def is_production(self) -> bool:
        """Verifica si es entorno de producción."""
        return self == Environment.PRODUCTION
    
    def is_testing(self) -> bool:
        """Verifica si es entorno de pruebas."""
        return self == Environment.TESTING