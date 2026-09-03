"""
Pruebas unitarias para el sistema de monitoreo de archivos.

Este módulo contiene pruebas para el file watcher de documentos.
"""

import pytest
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from core_engine.indexing.file_watcher import FileMonitor, DocumentFileHandler

class TestDocumentFileHandler:
    """Pruebas para el manejador de eventos de archivos."""
    
    def test_init(self):
        """Prueba la inicialización del manejador."""
        handler = DocumentFileHandler()
        
        assert handler.callback is None
        assert handler.processed_files == set()
    
    def test_init_with_callback(self):
        """Prueba la inicialización con callback."""
        callback = Mock()
        handler = DocumentFileHandler(callback)
        
        assert handler.callback == callback
        assert handler.processed_files == set()
    
    def test_is_pdf_file(self):
        """Prueba la detección de archivos PDF."""
        handler = DocumentFileHandler()
        
        assert handler._is_pdf_file("test.pdf") is True
        assert handler._is_pdf_file("test.PDF") is True
        assert handler._is_pdf_file("test.txt") is False
        assert handler._is_pdf_file("test.doc") is False
        assert handler._is_pdf_file("test") is False
    
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_process_new_document(self, mock_getsize, mock_exists):
        """Prueba el procesamiento de un nuevo documento."""
        handler = DocumentFileHandler()
        callback = Mock()
        handler.callback = callback
        
        file_path = "/test/document.pdf"
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        
        handler._process_new_document(file_path)
        
        assert file_path in handler.processed_files
        callback.assert_called_once_with(file_path)
    
    @patch('os.path.exists')
    def test_process_nonexistent_file(self, mock_exists):
        """Prueba el procesamiento de un archivo inexistente."""
        handler = DocumentFileHandler()
        callback = Mock()
        handler.callback = callback
        
        file_path = "/test/nonexistent.pdf"
        mock_exists.return_value = False
        
        handler._process_new_document(file_path)
        
        assert file_path not in handler.processed_files
        callback.assert_not_called()
    
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_process_empty_file(self, mock_getsize, mock_exists):
        """Prueba el procesamiento de un archivo vacío."""
        handler = DocumentFileHandler()
        callback = Mock()
        handler.callback = callback
        
        file_path = "/test/empty.pdf"
        mock_exists.return_value = True
        mock_getsize.return_value = 0
        
        handler._process_new_document(file_path)
        
        assert file_path not in handler.processed_files
        callback.assert_not_called()
    
    def test_process_duplicate_file(self):
        """Prueba el procesamiento de un archivo duplicado."""
        handler = DocumentFileHandler()
        callback = Mock()
        handler.callback = callback
        
        file_path = "/test/document.pdf"
        handler.processed_files.add(file_path)
        
        handler._process_new_document(file_path)
        
        # No debe llamar al callback de nuevo
        callback.assert_not_called()

class TestFileMonitor:
    """Pruebas para el monitor de archivos."""
    
    def test_init(self):
        """Prueba la inicialización del monitor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            
            assert monitor.documents_path == temp_dir
            assert monitor.observer is not None
            assert monitor.handler is not None
            assert monitor.is_running is False
    
    @patch('os.makedirs')
    def test_init_creates_directory(self, mock_makedirs):
        """Prueba que el monitor crea el directorio si no existe."""
        monitor = FileMonitor("/test/path")
        
        mock_makedirs.assert_called_once_with("/test/path", exist_ok=True)
    
    @patch('watchdog.observers.Observer.start')
    @patch('watchdog.observers.Observer.schedule')
    def test_start(self, mock_schedule, mock_start):
        """Prueba el inicio del monitor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            callback = Mock()
            
            monitor.start(callback)
            
            assert monitor.is_running is True
            mock_schedule.assert_called_once()
            mock_start.assert_called_once()
            assert monitor.handler.callback == callback
    
    def test_start_already_running(self, caplog):
        """Prueba el inicio cuando ya está en ejecución."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            monitor.is_running = True
            
            monitor.start()
            
            assert "ya está en ejecución" in caplog.text
    
    @patch('watchdog.observers.Observer.stop')
    @patch('watchdog.observers.Observer.join')
    def test_stop(self, mock_join, mock_stop):
        """Prueba la detención del monitor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            monitor.is_running = True
            
            monitor.stop()
            
            assert monitor.is_running is False
            mock_stop.assert_called_once()
            mock_join.assert_called_once()
    
    def test_stop_not_running(self):
        """Prueba la detención cuando no está en ejecución."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            monitor.is_running = False
            
            # No debe hacer nada
            monitor.stop()
    
    def test_add_callback(self):
        """Prueba la adición de un callback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            callback = Mock()
            
            monitor.add_callback(callback)
            
            assert monitor.handler.callback == callback
    
    def test_get_monitored_path(self):
        """Prueba la obtención de la ruta monitoreada."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            
            assert monitor.get_monitored_path() == temp_dir
    
    def test_get_processed_files_count(self):
        """Prueba la obtención del conteo de archivos procesados."""
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = FileMonitor(temp_dir)
            monitor.handler.processed_files.add("/test/file1.pdf")
            monitor.handler.processed_files.add("/test/file2.pdf")
            
            assert monitor.get_processed_files_count() == 2

class TestFileMonitorIntegration:
    """Pruebas de integración para el monitor de archivos."""
    
    def test_monitor_creates_directories(self):
        """Prueba que el monitor crea los directorios necesarios."""
        with tempfile.TemporaryDirectory() as temp_dir:
            documents_path = os.path.join(temp_dir, "documents")
            
            # El directorio no existe inicialmente
            assert not os.path.exists(documents_path)
            
            monitor = FileMonitor(documents_path)
            
            # El directorio debe existir después de la inicialización
            assert os.path.exists(documents_path)
    
    def test_monitor_with_default_path(self):
        """Prueba el monitor con la ruta por defecto."""
        from core_engine.config.settings import get_config
        
        config = get_config()
        monitor = FileMonitor()
        
        assert monitor.documents_path == config.paths.documents_path

if __name__ == "__main__":
    pytest.main([__file__, "-v"])