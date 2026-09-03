# Document Semantic Search

Motor local de búsqueda semántica y análisis de documentos mediante inteligencia artificial.

## 🎯 Visión General

Este proyecto implementa un sistema avanzado de búsqueda semántica que permite analizar grandes colecciones de documentos PDF y realizar búsquedas inteligentes basadas en significado, no solo en coincidencias de palabras clave.

### Características Principales

- **Indexación automática** de documentos PDF
- **Búsqueda semántica** basada en embeddings
- **Procesamiento local** para privacidad y seguridad
- **Integración con IA externa** para análisis avanzado
- **Arquitectura modular** y escalable
- **Despliegue Docker** para fácil instalación

## 🚀 Inicio Rápido

### Requisitos Previos

- Python 3.11+
- Docker (opcional, para despliegue)

### Instalación Local

1. **Clonar el repositorio:**
   ```bash
   git clone <url-del-repositorio>
   cd document-semantic-search
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar el sistema:**
   ```bash
   python scripts/setup/quick_start.py --mode api
   ```

4. **Acceder a la API:**
   - Documentación: http://localhost:8000/docs
   - Health Check: http://localhost:8000/api/v1/health

### Despliegue con Docker

1. **Construir y levantar servicios:**
   ```bash
   python scripts/setup/quick_start.py --mode docker
   ```

2. **Acceder a los servicios:**
   - API: http://localhost:8000
   - Qdrant (base de datos): http://localhost:6333

## 📁 Estructura del Proyecto

```
document-semantic-search/
├── core-engine/              # Motor central del sistema
│   ├── api/                  # API REST
│   ├── config/               # Configuración del sistema
│   ├── indexing/             # Procesamiento de documentos
│   ├── search/               # Motor de búsqueda
│   ├── vector_store/         # Base de datos vectorial
│   ├── workers/              # Procesamiento en segundo plano
│   └── utils/                # Utilidades
├── docker/                   # Configuración Docker
├── data/                     # Datos del sistema
│   ├── documents/            # Documentos originales
│   ├── processed/            # Documentos procesados
│   └── vector_index/         # Índices vectoriales
├── config/                   # Archivos de configuración
├── models/                   # Modelos de IA
├── scripts/                  # Scripts de utilidad
├── tests/                    # Pruebas del sistema
└── docs/                     # Documentación
```

## 🔧 Configuración

El sistema utiliza un archivo de configuración YAML ubicado en `config/settings.yaml`.

### Configuración Principal

```yaml
# Rutas del sistema
paths:
  documents_path: "data/documents"
  processed_path: "data/processed"
  vector_index_path: "data/vector_index"

# Configuración del sistema
system:
  environment: "development"
  debug: true
  max_workers: 4
  cpu_usage_limit: 0.8
  memory_limit_gb: 4.0

# Configuración de embeddings
embedding:
  model_name: "all-MiniLM-L6-v2"
  device: "cpu"
  batch_size: 32

# Configuración de base de datos
database:
  host: "localhost"
  port: 6333
  collection_name: "documents"
```

### Variables de Entorno

- `DSS_ENV`: Entorno del sistema (development, testing, production)
- `DSS_CONFIG_FILE`: Ruta al archivo de configuración

## 📋 Uso

### 1. Agregar Documentos

Coloca tus archivos PDF en la carpeta `data/documents/`. El sistema los detectará automáticamente.

### 2. Ver Estado del Sistema

```bash
# Ver estado general
curl http://localhost:8000/api/v1/status

# Ver documentos procesados
curl http://localhost:8000/api/v1/status/documents
```

### 3. Realizar Búsquedas

```bash
# Búsqueda semántica (endpoint futuro)
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "responsabilidad médica", "limit": 10}'
```

## 🧪 Pruebas

Ejecutar las pruebas unitarias:

```bash
# Instalar pytest si no está instalado
pip install pytest

# Ejecutar todas las pruebas
pytest tests/

# Ejecutar pruebas específicas
pytest tests/unit/test_api.py -v
pytest tests/unit/test_config.py -v
pytest tests/unit/test_file_watcher.py -v
```

## 🐳 Docker

### Construir Imagen

```bash
docker build -t document-semantic-search .
```

### Ejecutar Contenedor

```bash
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  document-semantic-search
```

### Docker Compose

```bash
docker-compose up --build
```

## 🔍 API Endpoints

### Endpoints Principales

- `GET /` - Información básica del sistema
- `GET /api` - Información detallada de la API
- `GET /api/v1/health` - Estado de salud del sistema
- `GET /api/v1/health/simple` - Health check simple
- `GET /api/v1/status` - Estado del sistema y procesamiento
- `GET /api/v1/status/documents` - Estado de documentos

### Documentación

Accede a la documentación completa en: http://localhost:8000/docs

## 🎯 Roadmap

### Fase 1 ✅ - Setup del Proyecto
- [x] Estructura de proyecto
- [x] Backend API base
- [x] Sistema de configuración
- [x] Docker setup
- [x] Estructura de carpetas
- [x] File watcher básico
- [x] Cola de tareas básica
- [x] Pruebas unitarias

### Fase 2 🚧 - Ingesta de Documentos
- [ ] Parser de PDFs
- [ ] Limpieza de texto
- [ ] Sistema de registro de documentos

### Fase 3 📋 - Pipeline de Procesamiento
- [ ] Chunking de documentos
- [ ] Validación de contenido
- [ ] Manejo de errores

### Fase 4 📊 - Generación de Embeddings
- [ ] Integración de modelos locales
- [ ] Control de recursos
- [ ] Procesamiento en lote

### Fases Futuras
- Base de datos vectorial
- Motor de búsqueda semántica
- Interfaz de usuario
- Integración con IA externa

## 🤝 Contribución

1. Haz un fork del proyecto
2. Crea una rama para tu feature (`git checkout -b feature/nombre-feature`)
3. Haz commit de tus cambios (`git commit -m 'Añade feature'`)
4. Sube a la rama (`git push origin feature/nombre-feature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para más detalles.

## 🙏 Agradecimientos

- Comunidad de machine learning y NLP
- Proyectos open source utilizados
- Contribuidores y testers

## 📞 Contacto

Para soporte o preguntas:

- Email: [tu-email@example.com]
- Issues: [GitHub Issues](https://github.com/tu-usuario/document-semantic-search/issues)

---

**Made with ❤️ for semantic search**