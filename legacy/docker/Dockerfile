# Dockerfile para Document Semantic Search API
# Basado en Python 3.11 para compatibilidad y rendimiento

# Etapa de construcción
FROM python:3.11-slim as builder

# Mantenedor
LABEL maintainer="Document Semantic Search Team"
LABEL description="Motor de búsqueda semántica local para documentos PDF"

# Configuración de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no root
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Etapa de producción
FROM python:3.11-slim

# Configuración de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no root
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Crear directorios
RUN mkdir -p /app /app/data /app/logs /app/temp

# Cambiar a usuario no root
USER appuser

# Copiar dependencias de la etapa de construcción
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/pip /usr/local/bin/pip

# Copiar código de la aplicación
COPY --chown=appuser:appuser . /app

# Cambiar al directorio de la aplicación
WORKDIR /app

# Exponer puerto
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/simple || exit 1

# Comando de inicio
CMD ["python", "-m", "core_engine.api.app"]