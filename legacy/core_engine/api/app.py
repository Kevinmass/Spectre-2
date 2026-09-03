#!/usr/bin/env python3
"""
Servidor API principal para el motor de búsqueda semántica de documentos.
Basado en FastAPI para alta performance y fácil desarrollo.
"""

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import uvicorn

# Importar rutas y controladores
from .routes import health, status
from ..config.settings import get_config

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Document Semantic Search API",
    description="Motor de búsqueda semántica local para documentos PDF",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración del sistema
config = get_config()

@app.on_event("startup")
async def startup_event():
    """Inicialización del sistema al arrancar."""
    logger.info("Iniciando Document Semantic Search API...")
    logger.info(f"Modo: {config.environment}")
    logger.info(f"Documentos: {config.documents_path}")
    logger.info(f"Índice vectorial: {config.vector_index_path}")

@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza del sistema al cerrar."""
    logger.info("Cerrando Document Semantic Search API...")

# Incluir rutas
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])

@app.get("/")
async def root():
    """Endpoint raíz con información básica del sistema."""
    return {
        "message": "Document Semantic Search API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "environment": config.environment
    }

@app.get("/api")
async def api_info():
    """Información general de la API."""
    return {
        "name": "Document Semantic Search API",
        "version": "1.0.0",
        "description": "Motor de búsqueda semántica local para documentos PDF",
        "endpoints": {
            "health": "/api/v1/health",
            "status": "/api/v1/status",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "features": [
            "Indexación automática de documentos",
            "Búsqueda semántica",
            "Procesamiento local",
            "Integración con IA externa"
        ]
    }

if __name__ == "__main__":
    # Configurar uvicorn para desarrollo
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )