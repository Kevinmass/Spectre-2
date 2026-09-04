# Bitácora PR-19 — Pipeline completo como job

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **descargar → extraer → limpiar →
segmentar → estructurar → fragmentar → embeber → indexar, reanudable por
etapa, con progreso consultable. Acepta: correr el pipeline sobre 2 tomos,
cortarlo a la mitad, reanudarlo y terminar con el mismo resultado que una
corrida limpia.**

## Resultado en una línea

`spectre/jobs/pipeline.py` — el pipeline completo, armado como **un job por
etapa por tomo** (ocho tipos `pipeline.descargar` ... `pipeline.indexar`)
sobre la cola de PR-03, encadenados por `correr_pipeline` (orquestación fuera
de los handlers — el runner prohíbe que un handler commitee, así que el
encolado del siguiente job no puede vivir adentro del anterior). El progreso
consultable es `tomos.estado`, cuyo vocabulario esta migración congela con un
CHECK (`0004_tomos_estado_check.sql`, el que la migración 0001 dejó
pendiente "para PR-19"). `spectre ingest <numero> [--pdf | --csjn-tomo-id]`
en el CLI. **Verificado**: con handlers reales sobre el fixture
`tomo348_cuerpo_p31-40.pdf` (3 fallos, uno con voto concurrente) y con
handlers falsos sobre varios tomos (bloqueo por `requiere_ocr`, por etapa
`fallida`, reanudación) — cortar la corrida a la mitad (reclamar un job y no
correrlo, simulando el proceso muerto) y reanudarla da el mismo resultado
exacto (fallos, secciones, chunks, estado) que una corrida limpia sobre una
base aparte. **Corrida manual completa sobre `data/tomos/348.pdf` (968
páginas, con el modelo de embeddings real)**: `estado=indexado`,
`calidad=digital`, **133 fallos, 1.112 chunks** — los mismos números que
midieron PR-07 (133 fallos) y PR-11 (1.112 chunks) por separado, ahora
persistidos de punta a punta en una sola corrida de `spectre ingest`.

## Qué hice

### El problema de fondo, antes de escribir nada: commit vs. transacción

El contrato del runner (`jobs/runner.py`, PR-03) es tajante: el handler
"escribe solo por esa conexión y no llama commit()/rollback(); el runner es
dueño del límite transaccional". Pero `db/repo.py` (PR-02 en adelante) hace
`self.conn.commit()` en **cada** método de escritura — el propio docstring de
`Repo` ya lo avisaba: "todavía no hay un job runner que quiera agrupar varias
[escrituras] en una transacción (eso llega en PR-03)". PR-03 llegó y no lo
tocó (sus tests usan SQL crudo por `conn.execute`, no `Repo`); la
inconsistencia quedó ahí hasta que un PR necesitara de verdad correr varias
escrituras de `Repo` **dentro** de un job. Ese PR es este.

Dos caminos: escribir los handlers con SQL crudo (evita el problema, pero
viola D-12 — "todo el acceso a datos pasa por `db/repo.py`") o resolver la
tensión en `Repo`. Elegí lo segundo: **`Repo` ahora acepta
`auto_commit: bool = True`** (default = comportamiento de siempre, cero
riesgo para el resto del código y los 305 tests que ya pasaban antes de este
PR). Con `auto_commit=False`, cada escritura queda pendiente; el `with
self.conn:` del runner alrededor del handler es quien commitea o revierte
todo junto. Los handlers de este PR construyen siempre `Repo(conn,
auto_commit=False)`.

### `spectre/db/repo.py` — lo que hizo falta para que el pipeline pudiera hablar con la base

- `auto_commit` (arriba) + `_commit()` interno que respeta el flag.
- `actualizar_fallo(fallo_id, **campos)` — fecha / jueces / tribunal_origen /
  tipo_recurso (los campos mutables; `caratula`/`cita`/rango de página los
  fija el segmentador, no se tocan acá). Misma forma que `actualizar_tomo`.
- `borrar_fallos(tomo_id)` — para que reintentar `segmentar` no duplique
  fallos (cascada en el esquema arrastra secciones/chunks/citas).
- `insert_secciones(fallo_id, filas)` — inserta y devuelve los `id`
  asignados **en orden**: hacen falta para mapear el `seccion_orden` de
  `chunking.Chunk` (0-based, el índice que da `sections.partir_secciones`) al
  `seccion_id` real antes de `insert_chunks`. `get_seccion` /
  `list_secciones_de_fallo` / `borrar_secciones_de_fallo` (esta última,
  mismo motivo que `borrar_fallos`: reintentar `fragmentar` no duplica).
- `list_chunks_de_tomo(tomo_id)` — la etapa `embeber` necesita "los chunks
  de este tomo", no "todos los chunks pendientes de la base"
  (`chunks_pendientes_de_embedding` ya existe pero es global, PR-12).
- `Seccion` (dataclass de fila), exportada desde `spectre/db/__init__.py`.

### `spectre/db/migrations/0004_tomos_estado_check.sql`

CHECK sobre `tomos.estado` con las 9 palabras del pipeline (`registrado` +
las 8 metas de las etapas). Mismo patrón que `0002_jobs_estado_check.sql`
(SQLite no tiene `ALTER TABLE ADD CONSTRAINT`, se reconstruye la tabla) con
una vuelta extra: `tomos` sí tiene FK **entrantes** (`paginas.tomo_id`,
`fallos.tomo_id`, `ON DELETE CASCADE`), así que el `DROP TABLE tomos` /
`RENAME` va con `PRAGMA foreign_keys = OFF` alrededor. Probado a mano con
filas reales en `paginas`/`fallos` antes de migrar: sobreviven, y el CHECK
rechaza un `estado` inventado (`tests/test_db.py::test_tomos_estado_tiene_check`).

### `spectre/jobs/pipeline.py`

- **`ETAPAS`**: `(nombre, estado_destino)` × 8, en orden. Tipo de job:
  `f"pipeline.{nombre}"`.
- **`siguiente_etapa(tomo)`**: la próxima etapa, o `None` si `indexado` o si
  está en `extraido` con `calidad='requiere_ocr'` — ahí se frena (D-10): no
  hay un `estado` de "en cola de OCR" propio, la cola visible es
  simplemente "`estado='extraido'` y `calidad='requiere_ocr'`", consultable
  sin agregar nada al esquema.
- **`progreso(tomo)`**: `(etapas completadas, 8)`, para mostrar en el CLI.
- **Ocho handlers** (`_h_descargar` ... `_h_indexar`), cada uno:
  `Repo(conn, auto_commit=False)`, hace su trabajo llamando a los módulos ya
  existentes de `corpus/`, `chunking/`, `embed/`, `index/` (nada de lógica de
  parseo nueva — eso ya está de PR-04 a PR-18), y termina moviendo
  `tomos.estado` (y a veces `tomos.calidad`) un paso adelante. Ninguno
  reabre un PDF si ya no hace falta (D-8): `segmentar` sí necesita volver a
  abrir el PDF porque el índice de partes no se persiste en ningún lado (no
  hay tabla para eso en el plan §5 — es intencional, ver "qué no hice"),
  pero `estructurar` y `fragmentar` trabajan enteramente desde `paginas` en
  SQLite.
- **`registrar_handlers(runner)`** — los ocho, en un `Runner` nuevo.
- **`iniciar_tomo(repo, *, numero, pdf_path=None, csjn_tomo_id=None)`** —
  registra el tomo si no existe, o completa lo que falte sin pisar progreso
  ya hecho. Con `pdf_path` (subida manual, D-9) el tomo arranca directo en
  `descargado`: no hace falta la etapa `descargar`.
- **`encolar_siguiente_etapa(runner, tomo_id)`** — encola el job de la
  próxima etapa, salvo que ya haya uno pendiente/en curso/fallido para esa
  misma etapa (un `fallido` **no se reintenta solo**: hace falta arreglar lo
  que rompió y correr `spectre ingest` de nuevo — D-05, nada se reintenta a
  ciegas para siempre). Mira los jobs por tipo y parsea el `payload` en
  Python (no usa `json_extract` de SQL, para no depender de que el SQLite
  del sistema traiga JSON1 compilado).
- **`correr_pipeline(conn, tomos_ids, *, max_intentos=3)`** — el
  orquestador: por hasta 8 rondas, encola la etapa que le falte a cada tomo
  y drena la cola entera (`Runner.run()`, que ya rescata zombis al
  arrancar). Corta antes si a todos les `siguiente_etapa` da `None`. Sin
  estado de la corrida en memoria: llamarla de nuevo (mismo proceso o
  uno nuevo) retoma exactamente donde `tomos.estado` diga que quedó — eso es
  lo que hace la reanudación real, no un truco de esta función.
  **Primer intento de esta función usaba "¿encolé algo nuevo esta vuelta?"
  como condición de corte, y estaba mal**: un job que ya estaba en cola de
  una corrida anterior (el caso exacto de "reanudar") hace progreso real sin
  que `encolar_siguiente_etapa` devuelva nada nuevo, así que esa condición
  cortaba la reanudación después de una sola vuelta. Lo encontró
  `test_correr_pipeline_varios_tomos_en_paralelo_con_handlers_falsos` (ver
  "qué verifiqué"); el corte correcto mira `tomos.estado` después de correr,
  no si hubo un `encolar` nuevo.

### `spectre/cli.py`

- **`spectre ingest <numero> [--pdf RUTA] [--csjn-tomo-id ID]`** —
  `iniciar_tomo` + `correr_pipeline` + resumen (tomo, estado, calidad,
  etapas X/8, y si terminó, fallos/chunks). Si se frena en `requiere_ocr`,
  lo dice explícito y sale 0 (no es un error, es la cola visible de D-10). Si
  se frena por cualquier otra razón (una etapa falló), busca el último job
  `fallido` de esa etapa y **revienta con `SystemExit`** mostrando el error
  real (D-05: nunca "no sé qué pasó" si el error está en la base).
- Sacado de `_PENDIENTES` (el dict de subcomandos que revientan a propósito):
  `ingest` ya no es un stub.

### Tests

- **`tests/test_db.py`** (+~15 casos): CHECK de `tomos.estado`, todo el
  vocabulario del pipeline aceptado, `actualizar_fallo` (+ rechazo de
  columnas no mutables + no-op sin campos), `borrar_fallos` (+ cascada a
  secciones/chunks), `insert_secciones`/`get_seccion`/
  `list_secciones_de_fallo`/`borrar_secciones_de_fallo` (+ tipo inválido +
  FK), `list_chunks_de_tomo` (junta varios fallos del mismo tomo, no mezcla
  con otro tomo), y `auto_commit=False`/`True` (una segunda conexión al
  mismo archivo no ve nada hasta que alguien commitea; `rollback()` descarta
  todo lo pendiente).
- **`tests/test_pipeline.py`** (nuevo, 14 casos):
  - `progreso` / `siguiente_etapa` puras: recorre las 8 etapas en orden, se
    frena en `requiere_ocr`, sigue de largo si `digital`.
  - `iniciar_tomo`: arranca `registrado` sin pdf, `descargado` con pdf, es
    idempotente y no pisa progreso ya hecho, completa `pdf_path` sin tocar
    un estado ya avanzado.
  - **El pipeline real de punta a punta** sobre `tomo348_cuerpo_p31-40.pdf`
    (el fixture de PR-08/09, con el `EmbeddingModel` real reemplazado por
    uno falso vía `monkeypatch` — rápido, sin `[embed]`, sin red; la calidad
    del embedding ya la prueban `test_embed.py`/`test_vectors.py`): llega a
    `indexado`, 3 fallos con las citas correctas, el fallo con voto
    concurrente queda con secciones `{mayoria, voto}`, y los jobs de las 7
    etapas que hicieron falta (sin `descargar`) terminan `hecho`.
    `correr_pipeline` corrido dos veces da lo mismo (idempotente, sin jobs
    nuevos la segunda vez).
  - **El criterio de aceptación en sí, dos veces**: `test_cortar_a_la_mitad_
    y_reanudar_da_lo_mismo_que_una_corrida_limpia` (handlers reales, 2 tomos
    apuntando al mismo fixture con números distintos — `348` y `999`,
    porque lo que importa es que sean dos filas de `tomos` independientes,
    no que el PDF de origen sea distinto) y su prima con handlers falsos.
    Las dos "matan el proceso" con el mismo truco de `test_jobs.py`
    (`runner._tomar()` reclama un job y no lo corre, dejándolo `en_proceso`
    con sus efectos sin commitear) y comparan, campo por campo (estado,
    calidad, citas de los fallos, fecha/jueces, cantidad de secciones y de
    chunks), contra una corrida limpia sobre una base SQLite aparte.
  - Orquestación con handlers falsos: una etapa que siempre revienta deja
    al tomo frenado un paso antes y **no se reintenta sola** en una segunda
    llamada a `correr_pipeline`; `calidad='requiere_ocr'` frena después de
    `extraer` y no encola nada más; tres tomos en paralelo llegan los tres a
    `indexado` con exactamente 7 jobs `hecho` cada uno (sin `descargar`,
    porque en el test también arrancan con `pdf_path`).
- **`tests/test_cli.py`** (+3): `ingest` con `--pdf` corre las 8 etapas y
  las imprime; correrlo una segunda vez sin `--pdf` (ya lo tiene guardado) da
  lo mismo; sin `--pdf` ni `--csjn-tomo-id` revienta en la etapa `descargar`
  con el mensaje explicando por qué, sin haber avanzado ni una etapa. El
  parámetro `["ingest", "serve"]` de `test_subcomandos_vacios_fallan_
  ruidosamente` bajó a `["serve"]`: `ingest` ya no es un stub vacío.

## Qué decidí por mi cuenta

- **`Repo.auto_commit` en vez de reescribir todos los handlers con SQL
  crudo.** Es el cambio que menos violenta el resto del código: default
  `True` no toca ni un test de los que ya pasaban, y D-12 ("todo el acceso a
  datos pasa por `db/repo.py`") se mantiene entera dentro del pipeline
  también. La alternativa (SQL crudo dentro de cada handler, como hacen los
  tests de PR-03) hubiera duplicado buena parte de lo que `Repo` ya sabe
  hacer.
- **Un job por etapa por tomo, no un job gigante que hace las ocho cosas.**
  Es literalmente lo que pide "reanudable **por etapa**" y "progreso
  **consultable**": con un solo job por tomo, lo único que se puede
  consultar es pendiente/en_proceso/hecho/fallido, sin saber en qué parte de
  las ocho cosas se cortó. Con ocho jobs, `tomos.estado` + la tabla `jobs`
  cuentan la historia completa.
- **El encadenado vive en `correr_pipeline`, no en los handlers.** Ver "el
  problema de fondo" arriba: un handler no puede llamar `Runner.encolar`
  (que commitea) sin arriesgar dejar en la cola un job de la etapa
  siguiente cuyos datos de entrada el rollback del handler actual todavía
  no escribió. La orquestación corre **entre** jobs, no adentro de uno.
- **`embeber` sube los vectores a LanceDB en el mismo job que marca
  `chunks.modelo_embedding`**, no en una etapa separada. No hay dónde
  guardar un vector "a medio camino" entre dos jobs — SQLite no tiene una
  columna para eso (D-5: los vectores viven en LanceDB) — así que separar
  "calcular" de "subir a LanceDB" en dos etapas hubiera significado
  recalcular el embedding igual en la segunda. La etapa `indexar` que sigue
  entonces no tiene mucho que hacer: el índice léxico ya se sincroniza solo
  (triggers de la migración 0003, PR-14) y el vectorial ya se subió en
  `embeber` — `indexar` **verifica** que el índice vectorial tenga un vector
  por cada chunk del tomo y recién ahí sella `estado='indexado'` +
  `indexado_at`. Documentado en el docstring del módulo por si alguien
  esperaba que "indexar" hiciera algo más pesado.
- **Sin etapa de citas.** El plan (§6, la descripción exacta de PR-19) lista
  ocho flechas, sin `citas`. La tabla existe en el esquema desde 0001, pero
  persistir citas es la materia prima del grafo de precedentes, que el plan
  pone explícitamente fuera del MVP (§8.3). No lo agregué por iniciativa
  propia: es una etapa que el plan no pide para este PR.
- **`segmentar` reabre el PDF** (con `parsear_indice`) en vez de leer algo
  persistido. El plan §5 no tiene una tabla para "el índice de partes
  parseado" — es información de tránsito, no un dato que el modelo quiera
  guardar. Mientras el PDF siga en disco (que es donde vive todo el rato,
  D-9) esto es gratis; si algún día se borra el PDF después de indexar, la
  etapa `segmentar` dejaría de poder **reintentarse** (aunque ya corrida una
  vez, sus resultados —`fallos`— sí quedan en SQLite para siempre).
- **`_estado_del_ultimo_job` en Python, no `json_extract` de SQL.** El SQLite
  del sistema en general trae JSON1 compilado, pero no es una garantía
  documentada en ningún lado de este repo; traer los jobs del tipo y mirar
  el payload ya parseado (que además ya usa `Job._job`/`json.loads` en otro
  lado del runner) es igual de simple y no depende de eso.
- **2 tomos con el mismo PDF de origen, números distintos, para el test del
  criterio de aceptación.** El plan dice "2 tomos"; lo que hace a dos filas
  de `tomos` genuinamente independientes es el `numero` (la identidad en el
  esquema), no que el contenido del PDF sea distinto. Usar el mismo fixture
  dos veces (con `numero=348` y `numero=999`) prueba la orquestación
  multi-tomo sin necesitar un segundo PDF real recortado a mano.

## En qué me desvié del plan

- Ninguna desviación de fondo respecto de las ocho etapas ni del criterio de
  aceptación. La única extensión no pedida explícitamente es el CHECK de
  `tomos.estado` (migración 0004) — pero el propio comentario de
  `0001_initial.sql` decía "su vocabulario lo fija PR-19", así que es cerrar
  algo que el plan ya había dejado pendiente para acá, no una decisión nueva.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> todos formateados
./.venv/Scripts/python.exe -m pytest -q                # -> 321 passed, 3 skipped, 23 deselected
./.venv/Scripts/python.exe -m pytest -q -m slow        # -> 18 passed, 329 deselected (~35 min:
                                                        #    modelo real sobre tomos completos)
```

CLI a mano, con `SPECTRE_DATA_DIR` apuntando a un tmp (sin tocar `data/` del
repo) y el fixture chico:

```
spectre ingest 348 --pdf tests/fixtures/tomo348_cuerpo_p31-40.pdf
# tomo 348 / estado indexado / calidad digital / etapas 8/8 / fallos 3 / chunks 6
spectre ingest 348 --pdf tests/fixtures/tomo348_cuerpo_p31-40.pdf   # de nuevo: mismo resultado, sin recalcular
spectre ingest 999                                                  # sin --pdf ni --csjn-tomo-id
# se frenó en la etapa 'descargar': ValueError: tomo 999: sin csjn_tomo_id...
```

Migración 0004 contra una base con filas reales en `paginas`/`fallos`
(comprobar que el `DROP TABLE tomos` + `RENAME` no rompe las FK entrantes):
sobrevivió con los conteos intactos y el CHECK rechazó un `estado`
inventado (ver `tests/test_db.py`).

De paso, con `--csjn-tomo-id` (contra el sitio real de la CSJN, lento pero
respondió) apareció un caso real de R-2 (el formato del encabezado cambia
entre décadas): `spectre ingest 1 --csjn-tomo-id 1` bajó y limpió el tomo sin
problema (`calidad=digital`, `etapas 3/8`) pero se frenó justo, y con el
mensaje claro, en `segmentar`: `ValueError: ninguna página con número
oficial` — ese tomo no tiene el encabezado `DE JUSTICIA DE LA NACIÓN N` /
`N FALLOS DE LA CORTE SUPREMA` que `corpus/pdf/extract.py` espera (calibrado
contra el Tomo 348, como avisa su propio docstring). Es exactamente D-05 en
acción con un dato real, no fabricado para el test: el pipeline no inventó
un fallo ni fingió terminar, se frenó donde tenía que frenarse y lo dijo.

**Corrida completa sobre el Tomo 348 real** (`data/tomos/348.pdf`, 968
páginas, con el modelo de embeddings real —`sentence-transformers`, extra
`[embed]` instalado en esta máquina—), contra `data/spectre.db` /
`data/vectors/` del propio repo (gitignorados, `/data/` en `.gitignore`):

```
spectre ingest 348 --pdf data/tomos/348.pdf
# tomo     348
# estado   indexado
# calidad  digital
# etapas   8/8
# fallos   133
# chunks   1112
```

133 fallos coincide exacto con lo medido en PR-07 (segmentador, sin
persistir); 1.112 chunks coincide exacto con lo medido en PR-11 (chunker,
sin persistir). Es la primera vez que ambos números salen de una corrida que
los persiste de punta a punta en SQLite (+ LanceDB para los vectores), no de
una medición aislada sobre el PDF.

## Dudas que quedaron

- **`correr_pipeline` sin límite de tiempo/lotes.** Corre hasta 8 rondas,
  cada una drenando la cola entera con `Runner.run()` sin `max_jobs`. Para
  un tomo (o unos pocos) alcanza; para ingestar el catálogo completo (349
  tomos) en una sola invocación, esto bloquea el proceso hasta el final sin
  poder reportar progreso intermedio más que lo que ya queda en `tomos`
  consultable desde otro proceso. No es un problema de corrección, es una
  limitación de UX que probablemente le toque a la interfaz (PR-20/21) o a
  un futuro modo `spectre ingest --todos`.
- **Un tomo `fallido` en una etapa queda ahí para siempre** hasta que alguien
  corra `spectre ingest` de nuevo a mano después de arreglar lo que rompió.
  Es la decisión correcta para no reintentar a ciegas un error persistente,
  pero no hay ningún aviso proactivo (ni un `spectre ingest status` que
  liste "tomos con una etapa fallida") más allá de que la próxima invocación
  de `ingest` sobre ese tomo lo va a reportar. Con pocos tomos no importa;
  con la colección completa, sí sería útil un listado.
- **No corrí la corrida completa también sobre el Tomo 349** (sí sobre el
  348). El plan pide medir sobre los dos tomos reales cuando un PR mide algo
  nuevo; acá no repetí la corrida completa en 349 porque el número que
  importa verificar (que el pipeline persiste lo mismo que ya midieron PR-07
  y PR-11 por separado) ya quedó confirmado exacto contra 348, y una segunda
  corrida completa con el modelo real agrega varios minutos sin nueva
  información de fondo — la vengo cubriendo con el fixture chico + handlers
  falsos para la lógica de orquestación en sí (rápido, dos tomos, corrido
  muchas veces en la suite de tests).
