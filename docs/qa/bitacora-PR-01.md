# Bitácora PR-01 — Configuración y CLI

Fecha: 02/09/2026
Criterio de aceptación (plan §6): la config se carga desde cualquier CWD y
apunta siempre a la misma carpeta `data/`. Test explícito de eso (bug D-02).
`spectre --help` con los subcomandos vacíos.

## Qué hice

### `spectre/config.py`

- `Settings(BaseSettings)` de `pydantic-settings`. Se puebla desde variables
  `SPECTRE_*` y un `.env` opcional.
- **Ancla de rutas:** `PACKAGE_DIR = Path(__file__).resolve().parent` (la carpeta
  `spectre/`), `PROJECT_ROOT = PACKAGE_DIR.parent` (la raíz del repo). El CWD no
  se consulta en ningún punto.
- Campo único de ruta: `data_dir`, default `PROJECT_ROOT / "data"`. Un
  `field_validator` ancla cualquier valor relativo (venga de env o de default) a
  `PROJECT_ROOT` y lo `resolve()`. Un valor absoluto se respeta tal cual.
- Rutas derivadas como `@property`, no como campos: `tomos_dir` (`data/tomos`),
  `db_path` (`data/spectre.db`), `vectors_dir` (`data/vectors`). Así siguen a
  `data_dir` si se lo pisa por env.
- `env_file` apunta a `PROJECT_ROOT / ".env"`, no al `.env` relativo al CWD que
  pydantic-settings usa por defecto —misma razón que todo lo demás.
- `ensure_dirs()` crea `data_dir`, `tomos_dir`, `vectors_dir`. **No se llama al
  importar** ni en el validator: solo cuando un PR posterior vaya a escribir de
  verdad. Importar la config no debe tocar el disco (el otro costado de D-02).
- `get_settings()` con `lru_cache`: punto de acceso único para el resto del
  paquete.
- `embedding_model` con default `sentence-transformers/paraphrase-multilingual-
  MiniLM-L12-v2` (D-7: multilingüe, 384 dim, CPU). Marcado como provisional
  hasta PR-12.

### `spectre/cli.py`

- `argparse` (stdlib, sin dependencia nueva de CLI).
- `spectre --version` → `spectre 0.0.0`.
- Subparsers con `required=True`: sin subcomando es error (exit 2).
- `spectre config`: **subcomando real**, imprime las 6 filas de config resuelta
  alineadas. Sirve para verificar D-02 a ojo. No finge nada.
- `spectre db` / `ingest` / `serve`: existen en `--help` (con la etiqueta del PR
  que los va a implementar) y **`raise SystemExit(mensaje)` si se invocan**
  (exit 1). Ningún stub que reporte éxito (D-05).
- `main(argv=None)` para poder testear sin `sys.argv`.

### `pyproject.toml`

- `dependencies = ["pydantic-settings>=2.4"]` (primera dependencia de runtime).
- `[project.scripts] spectre = "spectre.cli:main"` (lo que PR-00 había dejado
  anotado como pendiente).

### Tests

- `tests/test_config.py` (7 tests): `data_dir` absoluta y bajo el root; **config
  idéntica desde `PROJECT_ROOT` y desde un `tmp_path` cualquiera** (el test de
  D-02); rutas derivadas; env relativa se ancla al root; env absoluta se
  respeta; `ensure_dirs()` crea y antes no existía; `get_settings()` cacheado.
- `tests/test_cli.py` (7 tests): `--help` exit 0 y menciona `config`;
  `--version` exit 0; `config` imprime `data_dir` / `spectre.db` /
  `embedding_model`; los tres subcomandos vacíos → exit ≠ 0 con "no
  implementado"; sin subcomando → error; subcomando desconocido → error.

## Qué decidí por mi cuenta

- **`argparse` y no `typer`/`click`.** La CLI de PR-01 es mínima; no justifica
  sumar una dependencia. Si más adelante crece, se migra.
- **Qué subcomandos declarar vacíos.** El plan dice "los subcomandos vacíos" sin
  listarlos. Elegí `db` (PR-02), `ingest` (PR-19), `serve` (PR-20): son los tres
  puntos de entrada nombrados de forma explícita o casi en el plan. Los demás
  (catálogo, descarga, búsqueda por CLI) se agregan cuando su PR los necesite,
  para no adivinar nombres ahora.
- **`config` como subcomando que funciona**, en vez de dejar la CLI 100% hueca.
  No contradice "subcomandos vacíos": es introspección de la config, no
  procesamiento simulado, y es la forma natural de verificar D-02 a mano.
- **Rutas derivadas como `property` y no campos de `Settings`.** Un solo campo
  (`data_dir`) como fuente de verdad; lo demás se calcula. Menos superficie para
  que una env var deje la config incoherente.
- **`embedding_model` ya en la config** aunque PR-12 sea el que lo usa, porque
  D-7 dice "en la config" y no cuesta nada. Default provisional, comentado.

## En qué me desvié del plan

- Nada material. El plan pedía config + CLI vacía + test de D-02; está todo.
- Extra sobre lo pedido: el subcomando `config` operativo y el campo
  `embedding_model`. Ninguno agranda el alcance real.
- **Encadené PR-01 con PR-00 en la misma sesión**, contra la regla "un PR por
  sesión, no encadenar dos" de `CLAUDE.md` / plan §1. Fue a pedido explícito de
  Kevin en el chat, con PR-00 ya mergeado.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/ruff.exe check .            # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .   # -> 10 files already formatted
./.venv/Scripts/python.exe -m pytest -q     # -> 16 passed in 0.55s
./.venv/Scripts/python.exe -m spectre.cli --help     # lista config/db/ingest/serve
./.venv/Scripts/python.exe -m spectre.cli config     # 6 filas, rutas absolutas bajo el repo
./.venv/Scripts/python.exe -m spectre.cli serve      # exit 1, "no implementado todavía (llega en PR-20)"
```

Salida de `spectre config` (rutas recortadas a la raíz del repo):

```
project_root     .../Spectre
data_dir         .../Spectre/data
tomos_dir        .../Spectre/data/tomos
db_path          .../Spectre/data/spectre.db
vectors_dir      .../Spectre/data/vectors
embedding_model  sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

`pytest` corre el test de D-02 (`test_config_identica_desde_cualquier_cwd`) que
hace `chdir` a `PROJECT_ROOT` y después a un subdir de `tmp_path`, y exige el
mismo `data_dir` absoluto en ambos.

## Dudas que quedaron

- **"Raíz del paquete" = raíz del repo.** Interpreté que `data/` cuelga del repo
  (así está en el árbol del plan §4), y anclé a `spectre/__file__ → parent →
  parent`. Funciona con el install editable, que es el único modo de uso
  (monousuario, local). Un `pip install spectre` a site-packages no tendría
  `data/` al lado; no es un escenario del proyecto, pero queda anotado.
- **`get_settings()` es cacheado por proceso.** Si en el futuro algún flujo
  necesita releer la config tras cambiar el entorno, va a haber que exponer un
  `get_settings.cache_clear()`. Hoy nadie lo necesita.
- **Consola Windows** muestra los acentos del `--help` como mojibake por el
  codepage del shell; el fuente es UTF-8 y en CI (Linux) sale bien. No se tocó.
