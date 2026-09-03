"""
Pruebas unitarias para la API REST.

Este módulo contiene pruebas para los endpoints de la API.
"""

import pytest
import json
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Importar la aplicación
from core_engine.api.app import app

client = TestClient(app)

class TestAPIEndpoints:
    """Pruebas para los endpoints de la API."""
    
    def test_root_endpoint(self):
        """Prueba el endpoint raíz."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "status" in data
        assert "timestamp" in data
        assert "environment" in data
    
    def test_api_info_endpoint(self):
        """Prueba el endpoint de información de la API."""
        response = client.get("/api")
        assert response.status_code == 200
        
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "description" in data
        assert "endpoints" in data
        assert "features" in data
    
    def test_health_endpoint(self):
        """Prueba el endpoint de salud."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "system_info" in data
        assert "critical_paths" in data
        assert "version" in data
    
    def test_simple_health_endpoint(self):
        """Prueba el endpoint de salud simple."""
        response = client.get("/api/v1/health/simple")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] == "ok"
    
    def test_status_endpoint(self):
        """Prueba el endpoint de estado."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "system_info" in data
        assert "document_processing" in data
        assert "storage_info" in data
        assert "health_check" in data
    
    def test_document_status_endpoint(self):
        """Prueba el endpoint de estado de documentos."""
        response = client.get("/api/v1/status/documents")
        assert response.status_code == 200
        
        data = response.json()
        assert "documents" in data
        assert "processed" in data
        assert "timestamp" in data
        assert isinstance(data["documents"]["count"], int)
        assert isinstance(data["processed"]["count"], int)
        assert isinstance(data["documents"]["files"], list)
        assert isinstance(data["processed"]["files"], list)

class TestAPIErrorHandling:
    """Pruebas para el manejo de errores de la API."""
    
    def test_nonexistent_endpoint(self):
        """Prueba un endpoint inexistente."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_invalid_method(self):
        """Prueba un método HTTP inválido."""
        response = client.post("/api/v1/health")
        assert response.status_code == 405

if __name__ == "__main__":
    pytest.main([__file__, "-v"])