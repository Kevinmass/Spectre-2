"""
Configuración base del sistema.

Este módulo contiene la configuración centralizada para todo el sistema.
Utiliza variables de entorno y un archivo de configuración YAML para la flexibilidad.
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from .environment import Environment

@dataclass
class DatabaseConfig:
    """Configuración de la base de datos vectorial."""
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "documents"
    distance: str = "Cosine"
    vector_size: int = 384  # Tamaño típico para modelos pequeños
    recreate_collection: bool = False

@dataclass
class EmbeddingConfig:
    """Configuración de embeddings."""
    model_name: str = "all-MiniLM-L6-v2"
    model_path: str = "models/embeddings/all-MiniLM-L6-v2"
    device: str = "cpu"  # cpu o cuda
    batch_size: int = 32
    normalize_embeddings: bool = True

@dataclass
class ProcessingConfig:
    """Configuración de procesamiento de documentos."""
    chunk_size: int = 500  # Palabras por chunk
    chunk_overlap: int = 100  # Superposición entre chunks
    max_document_size_mb: int = 50  # Tamaño máximo de documento
    supported_formats: list = field(default_factory=lambda: ['.pdf'])
    cleanup_temp_files: bool = True

@dataclass
class SystemConfig:
    """Configuración del sistema."""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"
    max_workers: int = 4
    cpu_usage_limit: float = 0.8  # Porcentaje máximo de CPU a usar
    memory_limit_gb: float = 4.0  # Límite de memoria en GB

@dataclass
class PathsConfig:
    """Configuración de rutas del sistema."""
    base_path: str = str(Path(__file__).parent.parent.parent.parent.parent)
    documents_path: str = "data/documents"
    processed_path: str = "data/processed"
    vector_index_path: str = "data/vector_index"
    logs_path: str = "logs"
    temp_path: str = "temp"
    
    def __post_init__(self):
        """Convierte rutas relativas a absolutas."""
        self.base_path = os.path.abspath(self.base_path)
        self.documents_path = os.path.join(self.base_path, self.documents_path)
        self.processed_path = os.path.join(self.base_path, self.processed_path)
        self.vector_index_path = os.path.join(self.base_path, self.vector_index_path)
        self.logs_path = os.path.join(self.base_path, self.logs_path)
        self.temp_path = os.path.join(self.base_path, self.temp_path)

class BaseConfig:
    """Configuración base del sistema."""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Inicializa la configuración.
        
        Args:
            config_file: Ruta al archivo de configuración YAML (opcional).
        """
        self.environment = self._get_environment()
        self._load_config_file(config_file)
        self._setup_paths()
        self._setup_logging()
    
    def _get_environment(self) -> Environment:
        """Obtiene el entorno desde variables de entorno."""
        env_str = os.getenv('DSS_ENV', 'development')
        return Environment.from_string(env_str)
    
    def _load_config_file(self, config_file: Optional[str]):
        """Carga la configuración desde un archivo YAML."""
        config_data = {}
        
        # Archivo de configuración por defecto
        default_config_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', '..', '..', 'config', 'settings.yaml'
        )
        
        # Prioridad: parámetro > variable de entorno > archivo por defecto > valores por defecto
        config_to_load = config_file or os.getenv('DSS_CONFIG_FILE', default_config_path)
        
        if os.path.exists(config_to_load):
            try:
                with open(config_to_load, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Advertencia: No se pudo cargar el archivo de configuración {config_to_load}: {e}")
        
        # Configuración de paths
        paths_data = config_data.get('paths', {})
        self.paths = PathsConfig(**paths_data)
        
        # Configuración del sistema
        system_data = config_data.get('system', {})
        self.system = SystemConfig(**system_data)
        self.system.environment = self.environment
        
        # Configuración de embeddings
        embedding_data = config_data.get('embedding', {})
        self.embedding = EmbeddingConfig(**embedding_data)
        
        # Configuración de procesamiento
        processing_data = config_data.get('processing', {})
        self.processing = ProcessingConfig(**processing_data)
        
        # Configuración de base de datos
        database_data = config_data.get('database', {})
        self.database = DatabaseConfig(**database_data)
        
        # Aplicar configuración específica del entorno
        self._apply_environment_config()
    
    def _apply_environment_config(self):
        """Aplica configuración específica según el entorno."""
        if self.environment.is_production():
            self.system.debug = False
            self.system.log_level = "WARNING"
            self.system.max_workers = os.cpu_count() or 4
        elif self.environment.is_development():
            self.system.debug = True
            self.system.log_level = "DEBUG"
            self.processing.cleanup_temp_files = False
        elif self.environment.is_testing():
            self.system.debug = True
            self.system.log_level = "DEBUG"
            self.processing.cleanup_temp_files = True
    
    def _setup_paths(self):
        """Configura y crea los directorios necesarios."""
        paths_to_create = [
            self.paths.documents_path,
            self.paths.processed_path,
            self.paths.vector_index_path,
            self.paths.logs_path,
            self.paths.temp_path
        ]
        
        for path in paths_to_create:
            os.makedirs(path, exist_ok=True)
    
    def _setup_logging(self):
        """Configura el sistema de logging."""
        import logging
        
        # Configurar nivel de logging
        log_level = getattr(logging, self.system.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(self.paths.logs_path, 'app.log')),
                logging.StreamHandler()
            ]
        )
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración por clave.
        
        Args:
            key: Clave en formato 'seccion.clave' (ej: 'system.debug')
            default: Valor por defecto si no se encuentra la clave
            
        Returns:
            Valor de la configuración o el valor por defecto.
        """
        try:
            section, config_key = key.split('.', 1)
            config_section = getattr(self, section, None)
            if config_section and hasattr(config_section, config_key):
                return getattr(config_section, config_key)
        except (ValueError, AttributeError):
            pass
        
        return default
    
    def update(self, key: str, value: Any):
        """
        Actualiza un valor de configuración.
        
        Args:
            key: Clave en formato 'seccion.clave'
            value: Nuevo valor
        """
        try:
            section, config_key = key.split('.', 1)
            config_section = getattr(self, section, None)
            if config_section and hasattr(config_section, config_key):
                setattr(config_section, config_key, value)
        except (ValueError, AttributeError):
            raise ValueError(f"Clave de configuración inválida: {key}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a un diccionario."""
        return {
            'paths': {
                'base_path': self.paths.base_path,
                'documents_path': self.paths.documents_path,
                'processed_path': self.paths.processed_path,
                'vector_index_path': self.paths.vector_index_path,
                'logs_path': self.paths.logs_path,
                'temp_path': self.paths.temp_path
            },
            'system': {
                'environment': self.system.environment.value,
                'debug': self.system.debug,
                'log_level': self.system.log_level,
                'max_workers': self.system.max_workers,
                'cpu_usage_limit': self.system.cpu_usage_limit,
                'memory_limit_gb': self.system.memory_limit_gb
            },
            'embedding': {
                'model_name': self.embedding.model_name,
                'model_path': self.embedding.model_path,
                'device': self.embedding.device,
                'batch_size': self.embedding.batch_size,
                'normalize_embeddings': self.embedding.normalize_embeddings
            },
            'processing': {
                'chunk_size': self.processing.chunk_size,
                'chunk_overlap': self.processing.chunk_overlap,
                'max_document_size_mb': self.processing.max_document_size_mb,
                'supported_formats': self.processing.supported_formats,
                'cleanup_temp_files': self.processing.cleanup_temp_files
            },
            'database': {
                'host': self.database.host,
                'port': self.database.port,
                'collection_name': self.database.collection_name,
                'distance': self.database.distance,
                'vector_size': self.database.vector_size,
                'recreate_collection': self.database.recreate_collection
            }
        }
    
    def save_to_file(self, file_path: Optional[str] = None):
        """
        Guarda la configuración actual a un archivo YAML.
        
        Args:
            file_path: Ruta del archivo (opcional, usa la ruta por defecto si no se especifica)
        """
        if file_path is None:
            file_path = os.path.join(
                os.path.dirname(__file__), 
                '..', '..', '..', '..', 'config', 'settings.yaml'
            )
        
        config_data = self.to_dict()
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

# Instancia global de configuración
_config_instance: Optional[BaseConfig] = None

def get_config() -> BaseConfig:
    """
    Obtiene la instancia global de configuración.
    
    Returns:
        Instancia de BaseConfig.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = BaseConfig()
    return _config_instance

def set_config(config: BaseConfig):
    """
    Establece la instancia global de configuración.
    
    Args:
        config: Instancia de BaseConfig.
    """
    global _config_instance
    _config_instance = config