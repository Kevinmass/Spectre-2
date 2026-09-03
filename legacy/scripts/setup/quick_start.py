#!/usr/bin/env python3
"""
Script de inicio rápido para Document Semantic Search.

Este script permite iniciar el sistema rápidamente para pruebas y desarrollo.
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_requirements():
    """Verifica que las dependencias estén instaladas."""
    try:
        import fastapi
        import uvicorn
        import watchdog
        logger.info("✓ Dependencias principales instaladas")
        return True
    except ImportError as e:
        logger.error(f"✗ Falta dependencia: {e}")
        logger.info("Instala las dependencias con: pip install -r requirements.txt")
        return False

def create_test_document():
    """Crea un documento PDF de prueba."""
    try:
        from fpdf import FPDF
        
        # Crear directorio de documentos si no existe
        documents_dir = Path("data/documents")
        documents_dir.mkdir(parents=True, exist_ok=True)
        
        # Crear documento de prueba
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        content = """
        Documento de Prueba para Document Semantic Search
        
        Este es un documento PDF de prueba creado automáticamente
        para validar el funcionamiento del sistema.
        
        Contenido de prueba:
        - Búsqueda semántica
        - Procesamiento de documentos
        - Indexación automática
        - Análisis con IA
        
        Este documento debe ser detectado automáticamente por el
        sistema de monitoreo de archivos y procesado.
        """
        
        pdf.multi_cell(0, 10, content)
        
        test_file = documents_dir / "documento_prueba.pdf"
        pdf.output(str(test_file))
        
        logger.info(f"✓ Documento de prueba creado: {test_file}")
        return True
        
    except ImportError:
        logger.warning("✗ No se puede crear documento de prueba (falta fpdf)")
        return False
    except Exception as e:
        logger.error(f"✗ Error creando documento de prueba: {e}")
        return False

def start_api_server():
    """Inicia el servidor API."""
    try:
        logger.info("🚀 Iniciando servidor API...")
        logger.info("Accede a http://localhost:8000/docs para ver la documentación")
        
        # Cambiar al directorio del proyecto
        os.chdir(Path(__file__).parent.parent.parent.parent)
        
        # Iniciar el servidor
        subprocess.run([
            sys.executable, "-m", "core_engine.api.app"
        ], check=True)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Error iniciando servidor: {e}")
        return False
    except KeyboardInterrupt:
        logger.info("✓ Servidor detenido")
        return True

def start_with_docker():
    """Inicia el sistema con Docker."""
    try:
        logger.info("🐳 Iniciando con Docker...")
        
        # Cambiar al directorio de Docker
        docker_dir = Path(__file__).parent.parent.parent / "docker"
        os.chdir(docker_dir)
        
        # Construir y levantar servicios
        subprocess.run([
            "docker-compose", "up", "--build"
        ], check=True)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Error con Docker: {e}")
        return False
    except KeyboardInterrupt:
        logger.info("✓ Servicios detenidos")
        
        # Detener servicios
        try:
            subprocess.run([
                "docker-compose", "down"
            ], check=True)
        except:
            pass
        
        return True

def show_status():
    """Muestra el estado del sistema."""
    logger.info("📊 Estado del sistema:")
    
    # Verificar directorios
    dirs_to_check = [
        "data/documents",
        "data/processed", 
        "data/vector_index",
        "logs",
        "temp"
    ]
    
    for dir_path in dirs_to_check:
        if Path(dir_path).exists():
            logger.info(f"  ✓ {dir_path}")
        else:
            logger.info(f"  ✗ {dir_path}")
    
    # Verificar archivos de configuración
    config_files = [
        "config/settings.yaml",
        "requirements.txt"
    ]
    
    for file_path in config_files:
        if Path(file_path).exists():
            logger.info(f"  ✓ {file_path}")
        else:
            logger.info(f"  ✗ {file_path}")
    
    # Verificar documentos
    documents_dir = Path("data/documents")
    if documents_dir.exists():
        pdf_files = list(documents_dir.glob("*.pdf"))
        logger.info(f"  📄 {len(pdf_files)} documentos PDF")

def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Script de inicio rápido para Document Semantic Search"
    )
    parser.add_argument(
        "--mode", 
        choices=["api", "docker", "status"], 
        default="api",
        help="Modo de inicio (api|docker|status)"
    )
    parser.add_argument(
        "--create-test-doc", 
        action="store_true",
        help="Crear documento de prueba"
    )
    
    args = parser.parse_args()
    
    logger.info("🚀 Document Semantic Search - Inicio Rápido")
    logger.info("=" * 50)
    
    # Verificar dependencias
    if args.mode == "api" and not check_requirements():
        sys.exit(1)
    
    # Crear documento de prueba si se solicita
    if args.create_test_doc:
        create_test_document()
    
    # Mostrar estado
    if args.mode == "status":
        show_status()
        return
    
    # Iniciar sistema
    if args.mode == "api":
        start_api_server()
    elif args.mode == "docker":
        start_with_docker()

if __name__ == "__main__":
    main()