# Arranque de un comando (PR-24): del clone a la primera búsqueda sin leer
# documentación. Windows; para macOS/Linux ver scripts/arrancar.sh.
#
# Solo se ocupa de lo que hace falta ANTES de que `spectre` sea importable
# (crear el venv, instalar el paquete). El resto -bajar el modelo, intentar
# indexar un tomo de muestra, levantar el servidor- vive en
# scripts/arrancar.py, en Python, para poder testearlo.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "No se encontró 'python' en el PATH. Instalá Python 3.11+ y volvé a correr este script."
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creando el entorno virtual (.venv)..."
    python -m venv .venv
}

$venvPython = ".\.venv\Scripts\python.exe"

Write-Host "Instalando dependencias (esto puede tardar unos minutos)..."
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -e ".[embed]"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $venvPython scripts\arrancar.py
