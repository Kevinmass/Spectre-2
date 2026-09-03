"""
Registro de documentos para el sistema.

Este módulo gestiona el registro de documentos, permitiendo
llevar un control de los documentos procesados y su estado.
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import Lock

from ...config.settings import get_config

logger = logging.getLogger(__name__)

@dataclass
class DocumentRecord:
    """Registro de un documento en el sistema."""
    file_path: str
    file_name: str
    file_size: int
    file_hash: str
    status: str  # pending, processing, completed, failed
    created_at: str
    processed_at: Optional[str] = None
    error_message: Optional[str] = None
    chunks_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class DocumentRegistry:
    """Registro de documentos para el sistema."""
    
    def __init__(self, registry_file: Optional[str] = None):
        """
        Inicializa el registro de documentos.
        
        Args:
            registry_file: Ruta del archivo de registro (opcional).
        """
        self.config = get_config()
        self.registry_file = registry_file or os.path.join(
            self.config.paths.processed_path, 'document_registry.json'
        )
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
        
        self._documents: Dict[str, DocumentRecord] = {}
        self._lock = Lock()
        
        # Cargar registro existente
        self._load_registry()
    
    def add_document(self, file_path: str) -> str:
        """
        Agrega un nuevo documento al registro.
        
        Args:
            file_path: Ruta del archivo del documento.
            
        Returns:
            ID único del documento.
        """
        with self._lock:
            file_hash = self._calculate_file_hash(file_path)
            document_id = self._generate_document_id(file_path, file_hash)
            
            if document_id in self._documents:
                logger.warning(f"Documento ya registrado: {file_path}")
                return document_id
            
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            record = DocumentRecord(
                file_path=file_path,
                file_name=file_name,
                file_size=file_size,
                file_hash=file_hash,
                status="pending",
                created_at=datetime.now().isoformat()
            )
            
            self._documents[document_id] = record
            self._save_registry()
            
            logger.info(f"Documento registrado: {file_path} (ID: {document_id})")
            return document_id
    
    def update_status(self, document_id: str, status: str, 
                     processed_at: Optional[str] = None,
                     error_message: Optional[str] = None,
                     chunks_count: int = 0,
                     metadata: Optional[Dict[str, Any]] = None):
        """
        Actualiza el estado de un documento.
        
        Args:
            document_id: ID del documento.
            status: Nuevo estado.
            processed_at: Fecha de procesamiento.
            error_message: Mensaje de error (si aplica).
            chunks_count: Cantidad de chunks generados.
            metadata: Metadatos adicionales.
        """
        with self._lock:
            if document_id not in self._documents:
                logger.warning(f"Documento no encontrado en registro: {document_id}")
                return
            
            record = self._documents[document_id]
            record.status = status
            
            if processed_at:
                record.processed_at = processed_at
            
            if error_message:
                record.error_message = error_message
            
            if chunks_count > 0:
                record.chunks_count = chunks_count
            
            if metadata:
                record.metadata.update(metadata)
            
            self._save_registry()
            
            logger.info(f"Estado actualizado para documento {document_id}: {status}")
    
    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        """
        Obtiene un documento del registro.
        
        Args:
            document_id: ID del documento.
            
        Returns:
            Registro del documento o None si no existe.
        """
        with self._lock:
            return self._documents.get(document_id)
    
    def get_document_by_path(self, file_path: str) -> Optional[DocumentRecord]:
        """
        Obtiene un documento por su ruta de archivo.
        
        Args:
            file_path: Ruta del archivo.
            
        Returns:
            Registro del documento o None si no existe.
        """
        with self._lock:
            file_hash = self._calculate_file_hash(file_path)
            document_id = self._generate_document_id(file_path, file_hash)
            return self._documents.get(document_id)
    
    def get_all_documents(self) -> List[DocumentRecord]:
        """
        Obtiene todos los documentos del registro.
        
        Returns:
            Lista de todos los documentos registrados.
        """
        with self._lock:
            return list(self._documents.values())
    
    def get_documents_by_status(self, status: str) -> List[DocumentRecord]:
        """
        Obtiene documentos por estado.
        
        Args:
            status: Estado de los documentos.
            
        Returns:
            Lista de documentos con el estado especificado.
        """
        with self._lock:
            return [doc for doc in self._documents.values() if doc.status == status]
    
    def get_pending_documents(self) -> List[DocumentRecord]:
        """Obtiene documentos pendientes de procesamiento."""
        return self.get_documents_by_status("pending")
    
    def get_completed_documents(self) -> List[DocumentRecord]:
        """Obtiene documentos completados."""
        return self.get_documents_by_status("completed")
    
    def get_failed_documents(self) -> List[DocumentRecord]:
        """Obtiene documentos fallidos."""
        return self.get_documents_by_status("failed")
    
    def remove_document(self, document_id: str):
        """
        Elimina un documento del registro.
        
        Args:
            document_id: ID del documento a eliminar.
        """
        with self._lock:
            if document_id in self._documents:
                del self._documents[document_id]
                self._save_registry()
                logger.info(f"Documento eliminado del registro: {document_id}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del registro.
        
        Returns:
            Diccionario con estadísticas del registro.
        """
        with self._lock:
            total = len(self._documents)
            pending = len(self.get_pending_documents())
            completed = len(self.get_completed_documents())
            failed = len(self.get_failed_documents())
            
            total_size = sum(doc.file_size for doc in self._documents.values())
            total_chunks = sum(doc.chunks_count for doc in self._documents.values())
            
            return {
                "total_documents": total,
                "pending": pending,
                "completed": completed,
                "failed": failed,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_chunks": total_chunks,
                "registry_file": self.registry_file,
                "last_updated": datetime.now().isoformat()
            }
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calcula el hash SHA-256 de un archivo."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculando hash para {file_path}: {e}")
            return ""
    
    def _generate_document_id(self, file_path: str, file_hash: str) -> str:
        """Genera un ID único para el documento."""
        combined = f"{file_path}_{file_hash}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _load_registry(self):
        """Carga el registro desde el archivo."""
        try:
            if os.path.exists(self.registry_file):
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for doc_data in data:
                    record = DocumentRecord(**doc_data)
                    self._documents[record.file_hash] = record
                
                logger.info(f"Registro cargado: {len(self._documents)} documentos")
            else:
                logger.info("No se encontró archivo de registro, iniciando con registro vacío")
                
        except Exception as e:
            logger.error(f"Error cargando registro: {e}")
            self._documents = {}
    
    def _save_registry(self):
        """Guarda el registro en el archivo."""
        try:
            data = [asdict(record) for record in self._documents.values()]
            
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error guardando registro: {e}")

# Instancia global del registro
_document_registry: Optional[DocumentRegistry] = None

def get_document_registry() -> DocumentRegistry:
    """
    Obtiene la instancia global del registro de documentos.
    
    Returns:
        Instancia de DocumentRegistry.
    """
    global _document_registry
    if _document_registry is None:
        _document_registry = DocumentRegistry()
    return _document_registry

def set_document_registry(registry: DocumentRegistry):
    """
    Establece la instancia global del registro de documentos.
    
    Args:
        registry: Instancia de DocumentRegistry.
    """
    global _document_registry
    _document_registry = registry