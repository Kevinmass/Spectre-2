# Bitácora PR-00 — Esqueleto del repo

Fecha: 02/09/2026
Criterio de aceptación (plan §6): `pytest` corre y pasa; `ruff check` limpio;
CI en verde.

## Qué hice

1. **Moví el proyecto anterior a `legacy/`.** `mv document-semantic-search
   legacy`. Se movió el árbol completo, incluyendo lo que no estaba versionado
   (`config/`, `core_engine/`, `scripts/`, `tests/`, `requirements.txt`, `logs/`,
   `models/`, `desktop-app/`, `data/`, `temp/`). Los 3 archivos que git veía
   modificados sin commitear (`README.md`, `docker/Dockerfile`,
   `docker/docker-compose.yml`) se movieron tal cual, con sus cambios. No los
   revisé: `legacy/` es referencia histórica y no se toca.

2. **Borré `data/`, `logs/`, `temp/` de la raíz.** Eran residuo del bug D-02
   (rutas resueltas contra el CWD). Estaban vacíos salvo `logs/app.log` de 0
   bytes y subcarpetas del layout viejo (`data/documents`, `data/processed`,
   `data/vector_index`). Kevin confirmó el borrado en el chat.

3. **`pyproject.toml`** — build backend `hatchling`, `name = "spectre"`,
   `version = "0.0.0"`, `requires-python = ">=3.11"`, layout plano
   (`packages = ["spectre"]`). Sin dependencias de runtime todavía. Extra `dev`:
   `pytest>=8`, `ruff>=0.6`. Config de `ruff` (target py311, line-length 88,
   `select = ["E","F","I","UP","B","W"]`, `extend-exclude = ["legacy"]`) y de
   `pytest` (`testpaths = ["tests"]`, `addopts = "-ra"`) en el mismo archivo.

4. **`spectre/__init__.py`** con `__version__ = "0.0.0"` y docstring. Nada más.

5. **`tests/test_smoke.py`** — un test: el paquete importa y `__version__` es un
   string no vacío. No es un placeholder de features futuras; es lo que hace que
   la suite y el CI existan desde ya (defecto D-01).

6. **`.gitignore`** — Python estándar + `/data/`, `/logs/`, `/temp/` (anclados a
   la raíz), `*.db` y variantes WAL/SHM, `.venv/`, `.ruff_cache/`,
   `.pytest_cache/`, basura de editor/SO.

7. **`.github/workflows/ci.yml`** — job único en `ubuntu-latest`, Python 3.11,
   `pip install -e ".[dev]"`, `ruff check .`, `pytest`. Dispara en push a `main`
   y en todo pull request.

8. **`README.md`** en la raíz (antes no había; `pyproject` lo referencia).
   Placeholder honesto que apunta al plan y marca que el README de uso llega en
   PR-26.

## Qué decidí por mi cuenta

- **`hatchling`** como build backend en vez de `setuptools`. Más simple para
  layout plano, sin `setup.cfg` ni `MANIFEST.in`.
- **No declaré el script de consola `spectre`** en `[project.scripts]`. El plan
  pone la CLU en PR-01 ("`spectre --help` con los subcomandos vacíos"). Declarar
  el entry point ahora, apuntando a un `spectre.cli:main` inexistente, dejaría un
  `spectre --help` que explota con ImportError. Dejé un comentario en
  `pyproject.toml` señalando que PR-01 lo agrega.
- **CI con una sola versión de Python (3.11)**, no una matriz. D-11 fija 3.11
  como el stack; no hay razón hoy para probar contra 3.12/3.13.
- **`ruff` excluye `legacy/`** vía `extend-exclude`. El código viejo no tiene que
  poder romper el lint del proyecto nuevo.
- **`.gitignore` con rutas ancladas** (`/data/` y no `data/`) para que ignore
  solo las de la raíz del repo, no un futuro `spectre/algo/data/`.

## En qué me desvié del plan

- El plan dice "Borrar `data/`, `logs/`, `temp/` duplicados en la raíz". Además
  de esos tres, moví a `legacy/` un `desktop-app/` y un `models/` que el plan no
  menciona pero estaban dentro de `document-semantic-search/`. Van con el resto
  del proyecto viejo, no los saqué aparte.
- Agregué un `README.md` en la raíz, que el plan no pide explícitamente en
  PR-00, porque `pyproject.toml` lo necesita para no tirar warning al construir.

## Qué verifiqué y con qué comandos

Entorno: venv nuevo con el Python del sistema (3.13.7 — la máquina no tiene 3.11
instalado; CI cubre 3.11).

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/ruff.exe check .            # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .   # -> 5 files already formatted
./.venv/Scripts/python.exe -m pytest        # -> 1 passed in 0.02s
```

Salida de pytest:

```
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
configfile: pyproject.toml
testpaths: tests
collected 1 item
tests\test_smoke.py .                                              [100%]
1 passed in 0.02s
```

CI: el workflow está escrito pero todavía no corrió en GitHub. Se confirma verde
cuando se pushee la rama y Actions lo ejecute.

## Dudas que quedaron

- **Python 3.11 local.** La máquina de Kevin corre 3.13. La verificación local de
  este PR se hizo en 3.13. A partir de PR-02 (SQLite, migraciones) conviene tener
  un venv 3.11 real para que coincida con CI y con lo que se mide sobre el Tomo
  348. Anotado también en `CLAUDE.md`.
- **Fixture `data/tomos/348.pdf`.** No está en el repo (queda gitignored). Hace
  falta ponerlo a mano antes de PR-04 en adelante.
- **CI en verde de verdad.** Depende de un push a GitHub que este PR no hace.
