Guía para Agentes de IA del Proyecto
1. Descripción General del Proyecto

Este proyecto consiste en el desarrollo de un motor local de búsqueda semántica y análisis de documentos mediante inteligencia artificial.

El sistema está diseñado para analizar grandes colecciones de documentos en formato PDF y permitir búsquedas avanzadas que superen las limitaciones de las búsquedas tradicionales por palabras clave.

El objetivo principal es facilitar la exploración inteligente de grandes volúmenes de texto, permitiendo encontrar información relevante incluso cuando el contenido buscado no coincide literalmente con las palabras de la consulta.

La idea original surge del análisis de jurisprudencia legal, donde profesionales deben revisar cientos de documentos extensos para encontrar precedentes relevantes. Sin embargo, el sistema será generalista y adaptable a múltiples dominios del conocimiento.

Ejemplos de dominios posibles:

documentos legales

papers científicos

textos académicos

documentación técnica

manuales

artículos de investigación

libros digitalizados

documentación empresarial

El sistema permitirá indexar automáticamente documentos, generar representaciones vectoriales de su contenido y realizar búsquedas semánticas de alta precisión.

2. Objetivos del Sistema

El sistema deberá cumplir con los siguientes objetivos principales:

2.1 Motor de búsqueda semántica local

Permitir buscar información dentro de documentos usando significado semántico, no solo coincidencias de palabras.

Ejemplo:

Consulta:

responsabilidad del estado por negligencia médica

El sistema debe encontrar textos que hablen de:

mala praxis

responsabilidad estatal

fallos judiciales relacionados

negligencia hospitalaria

aunque no contengan exactamente la frase buscada.

2.2 Indexación automática de documentos

El sistema debe poder:

monitorear una carpeta de documentos

detectar nuevos PDFs automáticamente

procesarlos

extraer su texto

indexarlos para búsqueda

El usuario no deberá cargar documentos manualmente uno por uno.

2.3 Escalabilidad

El sistema debe poder manejar:

cientos de documentos

miles de documentos

documentos extensos (100–200 páginas o más)

Debe ser capaz de escalar sin degradar drásticamente el rendimiento.

2.4 Análisis de resultados con IA

El sistema permitirá analizar resultados utilizando modelos de IA externos.

Esto permitirá:

explicar por qué un documento es relevante

resumir fragmentos encontrados

comparar resultados

Ejemplo:

Este caso es relevante porque analiza responsabilidad médica en hospitales públicos
y establece un precedente sobre negligencia del personal sanitario.

El usuario podrá elegir qué proveedor de IA utilizar.

2.5 Perfiles de análisis por dominio

El sistema permitirá configurar perfiles de análisis que orienten el comportamiento de búsqueda.

Ejemplos de perfiles:

Legal

prioriza jurisprudencia

identifica precedentes

analiza decisiones judiciales

Científico

prioriza papers

identifica hipótesis

detecta metodologías

Técnico

prioriza documentación

identifica soluciones técnicas

Cada perfil podrá incluir:

prompts de contexto

parámetros de búsqueda

estrategias de análisis

2.6 Instalación simple

El sistema debe ser fácil de instalar para usuarios no técnicos.

Objetivos:

evitar instalaciones manuales complejas

evitar dependencias externas difíciles de configurar

empaquetar el sistema de forma simple

Para esto se permitirá el uso de Docker como método principal de distribución.

3. Principios de Diseño

El proyecto seguirá los siguientes principios:

Modularidad

Cada componente debe estar claramente separado.

Escalabilidad

La arquitectura debe permitir agregar funcionalidades sin romper el sistema.

Bajo consumo de recursos

Los procesos intensivos deben ejecutarse de forma controlada.

Privacidad

El procesamiento principal debe realizarse localmente.

Extensibilidad

Debe ser fácil agregar:

nuevos modelos de embeddings

nuevas bases vectoriales

nuevos proveedores de IA

4. Arquitectura General

El sistema estará compuesto por los siguientes módulos principales:

Usuario
  │
  ▼
Interfaz de búsqueda
  │
  ▼
API Backend
  │
  ├── Gestor de documentos
  ├── Pipeline de procesamiento
  ├── Generador de embeddings
  ├── Base de datos vectorial
  ├── Motor de búsqueda semántica
  └── Sistema de análisis con IA externa
5. Pipeline de Procesamiento de Documentos

Cuando se agregue un nuevo documento al sistema, se ejecutará el siguiente pipeline.

Paso 1 — Detección de archivo

El sistema detecta un nuevo PDF en la carpeta monitoreada.

Paso 2 — Extracción de texto

Se extrae el texto completo del documento.

Paso 3 — Limpieza de texto

Se eliminan:

encabezados repetidos

saltos de página innecesarios

caracteres corruptos

Paso 4 — Segmentación (Chunking)

El documento se divide en fragmentos de tamaño manejable.

Ejemplo:

Chunk 1: página 1–2
Chunk 2: página 3–4
Chunk 3: página 5–6

Esto permite mayor precisión en la búsqueda.

Paso 5 — Generación de embeddings

Cada fragmento se convierte en un vector semántico usando un modelo local.

Estos embeddings representan el significado del texto.

Paso 6 — Indexación vectorial

Los embeddings se almacenan en una base de datos vectorial que permite búsquedas semánticas rápidas.

6. Sistema de Búsqueda

Cuando el usuario realiza una consulta:

Paso 1

La consulta se convierte en embedding.

Paso 2

Se realiza una búsqueda de vectores similares en la base vectorial.

Paso 3

Se recuperan los fragmentos más relevantes.

Paso 4 (opcional)

Se aplica reranking para mejorar la precisión.

Paso 5

Se muestran múltiples resultados relevantes.

7. Explicación de Resultados con IA

El usuario podrá:

seleccionar fragmentos encontrados

enviarlos a una IA externa

Opciones posibles:

copiar prompt automáticamente

abrir proveedor externo

usar API configurada

El sistema debe permitir que el usuario configure su proveedor preferido.

Ejemplos:

ChatGPT

Claude

Gemini

otros servicios compatibles con API

8. Gestión de Recursos

La generación de embeddings puede consumir CPU.

Por lo tanto el sistema debe:

limitar uso de CPU

procesar documentos en segundo plano

permitir pausar indexación

Los embeddings se generan una sola vez por documento.

Solo se recalculan si el archivo cambia.

9. Estructura de Carpetas del Proyecto

La estructura del proyecto debe ser clara, modular y escalable.

semantic-document-search/
│
├── backend/
│   │
│   ├── api/
│   │   ├── routes/
│   │   └── controllers/
│   │
│   ├── services/
│   │   ├── search_service/
│   │   ├── embedding_service/
│   │   ├── reranking_service/
│   │   └── ai_analysis_service/
│   │
│   ├── ingestion/
│   │   ├── file_watcher/
│   │   ├── pdf_parser/
│   │   ├── text_cleaner/
│   │   └── chunker/
│   │
│   ├── vector_store/
│   │   ├── database/
│   │   └── index_manager/
│   │
│   ├── models/
│   │
│   └── config/
│
├── frontend/
│   │
│   ├── ui/
│   │
│   ├── search_interface/
│   │
│   ├── results_viewer/
│   │
│   └── settings/
│
├── embeddings_models/
│
├── data/
│   ├── documents/
│   ├── processed/
│   └── vector_index/
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── scripts/
│   ├── indexing
│   ├── maintenance
│   └── migration
│
├── docs/
│   ├── architecture.md
│   ├── development_guide.md
│   └── agent_guide.md
│
└── README.md
10. Reglas para Agentes de Desarrollo

Los agentes de IA que trabajen en este proyecto deben seguir estas reglas:

1. Mantener modularidad

No concentrar demasiada lógica en un solo archivo.

2. Evitar dependencias innecesarias

Solo agregar librerías si aportan valor real.

3. Mantener separación de responsabilidades

Cada módulo debe cumplir una función clara.

4. Priorizar procesamiento local

La información sensible debe permanecer en el sistema local.

5. Mantener el sistema extensible

Debe ser posible agregar:

nuevos modelos

nuevas bases vectoriales

nuevas interfaces

11. Visión a Futuro

Posibles extensiones del sistema:

OCR para PDFs escaneados

soporte para Word y otros formatos

clustering automático de documentos

detección automática de temas

análisis comparativo entre documentos

generación automática de resúmenes

recomendaciones de documentos relacionados

12. Resumen

Este proyecto busca crear un motor de análisis documental inteligente, capaz de procesar grandes volúmenes de texto y permitir búsquedas semánticas de alta precisión.

Características clave:

indexación automática

embeddings locales

búsqueda semántica

reranking de resultados

análisis con IA externa

instalación simple

arquitectura modular y escalable

El objetivo final es construir una herramienta poderosa pero accesible para profesionales que trabajan con grandes cantidades de documentos.