"""
Controlador para el endpoint de salud del sistema.

Contiene la lógica de negocio para verificar el estado del sistema.
"""

from datetime import datetime
from typing import Dict, Any
import psutil
import os

from ...config.settings import get_config

class HealthController:
    """Controlador para operaciones de salud del sistema."""
    
    def __init__(self):
        self.config = get_config()
    
    def check_health(self) -> Dict[str, Any]:
        """
        Verifica el estado de salud del sistema.
        
        Returns:
            Dict[str, Any]: Información sobre el estado del sistema.
        """
        try:
            # Verificar espacio en disco
            disk_usage = psutil.disk_usage(self.config.documents_path)
            disk_free_gb = disk_usage.free / (1024**3)  # Convertir a GB
            
            # Verificar memoria disponible
            memory = psutil.virtual_memory()
            memory_available_gb = memory.available / (1024**3)  # Convertir a GB
            
            # Verificar si las carpetas críticas existen
            critical_paths = {
                "documents": os.path.exists(self.config.documents_path),
                "processed": os.path.exists(self.config.processed_path),
                "vector_index": os.path.exists(self.config.vector_index_path)
            }
            
            # Estado general del sistema
            system_healthy = all(critical_paths.values()) and disk_free_gb > 1.0 and memory_available_gb > 0.5
            
            health_data = {
                "status": "healthy" if system_healthy else "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "system_info": {
                    "environment": self.config.environment,
                    "documents_path": self.config.documents_path,
                    "processed_path": self.config.processed_path,
                    "vector_index_path": self.config.vector_index_path,
                    "disk_free_gb": round(disk_free_gb, 2),
                    "memory_available_gb": round(memory_available_gb, 2),
                    "cpu_count": psutil.cpu_count()
                },
                "critical_paths": critical_paths,
                "version": "1.0.0"
            }
            
            return health_data
            
        except Exception as e:
            raise Exception(f"Error al verificar la salud del sistema: {str(e)}")
    
    def check_simple_health(self) -> Dict[str, str]:
        """
        Verifica el estado simple del sistema para monitoreo básico.
        
        Returns:
            Dict[str, str]: Estado simple del sistema.
        """
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        }
    
    def get_system_resources(self) -> Dict[str, Any]:
        """
        Obtiene información detallada sobre los recursos del sistema.
        
        Returns:
            Dict[str, Any]: Información sobre recursos del sistema.
        """
        try:
            # Información de CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Información de memoria
            memory = psutil.virtual_memory()
            memory_info = {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percentage": memory.percent
            }
            
            # Información de disco
            disk_usage = psutil.disk_usage(self.config.documents_path)
            disk_info = {
                "total_gb": round(disk_usage.total / (1024**3), 2),
                "free_gb": round(disk_usage.free / (1024**3), 2),
                "used_gb": round(disk_usage.used / (1024**3), 2),
                "percentage": round((disk_usage.used / disk_usage.total) * 100, 2)
            }
            
            return {
                "cpu": {
                    "count": cpu_count,
                    "usage_percent": cpu_percent
                },
                "memory": memory_info,
                "disk": disk_info,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            raise Exception(f"Error al obtener información de recursos: {str(e)}")