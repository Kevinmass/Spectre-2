Hoja de Ruta del Proyecto — Motor de Búsqueda Semántica de Documentos
1. Propósito del Roadmap

Este documento define las etapas de desarrollo del proyecto, organizadas en fases progresivas que permiten construir el sistema de manera ordenada, testeable y escalable.

Cada fase del roadmap busca:

mantener el sistema siempre funcional

permitir validar cada componente antes de avanzar

reducir complejidad técnica temprana

facilitar contribuciones futuras

La estrategia es construir primero el núcleo funcional, y luego agregar capacidades avanzadas.

2. Visión General de Fases

El desarrollo se dividirá en 8 fases principales:

Fase	Nombre
1	Setup del Proyecto
2	Ingesta de Documentos
3	Pipeline de Procesamiento
4	Generación de Embeddings
5	Base de Datos Vectorial
6	Motor de Búsqueda Semántica
7	Interfaz de Usuario
8	Integración con IA Externa
9	Optimización y Escalabilidad

Cada fase desbloquea capacidades nuevas del sistema.

3. Fase 1 — Setup del Proyecto
Objetivo

Preparar la base del proyecto para permitir desarrollo organizado.

Tareas
1. Crear estructura de proyecto

Implementar la estructura de carpetas definida en:

agent_guide.md
2. Configurar entorno de desarrollo

Crear:

Dockerfile
docker-compose.yml

Servicios iniciales:

backend

base de datos vectorial (si aplica)

3. Crear backend base

El backend debe incluir:

servidor API

rutas básicas

configuración del proyecto

Endpoints iniciales:

GET /health
GET /status
4. Configuración central

Crear un sistema de configuración para:

rutas de carpetas

modelos de embeddings

configuración de CPU

Ejemplo:

config/settings.yaml
4. Fase 2 — Ingesta de Documentos
Objetivo

Permitir que el sistema detecte automáticamente documentos nuevos.

Tareas
1. Carpeta de documentos

Crear carpeta:

data/documents/

Aquí el usuario colocará los PDFs.

2. Sistema de monitoreo

Implementar un file watcher que:

detecte archivos nuevos

detecte modificaciones

agregue documentos a una cola de procesamiento

Ejemplo:

backend/ingestion/file_watcher
3. Registro de documentos

Crear un sistema para registrar documentos:

nombre

ruta

estado de procesamiento

fecha de indexación

5. Fase 3 — Pipeline de Procesamiento
Objetivo

Transformar documentos PDF en texto limpio listo para análisis.

Tareas
1. Parser de PDF

Extraer texto de los documentos.

Ubicación:

backend/ingestion/pdf_parser

Debe soportar:

PDFs normales

PDFs largos

2. Limpieza de texto

Eliminar:

encabezados repetidos

saltos innecesarios

caracteres corruptos

Ubicación:

backend/ingestion/text_cleaner
3. Segmentación (Chunking)

Dividir documentos en fragmentos de tamaño adecuado.

Ejemplo:

chunk_size = 500 palabras
overlap = 100 palabras

Ubicación:

backend/ingestion/chunker
6. Fase 4 — Generación de Embeddings
Objetivo

Convertir fragmentos de texto en vectores semánticos.

Tareas
1. Integrar modelo de embeddings local

El sistema debe poder cargar modelos locales.

Ubicación:

embeddings_models/
2. Servicio de embeddings

Implementar servicio:

backend/services/embedding_service

Responsabilidades:

generar embeddings

controlar uso de CPU

procesar en segundo plano

3. Cola de procesamiento

Implementar una cola para procesar documentos sin bloquear el sistema.

7. Fase 5 — Base de Datos Vectorial
Objetivo

Guardar embeddings y permitir búsquedas eficientes.

Tareas
1. Seleccionar vector database

Debe permitir:

similarity search

indexado rápido

uso local

Ubicación:

backend/vector_store/
2. Sistema de indexación

Guardar:

vector

texto del fragmento

documento origen

página

3. Persistencia

Los índices deben sobrevivir reinicios del sistema.

Ubicación:

data/vector_index/
8. Fase 6 — Motor de Búsqueda Semántica
Objetivo

Permitir consultas inteligentes sobre los documentos indexados.

Tareas
1. Conversión de consulta a embedding

Cuando el usuario busca:

"responsabilidad por negligencia médica"

Se genera su embedding.

2. Similarity Search

Buscar los vectores más cercanos.

Resultado:

Top 20 resultados relevantes
3. Reranking

Mejorar precisión reordenando resultados.

Ubicación:

backend/services/reranking_service
4. Endpoint de búsqueda

API:

POST /search

Input:

query
modo de búsqueda
cantidad de resultados
9. Fase 7 — Interfaz de Usuario
Objetivo

Permitir que usuarios no técnicos utilicen el sistema.

Componentes
1. Buscador principal

Funciones:

campo de búsqueda

selección de modo

botón de búsqueda

2. Visualizador de resultados

Mostrar:

fragmento encontrado

documento origen

relevancia

3. Panel de documentos

Mostrar:

documentos indexados

estado de procesamiento

4. Configuración

Permitir:

elegir proveedor de IA

configurar carpetas

elegir perfil de análisis

10. Fase 8 — Integración con IA Externa
Objetivo

Permitir análisis avanzado de resultados.

Opciones
1. Copiar prompt automático

El sistema prepara un prompt para analizar resultados.

2. Abrir proveedor externo

El usuario puede abrir su IA preferida.

3. Uso de API

Opcionalmente:

enviar texto directamente

recibir explicación

11. Fase 9 — Optimización
Objetivo

Mejorar rendimiento y escalabilidad.

Mejoras posibles
Paralelización de embeddings

Procesar múltiples documentos a la vez.

Indexación incremental

Solo procesar documentos nuevos.

Caché de consultas

Guardar resultados frecuentes.

Optimización de índices

Mejorar velocidad de búsqueda.

12. Fase 10 — Funciones Avanzadas (Futuro)

Estas funciones no son necesarias para la versión inicial.

OCR para PDFs escaneados

Permitir analizar documentos que no contienen texto.

Clustering de documentos

Agrupar documentos por tema.

Detección automática de temas

Identificar tópicos principales.

Recomendaciones

Sugerir documentos relacionados.

Comparación de documentos

Analizar similitudes entre textos.

13. MVP (Producto Inicial)

La primera versión funcional del sistema debe incluir:

✔ indexación automática de PDFs
✔ extracción de texto
✔ generación de embeddings
✔ base vectorial
✔ búsqueda semántica
✔ interfaz simple
✔ visualización de resultados

14. Versión 1.0

La versión completa incluirá:

✔ perfiles de análisis
✔ reranking avanzado
✔ integración con IA externa
✔ optimización de búsqueda
✔ panel de administración

15. Filosofía de Desarrollo

Este proyecto debe desarrollarse con la siguiente filosofía:

construir paso a paso

validar cada componente

evitar complejidad prematura

priorizar estabilidad

mantener el sistema modular

16. Resultado Esperado

El resultado final será una herramienta capaz de:

analizar miles de documentos

encontrar información relevante rápidamente

ayudar a profesionales a navegar grandes volúmenes de texto

facilitar descubrimiento de conocimiento oculto en documentos

Este roadmap debe ser seguido progresivamente por los agentes de desarrollo para garantizar una implementación ordenada y escalable del sistema.