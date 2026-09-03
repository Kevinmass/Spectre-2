"""
Monitor de archivos para detectar nuevos documentos PDF.

Este módulo implementa un observador de archivos que detecta automáticamente
cuando se agregan nuevos documentos PDF a la carpeta de documentos.
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, Callable, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ...config.settings import get_config

logger = logging.getLogger(__name__)

class DocumentFileHandler(FileSystemEventHandler):
    """Manejador de eventos de archivos para documentos PDF."""
    
    def __init__(self, callback: Optional[Callable] = None):
        """
        Inicializa el manejador de eventos.
        
        Args:
            callback: Función a llamar cuando se detecta un nuevo documento.
        """
        self.callback = callback
        self.processed_files: Set[str] = set()
    
    def on_created(self, event):
        """Maneja el evento de creación de archivo."""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if self._is_pdf_file(file_path):
            logger.info(f"Nuevo documento detectado: {file_path}")
            self._process_new_document(file_path)
    
    def on_moved(self, event):
        """Maneja el evento de movimiento de archivo."""
        if event.is_directory:
            return
        
        file_path = event.dest_path
        if self._is_pdf_file(file_path):
            logger.info(f"Documento movido detectado: {file_path}")
            self._process_new_document(file_path)
    
    def _is_pdf_file(self, file_path: str) -> bool:
        """Verifica si el archivo es un PDF."""
        return file_path.lower().endswith('.pdf')
    
    def _process_new_document(self, file_path: str):
        """Procesa un nuevo documento detectado."""
        # Evitar procesar el mismo archivo múltiples veces
        if file_path in self.processed_files:
            return
        
        try:
            # Verificar que el archivo exista y tenga contenido
            if not os.path.exists(file_path):
                return
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.warning(f"Documento vacío detectado: {file_path}")
                return
            
            # Marcar como procesado
            self.processed_files.add(file_path)
            
            # Llamar al callback si existe
            if self.callback:
                self.callback(file_path)
            else:
                logger.info(f"Documento listo para procesamiento: {file_path}")
                
        except Exception as e:
            logger.error(f"Error procesando documento {file_path}: {e}")

class FileMonitor:
    """Monitor de archivos para documentos PDF."""
    
    def __init__(self, documents_path: Optional[str] = None):
        """
        Inicializa el monitor de archivos.
        
        Args:
            documents_path: Ruta de la carpeta de documentos (opcional).
        """
        self.config = get_config()
        self.documents_path = documents_path or self.config.paths.documents_path
        self.observer = Observer()
        self.handler = DocumentFileHandler()
        self.is_running = False
        
        # Crear la carpeta si no existe
        os.makedirs(self.documents_path, exist_ok=True)
    
    def start(self, callback: Optional[Callable] = None):
        """
        Inicia el monitoreo de archivos.
        
        Args:
            callback: Función a llamar cuando se detecta un nuevo documento.
        """
        if self.is_running:
            logger.warning("El monitor de archivos ya está en ejecución")
            return
        
        if callback:
            self.handler.callback = callback
        
        self.observer.schedule(
            self.handler, 
            self.documents_path, 
            recursive=False
        )
        self.observer.start()
        self.is_running = True
        
        logger.info(f"Monitor de archivos iniciado en: {self.documents_path}")
        
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Detiene el monitoreo de archivos."""
        if not self.is_running:
            return
        
        self.observer.stop()
        self.observer.join()
        self.is_running = False
        
        logger.info("Monitor de archivos detenido")
    
    def add_callback(self, callback: Callable):
        """
        Agrega un callback para ser llamado cuando se detecte un nuevo documento.
        
        Args:
            callback: Función a llamar cuando se detecta un nuevo documento.
        """
        self.handler.callback = callback
    
    def get_monitored_path(self) -> str:
        """Obtiene la ruta que está siendo monitoreada."""
        return self.documents_path
    
    def get_processed_files_count(self) -> int:
        """Obtiene la cantidad de archivos procesados."""
        return len(self.handler.processed_files)

def start_file_monitor(documents_path: Optional[str] = None, callback: Optional[Callable] = None):
    """
    Función auxiliar para iniciar el monitor de archivos.
    
    Args:
        documents_path: Ruta de la carpeta de documentos.
        callback: Función a llamar cuando se detecte un nuevo documento.
    """
    monitor = FileMonitor(documents_path)
    monitor.start(callback)
    return monitor

# Ejemplo de uso:
# def on_new_document(file_path):
#     print(f"Nuevo documento detectado: {file_path}")
#     # Aquí se podría agregar el documento a la cola de procesamiento
#
# monitor = start_file_monitor(callback=on_new_document)