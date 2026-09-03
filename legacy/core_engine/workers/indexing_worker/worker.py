"""
Worker de indexación para procesamiento de documentos.

Este módulo implementa el worker que se encarga de procesar documentos
y agregarlos a la cola de tareas.
"""

import os
import logging
import threading
import time
from typing import Optional, Callable

from ...config.settings import get_config
from ...indexing.file_watcher import FileMonitor
from ...indexing.document_registry import get_document_registry
from ...workers.task_queue import get_task_queue, TaskPriority

logger = logging.getLogger(__name__)

class IndexingWorker:
    """Worker para indexación de documentos."""
    
    def __init__(self):
        """Inicializa el worker de indexación."""
        self.config = get_config()
        self.file_monitor = None
        self.task_queue = get_task_queue()
        self.is_running = False
        self.worker_thread = None
        
        # Callbacks
        self.on_document_detected = None
        self.on_document_processed = None
    
    def start(self):
        """Inicia el worker de indexación."""
        if self.is_running:
            logger.warning("El worker de indexación ya está en ejecución")
            return
        
        self.is_running = True
        self.task_queue.start()
        
        # Iniciar monitor de archivos
        self.file_monitor = FileMonitor()
        self.file_monitor.add_callback(self._on_new_document)
        
        # Iniciar thread del worker
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        logger.info("Worker de indexación iniciado")
    
    def stop(self):
        """Detiene el worker de indexación."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Detener monitor de archivos
        if self.file_monitor:
            self.file_monitor.stop()
        
        # Detener cola de tareas
        self.task_queue.stop()
        
        # Esperar a que termine el thread
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        
        logger.info("Worker de indexación detenido")
    
    def add_callback(self, callback_type: str, callback: Callable):
        """
        Agrega un callback para eventos específicos.
        
        Args:
            callback_type: Tipo de callback ('document_detected', 'document_processed')
            callback: Función a llamar
        """
        if callback_type == 'document_detected':
            self.on_document_detected = callback
        elif callback_type == 'document_processed':
            self.on_document_processed = callback
    
    def _worker_loop(self):
        """Bucle principal del worker."""
        logger.info("Worker de indexación en ejecución")
        
        while self.is_running:
            try:
                # Verificar documentos pendientes
                self._check_pending_documents()
                
                # Dormir un tiempo antes de la próxima verificación
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error en el worker de indexación: {e}")
                time.sleep(5)
        
        logger.info("Worker de indexación detenido")
    
    def _on_new_document(self, file_path: str):
        """
        Maneja la detección de un nuevo documento.
        
        Args:
            file_path: Ruta del archivo detectado.
        """
        logger.info(f"Nuevo documento detectado: {file_path}")
        
        # Llamar al callback si existe
        if self.on_document_detected:
            try:
                self.on_document_detected(file_path)
            except Exception as e:
                logger.error(f"Error en callback de documento detectado: {e}")
        
        # Agregar a la cola de tareas
        self._add_document_to_queue(file_path)
    
    def _add_document_to_queue(self, file_path: str):
        """
        Agrega un documento a la cola de tareas para su procesamiento.
        
        Args:
            file_path: Ruta del archivo a procesar.
        """
        try:
            # Verificar si el documento ya está registrado
            registry = get_document_registry()
            existing_record = registry.get_document_by_path(file_path)
            
            if existing_record:
                logger.info(f"Documento ya registrado: {file_path}")
                return
            
            # Agregar a la cola de tareas
            task_id = self.task_queue.add_task(
                task_type="process_document",
                payload={
                    "file_path": file_path,
                    "priority": "high"
                },
                priority=TaskPriority.HIGH
            )
            
            logger.info(f"Documento agregado a la cola de tareas: {file_path} (Tarea: {task_id})")
            
        except Exception as e:
            logger.error(f"Error agregando documento a la cola: {file_path} - {e}")
    
    def _check_pending_documents(self):
        """Verifica y procesa documentos pendientes."""
        try:
            registry = get_document_registry()
            pending_docs = registry.get_pending_documents()
            
            if not pending_docs:
                return
            
            logger.info(f"Encontrados {len(pending_docs)} documentos pendientes")
            
            for doc in pending_docs:
                # Verificar si el archivo aún existe
                if not os.path.exists(doc.file_path):
                    logger.warning(f"Documento no encontrado: {doc.file_path}")
                    continue
                
                # Verificar si ya está en proceso
                task_queue = get_task_queue()
                existing_tasks = task_queue.get_pending_tasks()
                
                # Buscar si ya hay una tarea para este documento
                file_path = doc.file_path
                task_exists = any(
                    task.payload.get("file_path") == file_path 
                    for task in existing_tasks
                )
                
                if not task_exists:
                    self._add_document_to_queue(file_path)
                    
        except Exception as e:
            logger.error(f"Error verificando documentos pendientes: {e}")
    
    def get_status(self) -> dict:
        """Obtiene el estado del worker."""
        try:
            registry = get_document_registry()
            task_queue = get_task_queue()
            
            return {
                "is_running": self.is_running,
                "file_monitor_path": self.file_monitor.get_monitored_path() if self.file_monitor else None,
                "processed_files_count": self.file_monitor.get_processed_files_count() if self.file_monitor else 0,
                "document_registry_stats": registry.get_statistics(),
                "task_queue_metrics": task_queue.get_metrics(),
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estado del worker: {e}")
            return {
                "is_running": self.is_running,
                "error": str(e),
                "timestamp": time.time()
            }

# Instancia global del worker de indexación
_indexing_worker: Optional[IndexingWorker] = None

def get_indexing_worker() -> IndexingWorker:
    """
    Obtiene la instancia global del worker de indexación.
    
    Returns:
        Instancia de IndexingWorker.
    """
    global _indexing_worker
    if _indexing_worker is None:
        _indexing_worker = IndexingWorker()
    return _indexing_worker

def set_indexing_worker(worker: IndexingWorker):
    """
    Establece la instancia global del worker de indexación.
    
    Args:
        worker: Instancia de IndexingWorker.
    """
    global _indexing_worker
    _indexing_worker = worker