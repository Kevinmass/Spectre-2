"""
Pruebas unitarias para el sistema de configuración.

Este módulo contiene pruebas para la configuración del sistema.
"""

import pytest
import os
import tempfile
import yaml
from pathlib import Path

from core_engine.config.settings import BaseConfig, Environment, get_config

class TestEnvironment:
    """Pruebas para la clase Environment."""
    
    def test_environment_creation(self):
        """Prueba la creación de entornos."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.TESTING.value == "testing"
        assert Environment.PRODUCTION.value == "production"
    
    def test_environment_from_string(self):
        """Prueba la creación de entornos desde string."""
        assert Environment.from_string("development") == Environment.DEVELOPMENT
        assert Environment.from_string("dev") == Environment.DEVELOPMENT
        assert Environment.from_string("DEVELOPMENT") == Environment.DEVELOPMENT
        
        assert Environment.from_string("testing") == Environment.TESTING
        assert Environment.from_string("test") == Environment.TESTING
        
        assert Environment.from_string("production") == Environment.PRODUCTION
        assert Environment.from_string("prod") == Environment.PRODUCTION
        
        # Valor por defecto
        assert Environment.from_string("invalid") == Environment.DEVELOPMENT
    
    def test_environment_methods(self):
        """Prueba los métodos de verificación de entornos."""
        assert Environment.DEVELOPMENT.is_development() is True
        assert Environment.DEVELOPMENT.is_production() is False
        assert Environment.DEVELOPMENT.is_testing() is False
        
        assert Environment.PRODUCTION.is_production() is True
        assert Environment.PRODUCTION.is_development() is False
        assert Environment.PRODUCTION.is_testing() is False
        
        assert Environment.TESTING.is_testing() is True
        assert Environment.TESTING.is_development() is False
        assert Environment.TESTING.is_production() is False

class TestBaseConfig:
    """Pruebas para la clase BaseConfig."""
    
    def test_config_creation(self):
        """Prueba la creación de la configuración."""
        config = BaseConfig()
        
        assert config.environment is not None
        assert hasattr(config, 'paths')
        assert hasattr(config, 'system')
        assert hasattr(config, 'embedding')
        assert hasattr(config, 'processing')
        assert hasattr(config, 'database')
    
    def test_config_with_file(self):
        """Prueba la creación de configuración con archivo."""
        # Crear un archivo de configuración temporal
        config_data = {
            'paths': {
                'documents_path': 'test/documents',
                'processed_path': 'test/processed'
            },
            'system': {
                'debug': True,
                'log_level': 'DEBUG'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            config = BaseConfig(config_file)
            
            assert config.paths.documents_path.endswith('test/documents')
            assert config.paths.processed_path.endswith('test/processed')
            assert config.system.debug is True
            assert config.system.log_level == 'DEBUG'
            
        finally:
            os.unlink(config_file)
    
    def test_config_get_method(self):
        """Prueba el método get de configuración."""
        config = BaseConfig()
        
        # Prueba con clave válida
        value = config.get('system.debug')
        assert isinstance(value, bool)
        
        # Prueba con clave inválida
        value = config.get('invalid.key', 'default')
        assert value == 'default'
        
        # Prueba con sección inválida
        value = config.get('invalid.debug', 'default')
        assert value == 'default'
    
    def test_config_update_method(self):
        """Prueba el método update de configuración."""
        config = BaseConfig()
        
        # Actualizar un valor existente
        original_debug = config.system.debug
        config.update('system.debug', not original_debug)
        assert config.system.debug == (not original_debug)
        
        # Intentar actualizar con clave inválida
        with pytest.raises(ValueError):
            config.update('invalid.key', 'value')
    
    def test_config_to_dict(self):
        """Prueba el método to_dict de configuración."""
        config = BaseConfig()
        config_data = config.to_dict()
        
        assert isinstance(config_data, dict)
        assert 'paths' in config_data
        assert 'system' in config_data
        assert 'embedding' in config_data
        assert 'processing' in config_data
        assert 'database' in config_data
    
    def test_config_save_to_file(self):
        """Prueba el método save_to_file de configuración."""
        config = BaseConfig()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_file = f.name
        
        try:
            config.save_to_file(config_file)
            
            # Verificar que el archivo se creó
            assert os.path.exists(config_file)
            
            # Verificar que el contenido es válido YAML
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
                assert isinstance(data, dict)
                
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)
    
    def test_config_environment_specific(self):
        """Prueba la configuración específica por entorno."""
        # Probar con entorno de desarrollo
        os.environ['DSS_ENV'] = 'development'
        config = BaseConfig()
        
        assert config.system.debug is True
        assert config.system.log_level == 'DEBUG'
        assert config.processing.cleanup_temp_files is False
        
        # Probar con entorno de producción
        os.environ['DSS_ENV'] = 'production'
        config = BaseConfig()
        
        assert config.system.debug is False
        assert config.system.log_level == 'WARNING'
        assert config.system.max_workers > 0  # Debe usar CPU count
        
        # Limpiar variable de entorno
        del os.environ['DSS_ENV']

class TestGlobalConfig:
    """Pruebas para la configuración global."""
    
    def test_get_config(self):
        """Prueba la obtención de la configuración global."""
        config1 = get_config()
        config2 = get_config()
        
        # Debe retornar la misma instancia
        assert config1 is config2
    
    def test_set_config(self):
        """Prueba el establecimiento de la configuración global."""
        from core_engine.config.settings import set_config
        
        original_config = get_config()
        new_config = BaseConfig()
        
        set_config(new_config)
        
        assert get_config() is new_config
        
        # Restaurar configuración original
        set_config(original_config)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])