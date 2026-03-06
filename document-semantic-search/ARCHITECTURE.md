Arquitectura del Sistema — Motor de Búsqueda Semántica de Documentos
1. Introducción

Este documento describe la arquitectura técnica del sistema utilizado para construir el motor de búsqueda semántica y análisis de documentos con IA.

La arquitectura fue diseñada con los siguientes objetivos:

procesamiento local de documentos

escalabilidad a miles de archivos

modularidad

bajo consumo de recursos

extensibilidad futura

El sistema se basa en una arquitectura modular por servicios internos, donde cada componente cumple una función específica dentro del pipeline de procesamiento de documentos y búsqueda semántica.

2. Visión General de la Arquitectura

El sistema se compone de cuatro capas principales:

Usuario
   │
   ▼
Frontend (Interfaz de usuario)
   │
   ▼
Backend API
   │
   ├── Ingestión de documentos
   ├── Pipeline de procesamiento
   ├── Motor de embeddings
   ├── Base de datos vectorial
   ├── Motor de búsqueda semántica
   └── Integración con IA externa
   │
   ▼
Almacenamiento local

Cada capa tiene responsabilidades claras.

3. Componentes del Sistema
3.1 Frontend
Responsabilidad

Proveer la interfaz para que el usuario pueda:

realizar búsquedas

ver resultados

gestionar documentos

configurar el sistema

Funciones

enviar consultas al backend

mostrar resultados de búsqueda

mostrar estado de indexación

permitir acceso al análisis con IA externa

Componentes del frontend
frontend/
│
├── search_interface/
├── results_viewer/
├── documents_panel/
└── settings_panel/
4. Backend

El backend actúa como orquestador del sistema.

Es responsable de:

recibir consultas

coordinar servicios internos

procesar documentos

gestionar la base vectorial

4.1 API Layer

Esta capa expone endpoints para el frontend.

Ejemplos de endpoints
GET /health
GET /documents
POST /search
POST /reindex
GET /status

Ubicación:

backend/api/
4.2 Document Ingestion System

El sistema de ingesta detecta nuevos documentos y los envía al pipeline de procesamiento.

Componentes
backend/ingestion/
│
├── file_watcher
├── document_registry
└── ingestion_queue
Función

monitorear carpeta de documentos

detectar archivos nuevos

agregar documentos a la cola de procesamiento

5. Pipeline de Procesamiento de Documentos

El pipeline transforma documentos PDF en datos semánticos utilizables.

PDF
 │
 ▼
Extracción de texto
 │
 ▼
Limpieza de texto
 │
 ▼
Chunking
 │
 ▼
Generación de embeddings
 │
 ▼
Indexación vectorial
5.1 PDF Parser

Responsable de extraer texto del documento.

Ubicación:

backend/ingestion/pdf_parser/

Funciones:

abrir PDF

extraer texto

preservar orden del documento

5.2 Text Cleaner

Limpia el texto extraído.

Elimina:

encabezados repetidos

saltos innecesarios

artefactos del PDF

Ubicación:

backend/ingestion/text_cleaner/
5.3 Chunking Engine

Divide el texto en fragmentos manejables.

Ejemplo:

chunk_size = 500 palabras
overlap = 100 palabras

Esto permite mejorar precisión en búsquedas.

Ubicación:

backend/ingestion/chunker/
6. Motor de Embeddings

Los embeddings transforman texto en vectores numéricos que representan su significado.

Este componente se ejecuta localmente para preservar privacidad.

6.1 Embedding Service

Responsabilidades:

cargar modelo de embeddings

generar vectores semánticos

limitar uso de CPU

procesar en segundo plano

Ubicación:

backend/services/embedding_service/
6.2 Control de Recursos

Para evitar afectar el rendimiento del sistema del usuario:

limitar uso de CPU

ejecutar procesamiento en segundo plano

procesar documentos por lotes

Los embeddings se generan una sola vez por documento.

7. Base de Datos Vectorial

La base vectorial almacena:

embeddings

texto asociado

referencia al documento original

Permite realizar búsquedas por similitud semántica.

7.1 Estructura de Datos

Cada registro contiene:

vector_embedding
text_chunk
document_id
page_number
chunk_id
metadata

Ubicación:

backend/vector_store/
7.2 Persistencia

Los índices vectoriales se almacenan en:

data/vector_index/

Esto permite que el sistema conserve los datos entre reinicios.

8. Motor de Búsqueda Semántica

Este componente ejecuta las consultas del usuario.

Pipeline de búsqueda:

Consulta usuario
   │
   ▼
Embedding de consulta
   │
   ▼
Similarity search
   │
   ▼
Top resultados
   │
   ▼
Reranking (opcional)
   │
   ▼
Resultados finales
8.1 Query Embedding

La consulta del usuario se transforma en un vector.

Ejemplo:

"responsabilidad médica del estado"

Esto permite encontrar textos con significado similar.

8.2 Similarity Search

El sistema busca vectores cercanos en el espacio semántico.

Se devuelven los N resultados más relevantes.

8.3 Reranking

Un modelo adicional puede reorganizar los resultados para mejorar precisión.

Ubicación:

backend/services/reranking_service/
9. Sistema de Análisis con IA

El sistema puede enviar resultados a una IA externa para análisis adicional.

Esto permite:

explicar relevancia

resumir casos

comparar documentos

Opciones de uso
1. Copiar prompt preparado

El sistema genera un prompt listo para usar.

2. Abrir proveedor externo

El usuario puede abrir su herramienta favorita.

3. Integración API

Opcionalmente se puede configurar una API externa.

Ubicación:

backend/services/ai_analysis_service/
10. Sistema de Perfiles de Análisis

Los perfiles permiten adaptar el sistema a distintos dominios.

Ejemplos:

profiles/
│
├── legal.yaml
├── scientific.yaml
└── technical.yaml

Cada perfil define:

prompts de análisis

parámetros de búsqueda

configuración de reranking

11. Sistema de Almacenamiento

El sistema utiliza almacenamiento local estructurado.

data/
│
├── documents/
├── processed/
└── vector_index/
documents

Contiene los PDFs originales.

processed

Archivos intermedios del pipeline.

vector_index

Embeddings e índices vectoriales persistentes.

12. Dockerización del Sistema

El sistema puede ejecutarse usando Docker.

Beneficios:

instalación simple

entorno reproducible

dependencias encapsuladas

Estructura Docker
docker/
│
├── Dockerfile
└── docker-compose.yml
Servicios posibles
services:

  backend
  vector_db
  frontend

Esto permite levantar el sistema con:

docker compose up
13. Flujo Completo del Sistema
Indexación
Usuario coloca PDF
        │
        ▼
File Watcher detecta archivo
        │
        ▼
PDF Parser extrae texto
        │
        ▼
Text Cleaner
        │
        ▼
Chunking
        │
        ▼
Embeddings
        │
        ▼
Vector Database
Búsqueda
Usuario escribe consulta
        │
        ▼
Query Embedding
        │
        ▼
Similarity Search
        │
        ▼
Top Resultados
        │
        ▼
Reranking
        │
        ▼
Resultados mostrados
14. Escalabilidad del Sistema

El sistema fue diseñado para soportar:

cientos de documentos

miles de documentos

millones de fragmentos

Esto se logra mediante:

indexación vectorial

chunking eficiente

procesamiento incremental

15. Seguridad y Privacidad

El sistema prioriza procesamiento local.

Características:

documentos no se envían a la nube

embeddings generados localmente

análisis con IA externa solo si el usuario lo permite

16. Extensibilidad

La arquitectura permite agregar fácilmente:

Nuevos modelos de embeddings
embeddings_models/
Nuevas bases vectoriales
backend/vector_store/
Nuevos perfiles de análisis
profiles/
Nuevas integraciones de IA
backend/services/ai_analysis_service/
17. Conclusión

La arquitectura propuesta permite construir un sistema que sea:

potente

modular

escalable

privado

extensible

El diseño está optimizado para permitir que el sistema evolucione con el tiempo sin requerir reestructuraciones profundas.

Este documento sirve como referencia técnica para desarrolladores y agentes de IA que trabajen en el proyecto.