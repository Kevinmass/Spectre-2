# Bitácora PR-02 — Esquema SQLite y repositorio

Fecha: 03/09/2026
Criterio de aceptación (plan §6): `schema.sql`, migraciones versionadas simples,
`db/repo.py` con las operaciones de tomo/página/fallo. Crear la base, insertar un
tomo y leerlo; test de idempotencia de la migración.

## Qué hice

### `spectre/db/migrations/0001_initial.sql`

El esquema completo del plan §5, las 7 tablas del modelo congelado:
`tomos`, `paginas`, `fallos`, `secciones`, `chunks`, `citas`, `jobs`. Cada una
con `id INTEGER PRIMARY KEY`.

- **Timestamps** en TEXT ISO 8601 UTC (`indexado_at`, `embedding_at`,
  `creado_at`, `iniciado_at`, `terminado_at`).
- **JSON** (`fallos.jueces`, `jobs.payload`) en TEXT; el repo no los interpreta
  todavía.
- **Foreign keys** hacia el padre (`paginas`/`fallos` → `tomos`;
  `secciones`/`chunks`/`citas` → `fallos`; `chunks` → `secciones`) con
  `ON DELETE CASCADE`. Borrar un tomo se lleva sus páginas, fallos, secciones,
  chunks y citas.
- **CHECK** solo sobre los dos vocabularios que el plan congela:
  `tomos.calidad IN ('digital','requiere_ocr','desconocida')` (D-10) y
  `secciones.tipo IN ('mayoria','voto','disidencia','dictamen')` (D-4).
- **UNIQUE**: `tomos.numero`, `tomos.sha256`, `fallos.cita`,
  `paginas(tomo_id, pdf_page)`.
- **Índices** de lookup en las FK y en `chunks.modelo_embedding` (D-7: saber qué
  reindexar), `citas(tomo_citado, pagina_citada)` (grafo de precedentes futuro),
  `jobs.estado` (la cola de PR-03).

### `spectre/db/repo.py` — única puerta al almacenamiento

- **`connect(db_path)`**: abre SQLite con `row_factory = sqlite3.Row`,
  `PRAGMA foreign_keys = ON` (sqlite las trae apagadas por conexión) y
  `PRAGMA journal_mode = WAL`. Crea la carpeta contenedora si falta. El llamador
  pasa una ruta ya anclada por `config` (D-02); `connect` no mira el CWD.
- **`migrate(conn)`**: aplica los `.sql` de `migrations/` que no estén ya en la
  tabla de control `_migraciones (version, aplicada_at)`, en orden de nombre.
  Cada archivo va en su propia transacción (`BEGIN` explícito por delante del
  script, luego el `INSERT` en `_migraciones`, luego `commit`; si algo falla,
  `rollback` — el DDL de SQLite es transaccional). Devuelve la lista de
  versiones aplicadas en esa llamada. Segunda llamada seguida: devuelve `[]`,
  no toca nada, no es error → **idempotencia**.
- **`migraciones_disponibles()`**: los `Path` de `migrations/*.sql` ordenados.
- **Filas tipadas**: `Tomo`, `Pagina`, `Fallo` como `@dataclass(frozen=True,
  slots=True)`. Se construyen con `Clase(**row)` (la `sqlite3.Row` se
  desempaqueta como mapping); los nombres de columna calzan 1:1 con los campos.
- **`Repo(conn)`** con:
  - tomos: `insert_tomo(numero, *, …) -> int`, `get_tomo(id)`,
    `get_tomo_por_numero(numero)`, `list_tomos()` (orden por número),
    `actualizar_tomo(id, **campos)` — `numero` es inmutable y una columna
    inexistente es `ValueError`, no un no-op.
  - páginas: `insert_pagina(tomo_id, pdf_page, *, …) -> int`,
    `get_pagina(tomo_id, pdf_page)`, `list_paginas(tomo_id)` (orden por
    `pdf_page`), `contar_paginas(tomo_id)`.
  - fallos: `insert_fallo(tomo_id, caratula, *, cita=…, …) -> int`,
    `get_fallo(id)`, `get_fallo_por_cita(cita)`, `list_fallos(tomo_id)` (orden
    por `pagina_inicio, id`).
  - Cada escritura hace `commit()` sola: todavía no hay job runner que quiera
    agrupar varias en una transacción (PR-03).

### `spectre/db/__init__.py`

Reexporta `connect`, `migrate`, `migraciones_disponibles`, `Repo`, `Tomo`,
`Pagina`, `Fallo`, `ahora_iso`.

### `spectre/cli.py`

- `db` deja de ser stub. Es un subcomando con dos acciones:
  - `spectre db migrate`: `ensure_dirs()`, `connect(db_path)`, `migrate()`,
    imprime lo aplicado o "sin migraciones pendientes".
  - `spectre db status`: lista `[aplicada]` / `[pendiente]` por migración. Si la
    base no existe **no la crea**: avisa y muestra todo como pendiente. Marca
    `[huérfana]` una versión registrada sin archivo.
- `_PENDIENTES` queda en `{ingest: PR-19, serve: PR-20}`.

### Tests

- **`tests/test_db.py`** (26 tests):
  - migraciones: `migrate` crea las 8 tablas (7 + `_migraciones`); idempotente
    (segunda y tercera llamada → `[]`, dump de `sqlite_master` idéntico, una
    sola fila en `_migraciones`); idempotente también entre conexiones distintas
    sobre el mismo archivo; hay exactamente una migración por ahora.
  - tomos: insert + read completo (el caso de aceptación); `get_*` inexistente →
    `None`; `numero` y `sha256` únicos → `IntegrityError`; `calidad` inválida →
    `IntegrityError` (el CHECK); `list_tomos` ordena; `actualizar_tomo` aplica y
    rechaza `numero` / columnas fantasma; sin campos es no-op.
  - páginas: insert + read; `(tomo_id, pdf_page)` único; FK a tomo inexistente →
    `IntegrityError`; `list`/`contar`; borrar el tomo arrastra las páginas
    (cascade + FK activas).
  - fallos: insert + read; `cita` única pero dos `cita` NULL conviven;
    `list_fallos` ordena por `pagina_inicio`; FK a tomo inexistente.
  - conexión: `foreign_keys` = 1 y `journal_mode` = wal; `connect` crea la
    carpeta contenedora.
- **`tests/test_cli.py`**: saqué `db` del parametrize de "subcomandos vacíos"
  (ahora es real). Agregué: `db migrate` crea la base y nombra `0001_initial`;
  `db migrate` dos veces → "sin migraciones pendientes"; `db status` marca
  pendiente y después aplicada; `db` sin acción es error. Fixture `datos_tmp`
  que redirige `SPECTRE_DATA_DIR` a un tmp y limpia el `lru_cache` de
  `get_settings` antes y después (si no, la config cacheada de otro test se
  filtra).

## Qué decidí por mi cuenta

- **`migrations/0001_initial.sql` en lugar de `db/schema.sql`.** El plan §4
  dibuja `schema.sql`, pero el mismo PR pide "migraciones versionadas". Tener un
  `schema.sql` suelto *más* migraciones son dos fuentes del esquema que se
  desincronizan. La migración 0001 **es** el esquema; futuros cambios entran
  como 0002, 0003. Anotado en el docstring de `repo.py`.
- **Tabla de control `_migraciones`**, no `PRAGMA user_version`. Un entero es
  frágil (no dice qué se aplicó ni cuándo); una tabla con `version` textual y
  `aplicada_at` se lee de un `SELECT` y sobrevive a que alguien numere raro.
- **Creé las 7 tablas ahora**, no solo tomo/página/fallo. El modelo §5 está
  congelado y las tablas de más adelante (`secciones`, `chunks`, `citas`,
  `jobs`) las referencian FKs. Crearlas vacías no cuesta nada y evita una
  migración por tabla. Pero **`repo.py` solo tiene operaciones de
  tomo/página/fallo**, como pide el PR; el resto lo agrega su PR dueño.
- **CHECK solo en `calidad` y `tipo`.** Son los vocabularios que el plan
  congela. `tomos.estado` y `jobs.estado` los definen PR-19 y PR-03; ponerles un
  CHECK adivinado ahora es deuda. Igual con los UNIQUE de dominio de
  `secciones`/`chunks`: los pone el PR que las estrena.
- **`db migrate` / `db status` como acciones de `db`.** El plan no dice qué hace
  `spectre db`. `migrate` es lo mínimo para "crear la base" desde la CLI;
  `status` para ver el estado sin abrir la base a mano. Nada finge trabajo.
- **`db status` no crea la base.** Chequea `db_path.exists()` antes de conectar.
  Un comando de solo-lectura que deja un `spectre.db` vacío de rastro es
  confuso.
- **`WAL` desde ya.** La cola durable de PR-03 lo va a querer (lecturas
  concurrentes con una escritura). No molesta ahora.
- **`jueces` se guarda como TEXT crudo**, sin serializar en el repo. Cómo se
  arma esa lista lo decide PR-08 (metadatos). El repo no adivina el formato.

## En qué me desvié del plan

- `schema.sql` → `migrations/0001_initial.sql` (arriba, con la razón).
- Nada más material. Config + CLI de PR-01 intactas salvo el subcomando `db`,
  que este PR tenía que llenar.
- Actualicé `CLAUDE.md` (sección Comandos y una sección Git nueva) en el mismo
  commit: reflejan que `spectre db` ya existe y anclan los comandos reales del
  venv 3.13 local. No cambia ninguna regla del proyecto.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 15 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 45 passed
```

CLI a mano, con `SPECTRE_DATA_DIR` apuntando a un tmp:

```
spectre db status      # base no existe -> "corré spectre db migrate", 0001 pendiente
                       #   -> NO crea el archivo (verificado con ls)
spectre db migrate     # -> "aplicadas: 0001_initial"
spectre db migrate     # -> "sin migraciones pendientes"  (idempotente)
spectre db status      # -> "[aplicada ] 0001_initial"
```

Objetos creados en la base (SELECT sobre `sqlite_master`):

```
tablas:   tomos paginas fallos secciones chunks citas jobs _migraciones
índices:  idx_paginas_tomo_oficial idx_fallos_tomo idx_secciones_fallo
          idx_chunks_fallo idx_chunks_modelo idx_citas_fallo idx_citas_destino
          idx_jobs_estado + autoindex de cada UNIQUE
```

Idempotencia (el criterio de aceptación): `test_migrate_es_idempotente` llama
`migrate()` tres veces sobre la misma conexión; la 2ª y 3ª devuelven `[]`, el
dump de `sqlite_master` no cambia y `_migraciones` tiene una sola fila.
`test_migrate_sobre_base_ya_migrada_en_otra_conexion` lo repite con dos
conexiones al mismo archivo.

Insert + read de un tomo (el otro criterio): `test_insert_y_leer_tomo` inserta
el Tomo 348 (`calidad='digital'`, `paginas=968`, `offset_pagina=6`) y verifica
cada campo al releerlo, incluido `indexado_at IS NULL`.

## Dudas que quedaron

- **`tomos.estado` sin vocabulario.** Lo dejé como TEXT libre con default
  `'registrado'`. PR-19 (pipeline por etapas) tiene que fijar los valores y
  seguramente sumar un CHECK vía migración 000N. Hasta entonces cualquier
  string entra.
- **`chunks.orden` / `secciones.orden` sin UNIQUE.** No sé todavía si el orden es
  por fallo o por sección. Lo define PR-09 / PR-11; que lo agreguen con su
  migración.
- **`connect()` fuerza WAL siempre.** Sobre `:memory:` es inocuo; sobre archivo
  deja `-wal`/`-shm` al lado (ya gitignored). Si alguna vez se quiere una
  conexión efímera sin WAL habría que parametrizarlo. Hoy nadie lo necesita.
- **`get_settings()` cacheado** vuelve a morder: el test de CLI tuvo que limpiar
  el `lru_cache` a mano. Si más flujos necesitan releer config tras cambiar el
  entorno, conviene exponer un helper de reset en `config.py`. Anotado también
  en la bitácora de PR-01.
- **Consola Windows** sigue mostrando los acentos de la CLI como mojibake por el
  codepage del shell; el fuente es UTF-8 y en CI (Linux) sale bien. Sin tocar.
