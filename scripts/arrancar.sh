#!/usr/bin/env bash
# Arranque de un comando (PR-24): del clone a la primera búsqueda sin leer
# documentación. macOS/Linux; para Windows ver scripts/arrancar.ps1.
#
# Solo se ocupa de lo que hace falta ANTES de que `spectre` sea importable
# (crear el venv, instalar el paquete). El resto —bajar el modelo, intentar
# indexar un tomo de muestra, levantar el servidor— vive en
# scripts/arrancar.py, en Python, para poder testearlo.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON=python3.11
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "No se encontró python3 en el PATH. Instalá Python 3.11+ y volvé a correr este script." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creando el entorno virtual (.venv)..."
  "$PYTHON" -m venv .venv
fi

VENV_PY=".venv/bin/python"

echo "Instalando dependencias (esto puede tardar unos minutos)..."
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -e ".[embed]"

exec "$VENV_PY" scripts/arrancar.py
