# Bitácora PR-03 — Runner de jobs durable

Fecha: 03/09/2026
Criterio de aceptación (plan §6): cola en SQLite, un solo proceso, estados y
reintentos, sin threads ni control de recursos casero. Matar el proceso a mitad
de un job y reanudarlo **sin perder ni duplicar** trabajo. Test que lo
demuestre.

Rama apilada sobre `pr-02-esquema-sqlite` (usa `spectre.db` y la tabla `jobs`).
El PR apunta a esa rama; GitHub lo reapunta a `main` cuando PR-02 mergee.

## Qué hice

### `spectre/jobs/runner.py`

Una cola durable sobre la tabla `jobs` (ya creada en la migración 0001) y un
runner de un solo hilo.

**Ciclo de un job:** `pendiente → en_proceso → hecho | fallido`.

- **`Runner(conn, *, max_intentos=3)`** — trabaja sobre una conexión ya migrada
  (mismo patrón que `Repo`). `max_intentos < 1` es `ValueError`.
- **`registrar(tipo, handler)`** — un handler por tipo de job;
  `handler(conn, job)`. Registrar dos veces el mismo tipo es `ValueError`.
- **`encolar(tipo, payload=None)`** — inserta un job `pendiente`, `payload` como
  JSON en TEXT (default `{}`), `intentos = 0`. Devuelve el id.
- **`get(job_id)`** / **`contar_por_estado()`** — lectura; `contar_por_estado`
  es lo que PR-19 va a usar para "progreso consultable".
- **`recuperar_zombis()`** — jobs que quedaron `en_proceso` porque el proceso
  anterior murió: vuelven a `pendiente` (o a `fallido` si ya no quedan
  reintentos). Devuelve cuántos tocó. `run()` la llama sola al arrancar.
- **`run(*, max_jobs=None)`** — `while` que reclama el `pendiente` más viejo, lo
  procesa y sigue, hasta vaciar la cola (o hasta que `max_jobs` jobs lleguen a
  estado terminal). Devuelve cuántos terminaron (`hecho` o `fallido`) en esta
  corrida; los reintentos no suman hasta que se resuelven. **Sin threads, sin
  pool, sin mirar RAM/CPU** (D-06).

**Cómo garantiza "sin perder ni duplicar":**

1. **Reclamar** (`_tomar`): `UPDATE ... estado='en_proceso', iniciado_at=now,
   intentos=intentos+1` **y commit**. Es lo único que queda si el proceso muere
   inmediatamente después. Un solo proceso toca la tabla (decisión del plan),
   así que `SELECT id … LIMIT 1` + `UPDATE` + `commit` alcanza para reclamar sin
   carrera; no hace falta `BEGIN IMMEDIATE` ni RETURNING.
2. **Correr el handler y marcar `hecho` en una sola transacción**
   (`with self.conn:` alrededor de `handler(conn, job)` + el `UPDATE` a
   `hecho`). Si el proceso muere antes del commit, SQLite descarta esa
   transacción entera: los efectos del handler **y** la marca se van juntos. El
   job queda `en_proceso`.
3. **Al reanudar**, `recuperar_zombis()` devuelve ese job a `pendiente` y se
   reprocesa **desde cero**. No se perdió (seguía en la cola); no se duplicó
   (los efectos a medio hacer se descartaron con la transacción).

**Contrato del handler** (docstring del módulo y de `registrar`): escribe solo a
través de la `conn` que recibe y **no llama `commit()`/`rollback()`** — el
runner es dueño del límite transaccional. Un handler que commitea rompe la
garantía de "sin duplicar".

**Reintentos:** si el handler lanza una excepción, `with self.conn` hace
rollback y el runner decide: si a `job.intentos` (ya incrementado por el
reclamo) le quedan intentos, vuelve a `pendiente` con el error guardado; si no,
`fallido`. `max_intentos` cuenta **corridas**, incluidas las que abortó una
caída — así un job que revienta el proceso una y otra vez no deja la cola
girando para siempre.

**Tipo sin handler:** no traba la cola. El job va directo a `fallido` con
`"sin handler para el tipo 'X'"` y el runner sigue. Es un error de cableado
visible, no un stub que finge éxito (D-05).

### `spectre/jobs/__init__.py`

Reexporta `Runner`, `Job`, `Handler`, los estados (`PENDIENTE`, `EN_PROCESO`,
`HECHO`, `FALLIDO`) y `TERMINALES`.

### `spectre/db/migrations/0002_jobs_estado_check.sql`

La bitácora de PR-02 dejó anotado que PR-03 fijaría el vocabulario de
`jobs.estado` y "seguramente" sumaría un CHECK. Lo sumo:
`CHECK (estado IN ('pendiente','en_proceso','hecho','fallido'))`.

SQLite no tiene `ALTER TABLE ADD CONSTRAINT`, así que la migración reconstruye
la tabla: `CREATE jobs_nueva` (con el CHECK) → `INSERT … SELECT` con lista de
columnas explícita → `DROP jobs` → `RENAME`. `jobs` no tiene FKs entrantes, así
que no hay que tocar `PRAGMA foreign_keys` (que además no se puede cambiar
dentro de la transacción que envuelve cada migración). Verificado a mano: sobre
una base que sólo tiene 0001, `migrate()` aplica sólo 0002, preserva las filas
de `jobs` y el CHECK queda activo.

### Tests

- **`tests/test_jobs.py`** (18 tests):
  - **`test_proceso_muerto_a_mitad_reanuda_sin_perder_ni_duplicar`** — el
    criterio de aceptación, con un **subproceso real**. `tests/_job_worker.py`
    reclama el job, el handler inserta una fila en `_efectos` (sin commitear) y
    se cuelga en `time.sleep(60)`; el test espera a que aparezca el archivo
    marker, manda `proc.kill()` (SIGKILL en POSIX, `TerminateProcess` en
    Windows — caída sin `finally` ni atexit) y `proc.wait()`. Después, en este
    proceso: el job quedó `en_proceso` con `intentos=1` y `_efectos` **vacía**
    (el INSERT sin commit se descartó); reanuda con `Runner.run()`, el handler
    corre **una sola vez**, `_efectos` tiene **una** fila con el dato correcto,
    el job queda `hecho` con `intentos=2`. Corrido 3 veces seguidas sin
    flakiness (~0,4 s).
  - `test_reclamo_sin_terminar_se_reanuda_una_sola_vez` — la misma idea
    in-process y determinista: `_tomar()` (el proceso "muere" ahí), después un
    `Runner` nuevo sobre el mismo archivo procesa el job una vez y no duplica.
  - `test_los_efectos_de_un_intento_fallido_se_descartan` — handler que escribe
    y después lanza: `_efectos` queda vacía (rollback), job `fallido`.
  - reintentos: `test_reintenta_hasta_max_y_termina_fallido` (handler que
    siempre falla → 3 corridas, `intentos=[1,2,3]`, `fallido` con el error);
    `test_exito_despues_de_un_fallo_limpia_el_error` (falla la 1ª, anda la 2ª →
    `hecho`, `intentos=2`, `error` a NULL, un solo efecto).
  - zombis: `recuperar_zombis` vuelve a `pendiente`; si agotó intentos →
    `fallido`; `run()` arranca rescatando.
  - básicos: encolar crea `pendiente`/`intentos=0`/payload round-trip; FIFO por
    id; `run()` vacío → 0; no reprocesa lo hecho; efectos del handler se
    commitean; tipo sin handler → `fallido` sin trabar la cola;
    `contar_por_estado`; `max_intentos=0` y doble `registrar` → `ValueError`.
- **`tests/_job_worker.py`** — helper del test de caída. El guion bajo lo
  mantiene fuera de la colección de pytest.
- **`tests/test_db.py`** — actualizado para las 2 migraciones (`MIGRACIONES`
  como constante); nuevo `test_jobs_estado_tiene_check`.

## Qué decidí por mi cuenta

- **Rama apilada sobre PR-02**, no sobre `main`. PR-03 usa `spectre.db`, que
  vive en PR-02 sin mergear. Alternativa era esperar el merge; Kevin pidió
  seguir. El PR apunta a `pr-02-esquema-sqlite`.
- **Sin subcomando de CLI para el runner.** El plan no nombra ninguno para
  PR-03. Un `spectre jobs run` sin handlers reales no puede procesar nada — o
  sería un handler de demo, que es exactamente el stub que el proyecto prohíbe.
  La superficie de jobs (encolar el pipeline, ver progreso) aparece natural en
  PR-19. Por ahora el runner es infraestructura que consume PR-19; los tests lo
  ejercen de punta a punta, incluida una caída de proceso real (espíritu de
  D-03: verlo procesar algo de verdad).
- **`intentos` se incrementa al reclamar, no al terminar.** Así una caída del
  proceso *consume* un intento. Un handler que segfaultea el proceso siempre no
  deja la cola en loop infinito: a los `max_intentos` reclamos, `recuperar_zombis`
  lo manda a `fallido`. El costo: un job que cayó por una razón ajena (corte de
  luz) gasta un intento igual. Me parece el lado correcto del trade.
- **El runner es dueño de la transacción, el handler no commitea.** Es lo que
  hace que "matar a mitad" no duplique: efectos + marca `hecho` caen juntos. Lo
  puse en el contrato (docstrings) porque no se puede forzar sin envolver la
  conexión en un proxy, que es más maquinaria de la que amerita hoy.
- **Tipo sin handler → `fallido`, no excepción que corta `run()`.** Una cola
  durable no se traba por un mensaje que no sabe procesar. `fallido` con el
  motivo es honesto y visible.
- **CHECK en `jobs.estado` vía reconstrucción de tabla.** La bitácora de PR-02
  lo dejó como "seguramente"; lo cumplo. Son 5 statements, todos
  transaccionales, y `jobs` no tiene FKs entrantes, así que la reconstrucción es
  barata y segura.
- **`_tomar` sin `BEGIN IMMEDIATE` ni `RETURNING`.** Un solo proceso (decisión
  del plan) hace que SELECT+UPDATE+commit sea suficiente y portable. Si algún
  día se corren varios procesos —el plan dice que no— habría que volver acá.

## En qué me desvié del plan

- **Encadené PR-03 con PR-02 en la misma sesión**, contra "un PR por sesión, no
  encadenar dos" (`CLAUDE.md` / plan §1). A pedido explícito de Kevin en el
  chat, con PR-02 ya abierto y en verde. Igual que PR-01 sobre PR-00.
- **Migración 0002 no listada en el plan.** El plan §6 de PR-03 habla de la
  cola, no de tocar el esquema. La agrego porque la bitácora de PR-02 la dejó
  pendiente y es el lugar donde el vocabulario de `jobs.estado` queda fijo.
- Nada más. La cola, el proceso único, los estados y los reintentos están; el
  test de caída es real.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 19 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 64 passed
```

El test de aceptación, corrido aislado 3 veces seguidas:

```
./.venv/Scripts/python.exe -m pytest \
  "tests/test_jobs.py::test_proceso_muerto_a_mitad_reanuda_sin_perder_ni_duplicar" -q
# -> 1 passed  (x3, ~0,4 s cada una, sin flakiness)
```

Runner de punta a punta a mano:

```
spectre db migrate         # aplica 0001_initial y 0002_jobs_estado_check
spectre db status          # ambas [aplicada]
# Runner: encolar 2 jobs 'saludar', run() -> terminados: 2, log: ['mundo','corte'],
#   estados: {'hecho': 2}
```

Migración 0002 sobre una base con sólo 0001 (el caso del que ya corrió PR-02 y
actualiza): `migrate()` -> `['0002_jobs_estado_check']`, las filas de `jobs`
preexistentes se preservan, y un INSERT con `estado='raro'` pasa a tirar
`IntegrityError`.

## Dudas que quedaron

- **El contrato "el handler no commitea" no está forzado.** Si un handler llama
  `conn.commit()` a mitad, parte de sus efectos quedan y la garantía de "sin
  duplicar" se rompe para ese job. Hoy confío en el docstring. Si aparecen
  muchos handlers, conviene pasarles una vista de la conexión que capea
  `commit`/`rollback`.
- **`payload` se parsea con `json.loads` sin validar esquema.** Cada handler ve
  un `dict` y saca lo que necesita; un payload mal formado revienta dentro del
  handler y cae en la lógica de reintentos. Cuando PR-19 defina tipos de job
  concretos quizás quiera validación por tipo.
- **`recuperar_zombis` corre en `run()`; no hay un `spectre jobs recover`
  suelto.** Mientras el único punto de entrada al runner sea `run()`, alcanza.
  PR-19/PR-23 (UI con progreso) capaz quieran exponerlo.
- **Un job "envenenado" que hace fallar al proceso** (no una excepción, una
  caída dura) se reintenta `max_intentos` veces gastando una caída de proceso
  por intento. Es lo correcto pero puede ser molesto de operar; queda para
  cuando haya jobs reales que lo disparen.
- **Concurrencia entre `run()` y lectores** (una futura UI que consulta
  `contar_por_estado` mientras el runner trabaja): WAL lo permite y el runner
  hace transacciones cortas, pero no lo probé con un lector concurrente de
  verdad. Entra cuando exista ese lector (PR-23).
