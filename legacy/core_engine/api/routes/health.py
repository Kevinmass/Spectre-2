"""
Rutas para el endpoint de salud del sistema.

Este módulo contiene el endpoint GET /health que verifica el estado del sistema.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import psutil
import os
from typing import Dict, Any

from ...config.settings import get_config

router = APIRouter()

@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """
    Verifica el estado de salud del sistema.
    
    Returns:
        Dict[str, Any]: Información sobre el estado del sistema.
    """
    try:
        # Obtener información del sistema
        config = get_config()
        
        # Verificar espacio en disco
        disk_usage = psutil.disk_usage(config.documents_path)
        disk_free_gb = disk_usage.free / (1024**3)  # Convertir a GB
        
        # Verificar memoria disponible
        memory = psutil.virtual_memory()
        memory_available_gb = memory.available / (1024**3)  # Convertir a GB
        
        # Verificar si las carpetas críticas existen
        critical_paths = {
            "documents": os.path.exists(config.documents_path),
            "processed": os.path.exists(config.processed_path),
            "vector_index": os.path.exists(config.vector_index_path)
        }
        
        # Estado general del sistema
        system_healthy = all(critical_paths.values()) and disk_free_gb > 1.0 and memory_available_gb > 0.5
        
        health_data = {
            "status": "healthy" if system_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "environment": config.environment,
                "documents_path": config.documents_path,
                "processed_path": config.processed_path,
                "vector_index_path": config.vector_index_path,
                "disk_free_gb": round(disk_free_gb, 2),
                "memory_available_gb": round(memory_available_gb, 2),
                "cpu_count": psutil.cpu_count()
            },
            "critical_paths": critical_paths,
            "version": "1.0.0"
        }
        
        if not system_healthy:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Sistema con problemas de salud",
                    "health_data": health_data
                }
            )
        
        return health_data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error al verificar la salud del sistema",
                "error": str(e)
            }
        )

@router.get("/health/simple")
async def simple_health_check():
    """
    Endpoint simple de salud para load balancers y monitoreo básico.
    
    Returns:
        Dict[str, str]: Estado simple del sistema.
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat()}