"""
Rutas para el endpoint de estado del sistema.

Este módulo contiene el endpoint GET /status que muestra el estado de procesamiento.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import os
from typing import Dict, Any, List
from pathlib import Path

from ...config.settings import get_config

router = APIRouter()

@router.get("/status", response_model=Dict[str, Any])
async def get_system_status():
    """
    Obtiene el estado actual del sistema de procesamiento.
    
    Returns:
        Dict[str, Any]: Información detallada sobre el estado del sistema.
    """
    try:
        config = get_config()
        
        # Contar documentos en cada estado
        documents_count = _count_documents_in_directory(config.documents_path)
        processed_count = _count_documents_in_directory(config.processed_path)
        
        # Obtener información de archivos
        documents_info = _get_directory_info(config.documents_path)
        processed_info = _get_directory_info(config.processed_path)
        vector_index_info = _get_directory_info(config.vector_index_path)
        
        # Estado general
        status_data = {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "environment": config.environment,
                "version": "1.0.0"
            },
            "document_processing": {
                "total_documents": documents_count,
                "processed_documents": processed_count,
                "pending_documents": max(0, documents_count - processed_count),
                "processing_rate": _calculate_processing_rate(documents_count, processed_count)
            },
            "storage_info": {
                "documents": documents_info,
                "processed": processed_info,
                "vector_index": vector_index_info
            },
            "health_check": {
                "disk_space_ok": documents_info["free_space_gb"] > 1.0,
                "memory_ok": True,  # Se podría implementar verificación de memoria
                "paths_accessible": all([
                    os.path.exists(config.documents_path),
                    os.path.exists(config.processed_path),
                    os.path.exists(config.vector_index_path)
                ])
            }
        }
        
        return status_data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error al obtener el estado del sistema",
                "error": str(e)
            }
        )

@router.get("/status/documents")
async def get_document_status():
    """
    Obtiene información específica sobre los documentos.
    
    Returns:
        Dict[str, Any]: Información sobre los documentos en el sistema.
    """
    try:
        config = get_config()
        
        documents = _list_documents(config.documents_path)
        processed = _list_documents(config.processed_path)
        
        return {
            "documents": {
                "count": len(documents),
                "files": documents
            },
            "processed": {
                "count": len(processed),
                "files": processed
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error al obtener el estado de documentos",
                "error": str(e)
            }
        )

def _count_documents_in_directory(directory_path: str) -> int:
    """Cuenta la cantidad de documentos en un directorio."""
    if not os.path.exists(directory_path):
        return 0
    
    count = 0
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                count += 1
    return count

def _get_directory_info(directory_path: str) -> Dict[str, Any]:
    """Obtiene información sobre un directorio."""
    info = {
        "path": directory_path,
        "exists": os.path.exists(directory_path),
        "file_count": 0,
        "total_size_mb": 0,
        "free_space_gb": 0
    }
    
    if os.path.exists(directory_path):
        # Contar archivos y calcular tamaño
        total_size = 0
        file_count = 0
        
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    total_size += os.path.getsize(file_path)
                    file_count += 1
                except OSError:
                    pass  # Ignorar archivos que no se puedan acceder
        
        info["file_count"] = file_count
        info["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        # Obtener espacio libre
        import shutil
        try:
            free_bytes = shutil.disk_usage(directory_path).free
            info["free_space_gb"] = round(free_bytes / (1024**3), 2)
        except OSError:
            info["free_space_gb"] = 0
    
    return info

def _list_documents(directory_path: str) -> List[Dict[str, Any]]:
    """Lista los documentos en un directorio con información detallada."""
    documents = []
    
    if not os.path.exists(directory_path):
        return documents
    
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                file_path = os.path.join(root, file)
                try:
                    stat = os.stat(file_path)
                    documents.append({
                        "name": file,
                        "path": file_path,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except OSError:
                    pass  # Ignorar archivos que no se puedan acceder
    
    return sorted(documents, key=lambda x: x["modified"], reverse=True)

def _calculate_processing_rate(total: int, processed: int) -> float:
    """Calcula el porcentaje de documentos procesados."""
    if total == 0:
        return 0.0
    return round((processed / total) * 100, 2)