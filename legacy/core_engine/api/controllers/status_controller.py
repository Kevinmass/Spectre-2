"""
Controlador para el endpoint de estado del sistema.

Contiene la lógica de negocio para obtener el estado de procesamiento.
"""

from datetime import datetime
from typing import Dict, Any, List
import os
import shutil
from pathlib import Path

from ...config.settings import get_config

class StatusController:
    """Controlador para operaciones de estado del sistema."""
    
    def __init__(self):
        self.config = get_config()
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual del sistema de procesamiento.
        
        Returns:
            Dict[str, Any]: Información detallada sobre el estado del sistema.
        """
        try:
            # Contar documentos en cada estado
            documents_count = self._count_documents_in_directory(self.config.documents_path)
            processed_count = self._count_documents_in_directory(self.config.processed_path)
            
            # Obtener información de archivos
            documents_info = self._get_directory_info(self.config.documents_path)
            processed_info = self._get_directory_info(self.config.processed_path)
            vector_index_info = self._get_directory_info(self.config.vector_index_path)
            
            # Estado general
            status_data = {
                "status": "operational",
                "timestamp": datetime.now().isoformat(),
                "system_info": {
                    "environment": self.config.environment,
                    "version": "1.0.0"
                },
                "document_processing": {
                    "total_documents": documents_count,
                    "processed_documents": processed_count,
                    "pending_documents": max(0, documents_count - processed_count),
                    "processing_rate": self._calculate_processing_rate(documents_count, processed_count)
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
                        os.path.exists(self.config.documents_path),
                        os.path.exists(self.config.processed_path),
                        os.path.exists(self.config.vector_index_path)
                    ])
                }
            }
            
            return status_data
            
        except Exception as e:
            raise Exception(f"Error al obtener el estado del sistema: {str(e)}")
    
    def get_document_status(self) -> Dict[str, Any]:
        """
        Obtiene información específica sobre los documentos.
        
        Returns:
            Dict[str, Any]: Información sobre los documentos en el sistema.
        """
        try:
            documents = self._list_documents(self.config.documents_path)
            processed = self._list_documents(self.config.processed_path)
            
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
            raise Exception(f"Error al obtener el estado de documentos: {str(e)}")
    
    def get_processing_statistics(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas detalladas sobre el procesamiento de documentos.
        
        Returns:
            Dict[str, Any]: Estadísticas de procesamiento.
        """
        try:
            documents_count = self._count_documents_in_directory(self.config.documents_path)
            processed_count = self._count_documents_in_directory(self.config.processed_path)
            
            # Calcular tasas
            processing_rate = self._calculate_processing_rate(documents_count, processed_count)
            
            # Obtener información de tamaño
            documents_size = self._get_directory_size(self.config.documents_path)
            processed_size = self._get_directory_size(self.config.processed_path)
            
            return {
                "total_documents": documents_count,
                "processed_documents": processed_count,
                "pending_documents": max(0, documents_count - processed_count),
                "processing_rate_percent": processing_rate,
                "storage_usage": {
                    "documents_mb": round(documents_size / (1024 * 1024), 2),
                    "processed_mb": round(processed_size / (1024 * 1024), 2),
                    "total_mb": round((documents_size + processed_size) / (1024 * 1024), 2)
                },
                "efficiency": {
                    "compression_ratio": self._calculate_compression_ratio(documents_size, processed_size) if documents_size > 0 else 0,
                    "average_processing_time": self._estimate_processing_time(documents_count)
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            raise Exception(f"Error al obtener estadísticas de procesamiento: {str(e)}")
    
    def _count_documents_in_directory(self, directory_path: str) -> int:
        """Cuenta la cantidad de documentos en un directorio."""
        if not os.path.exists(directory_path):
            return 0
        
        count = 0
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    count += 1
        return count
    
    def _get_directory_info(self, directory_path: str) -> Dict[str, Any]:
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
            try:
                free_bytes = shutil.disk_usage(directory_path).free
                info["free_space_gb"] = round(free_bytes / (1024**3), 2)
            except OSError:
                info["free_space_gb"] = 0
        
        return info
    
    def _list_documents(self, directory_path: str) -> List[Dict[str, Any]]:
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
    
    def _calculate_processing_rate(self, total: int, processed: int) -> float:
        """Calcula el porcentaje de documentos procesados."""
        if total == 0:
            return 0.0
        return round((processed / total) * 100, 2)
    
    def _get_directory_size(self, directory_path: str) -> int:
        """Obtiene el tamaño total de un directorio en bytes."""
        total_size = 0
        
        if not os.path.exists(directory_path):
            return total_size
        
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    total_size += os.path.getsize(file_path)
                except OSError:
                    pass  # Ignorar archivos que no se puedan acceder
        
        return total_size
    
    def _calculate_compression_ratio(self, original_size: int, compressed_size: int) -> float:
        """Calcula la razón de compresión."""
        if original_size == 0:
            return 0.0
        return round((1 - compressed_size / original_size) * 100, 2)
    
    def _estimate_processing_time(self, document_count: int) -> str:
        """Estima el tiempo de procesamiento basado en la cantidad de documentos."""
        if document_count == 0:
            return "No hay documentos para procesar"
        elif document_count <= 10:
            return "Menos de 1 hora"
        elif document_count <= 50:
            return "1-3 horas"
        elif document_count <= 100:
            return "3-6 horas"
        else:
            return "Más de 6 horas"