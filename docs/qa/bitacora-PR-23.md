# Bitácora PR-23 — Biblioteca

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **Tomos disponibles, cuáles están
indexados, cuáles requieren OCR, progreso de indexación, botón para indexar
y para subir un PDF propio. Acepta: lanzar la indexación de un tomo desde la
UI y ver el progreso.**

## Resultado en una línea

`POST /api/tomos/{numero}/indexar` (por `csjn_tomo_id`, D-9) y `POST
/api/tomos/{numero}/subir` (PDF a mano, D-9) registran el tomo al toque
(202) y arrancan `jobs.correr_pipeline` (PR-19) **en segundo plano** con
`BackgroundTasks` de Starlette, así el servidor no se bloquea los minutos
que puede tardar el pipeline con el modelo real. `GET /api/estado` (PR-20)
ahora suma, por tomo, cuántas etapas completó y el error de la última si
falló una. `spectre/web/`: la pestaña Biblioteca sondea `/api/estado` cada
2 segundos mientras está a la vista y tiene los dos formularios para lanzar
una indexación. **Verificado contra un `spectre serve` real** (no
`TestClient`, que ejecuta las tareas de fondo de forma síncrona y hubiera
ocultado justo lo que hay que probar acá): subir un PDF por `curl` devuelve
202 al instante, y sondeando `/api/estado` en paralelo mientras el servidor
seguía respondiendo otras requests, el tomo avanzó solo de `descargado`
(1/8) a `indexado` (8/8) sin que la subida bloqueara nada.

## Qué hice

### El problema de fondo: el pipeline es lento y el servidor es un solo proceso

`spectre ingest` (CLI, PR-19) corre `correr_pipeline` de punta a punta y
bloquea hasta terminar — aceptable en una terminal, donde el usuario ya sabe
que está esperando. Un handler HTTP que hiciera lo mismo dejaría a
`spectre serve` sin poder atender **ninguna otra request** (ni la del
`/api/estado` que la propia página de Biblioteca necesita para mostrar el
progreso) durante los minutos que tarda un tomo con el modelo real —
inaceptable para "ver el progreso" en tiempo real.

La solución: `BackgroundTasks` de Starlette (`fastapi.BackgroundTasks`).
`background_tasks.add_task(func, *args)` con `func` sincrónica corre en el
threadpool que ya trae el framework (`anyio.to_thread.run_sync` por debajo)
**después** de que la respuesta ya se mandó — no es un worker casero (D-06:
"sin control de recursos casero, sin threads" es sobre no reimplementar
supervisión de procesos/límites de memoria, no sobre no usar la
infraestructura estándar de FastAPI para no bloquear el event loop). Lo
verifiqué antes de construir nada: un experimento con
`time.sleep(0.5)` en una tarea de fondo confirma que `TestClient.post()`
**sí espera** a que la tarea termine antes de devolver el control (útil
para tests deterministas, sin sleeps ni polling) — pero contra un servidor
real (`uvicorn`), la respuesta HTTP vuelve al cliente antes de que la tarea
de fondo corra, y el event loop queda libre para atender otras requests
mientras tanto. Las dos cosas las medí, no las asumí (ver "qué verifiqué").

### `spectre/api/app.py`

- **`_tomo_a_dict(conn, tomo)`**: arma el dict de cada tomo para
  `/api/estado` — `numero`/`estado`/`calidad` (como antes) más
  `etapas_hechas`/`etapas_total` (`jobs.progreso`, ya existía desde PR-19) y
  `error` (`_error_de_etapa_fallida`, nuevo).
- **`_error_de_etapa_fallida(conn, tomo)`**: mismo query que ya usaba
  `cli._cmd_ingest` desde PR-19 (`SELECT error FROM jobs WHERE tipo = ? AND
  estado = 'fallido' ORDER BY id DESC LIMIT 1` sobre `f"pipeline.{etapa}"`,
  con `etapa` la próxima que le falta al tomo) — hasta esta sesión vivía
  solo en el CLI; PR-23 la necesita también en la API para que la UI pueda
  mostrar "esta etapa falló" en vez de un progreso trabado sin explicación.
  Un tomo frenado por `requiere_ocr` (D-10) no tiene "próxima etapa" —
  `siguiente_etapa` devuelve `None` — así que nunca cae en esta rama:
  requiere OCR no es un error, es la cola visible de D-10.
- **`POST /api/tomos/{numero}/indexar`**: `iniciar_tomo` (síncrono, rápido:
  un insert/update) + `background_tasks.add_task(_correr_pipeline_en_fondo,
  s.db_path, tomo_id)`. Responde 202 con el estado del tomo **tal como
  quedó después de registrarlo**, antes de que el pipeline avance nada — es
  la foto de "se aceptó el pedido", no "ya terminó".
- **`POST /api/tomos/{numero}/subir`**: `async def` (necesita `await
  archivo.read()`); guarda el PDF en `tomos_dir/{numero}.pdf` (mismo nombre
  que arma `_h_descargar`, PR-19) y de ahí en más es idéntico a `/indexar`
  pero con `pdf_path` en vez de `csjn_tomo_id` — el tomo arranca directo en
  `descargado` (D-9, misma lógica que `iniciar_tomo` ya tenía). Valida que
  el nombre del archivo termine en `.pdf` (400 si no); no valida el
  contenido — si no es un PDF de verdad, `extraer_texto` (PR-04) va a
  reventar en la etapa `extraer` con un error claro, que `/api/estado` va a
  mostrar igual que cualquier otra etapa fallida.
- **`_correr_pipeline_en_fondo(db_path, tomo_id)`**: función de módulo (no
  vive en el closure de `crear_app`, no necesita estado compartido). Abre
  su **propia** conexión SQLite — la del request ya se cerró para cuando
  esto corre — y llama `correr_pipeline`, el mismo que usa `spectre ingest`.

### `spectre/web/` — Biblioteca con progreso y dos formularios

- `index.html`: cuarta columna "Progreso" en la tabla; dos `<form>` debajo
  (`form-indexar-csjn`: número + `csjn_tomo_id` opcional; `form-subir-pdf`:
  número + archivo) y un `<p id="biblioteca-aviso">` para el resultado de
  la acción.
- `app.js`:
  - `activarTab` ahora arranca/corta un `setInterval(cargarEstado, 2000)`
    al entrar/salir de la pestaña Biblioteca — nadie necesita seguir
    pidiendo `/api/estado` cada 2 segundos mientras mira Buscar o un fallo.
  - `renderProgresoTomo(tomo)`: "`hechas`/`total`" siempre, más una nota
    si `calidad === "requiere_ocr"` (D-10: se frenó a propósito, no es un
    error) o el mensaje de `tomo.error` si lo hay (color de aviso, mismo
    `--error` que ya usaba el badge de disidencia).
  - `indexarDesdeCsjn` / `subirPdf`: `fetch` a la ruta correspondiente,
    aviso de "Registrando…"/"Subiendo…" mientras espera, botón deshabilitado
    durante el request (evita doble-click), y en caso de error el `detail`
    que mandó FastAPI (no un genérico "algo salió mal").

### Tests

- **`tests/test_api.py`** (+18 sobre PR-22): progreso a medio camino
  (`etapas_hechas` correcto para un tomo en `estructurado`); error de una
  etapa fallida armado a mano (inserto un job `fallido` directo por SQL,
  igual que hacen `test_db.py`/`test_pipeline.py`) reflejado en
  `/api/estado`; `requiere_ocr` **no** se confunde con un error;
  `/indexar` responde 202 con el registro inicial; sin `csjn_tomo_id` falla
  en `descargar` y el error queda visible; con `descargar_tomo` mockeado
  (copia el fixture chico a destino, mismo patrón de `monkeypatch.setattr`
  que ya usa el resto del archivo) + modelo de embeddings falso, el tomo
  llega a `indexado` (8/8, 6 chunks); `/indexar` es idempotente sobre un
  tomo ya registrado (no lo duplica); `/subir` rechaza un archivo que no
  termina en `.pdf` (400); `/subir` con el fixture real y modelo falso
  llega a `indexado`, arranca en `descargado` (saltea `descargar`, D-9), y
  el archivo queda de verdad en `data/tomos/{numero}.pdf` (en el tmp del
  test, no el del repo).

## Qué decidí por mi cuenta

- **`BackgroundTasks` de Starlette, no un job runner nuevo ni un thread
  manual.** Alternativas descartadas: (a) correr el pipeline síncrono
  dentro del handler — bloquea el servidor entero, inaceptable para "ver el
  progreso"; (b) un poller separado del lado del cliente que dispare
  `spectre ingest` como subproceso — agrega una superficie nueva (manejo de
  subprocesos, captura de su salida) para resolver algo que FastAPI ya
  resuelve con una función de su API pública. `BackgroundTasks` es la
  respuesta idiomática de FastAPI a "correr algo después de responder sin
  bloquear", no una pieza de infraestructura que este PR construye.
- **No hay forma de reintentar una etapa fallida desde la UI — y **no
  hice** que pareciera que la hay.** Antes de diseñar el botón "Indexar"
  leí el propio test de PR-19
  (`test_correr_pipeline_no_reintenta_solo_una_etapa_fallida`,
  `tests/test_pipeline.py`) para confirmar el comportamiento real: si la
  última corrida de una etapa quedó `fallido`,
  `encolar_siguiente_etapa` la salta para siempre — ni `spectre ingest` ni
  este PR la reintentan solos. Clickear "Indexar" de nuevo sobre un tomo
  trabado no hace nada (es un no-op seguro, no un error), y `/api/estado`
  muestra el error para que quien mira sepa por qué no avanza. No armé un
  mecanismo de reintento (borrar el job fallido, forzar un nuevo intento)
  porque el plan no lo pide para este PR y es una pieza de diseño con su
  propio peso (¿reintenta desde cero la etapa, o asume que "lo que rompió"
  ya se arregló afuera?) — mejor dejarla para cuando haga falta de verdad,
  documentada acá como hallazgo, no resuelta a las apuradas.
- **Sin catálogo de la CSJN embebido en la UI.** El formulario de "Indexar
  desde la CSJN" pide `csjn_tomo_id` a mano, con una nota apuntando a
  `spectre csjn catalog` (PR-16) para conseguirlo. Traer el catálogo real a
  la UI (con paginación, quizás una tabla filtrable) es una pieza de
  trabajo bastante más grande que "lanzar una indexación y ver el
  progreso" — el criterio de aceptación no pide poder *buscar* qué tomos
  existen, solo poder *indexar* uno. Además el catálogo pega contra el
  sitio real de la CSJN (marcado `red` en los tests, PR-16): meterlo en el
  flujo principal de la UI ata la experiencia de Biblioteca a que ese sitio
  esté arriba, algo que hoy no depende de nada más.
- **La validación de "es un PDF" en `/subir` es superficial (extensión del
  nombre), no de contenido.** Un archivo con extensión `.pdf` que en
  realidad no lo es va a reventar en `extraer` (PR-04), con un error
  específico visible en `/api/estado` — es D-05 en acción (falla ruidoso,
  no silencioso), no hacía falta duplicar esa validación acá.

## En qué me desvié del plan

Ninguna desviación de fondo. El plan describe PR-23 en una frase ("tomos
disponibles, cuáles están indexados, cuáles requieren OCR, progreso de
indexación, botón para indexar y para subir un PDF propio") sin especificar
mecanismo de background ni forma de la API — las decisiones de diseño no
prescriptas explícitamente (`BackgroundTasks`, sin catálogo embebido, sin
reintento de etapas fallidas) están justificadas arriba.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Nueva dependencia dura:
`python-multipart>=0.0.9` (FastAPI la necesita para `UploadFile`/formularios
multipart) — instalada con `pip install -e ".[dev]"` (0.0.32 resuelta).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 85 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 358 passed, 3 skipped, 23 deselected
```

**Contra un `TestClient`**, que ejecuta las tareas de fondo de forma
síncrona (lo comprobé antes de escribir los tests: un experimento con
`time.sleep(0.5)` en una background task muestra que `client.post()` tarda
esos 0.5 s y el log confirma el orden `response-returned` → `start` →
`end`) — perfecto para tests deterministas, pero **no** prueba que el
servidor real evite bloquearse. Por eso, además:

**Contra un `spectre serve` real** (puerto de prueba, sin `--no-browser`
implícito en el propio proceso), con `curl`:

```
curl -F archivo=@tests/fixtures/tomo348_cuerpo_p31-40.pdf;type=application/pdf \
  http://127.0.0.1:8743/api/tomos/9001/subir
# {"numero":9001,"estado":"descargado","calidad":"desconocida",
#  "etapas_hechas":1,"etapas_total":8,"error":null}      <- 202 al instante

# sondeando /api/estado cada 2s mientras el servidor seguía respondiendo:
# intento 1: fragmentado
# intento 2: fragmentado
# intento 3: indexado
```

El tomo de prueba (9001) y su PDF se borraron de `data/` al terminar (no
son parte del repo; `data/` está gitignorado, pero es la base real de este
equipo con 348+349 ya indexados desde PR-21, y no tenía sentido dejarla con
basura de prueba). Quedó un residuo menor: `IndiceVectorial` no tiene un
método para borrar vectores puntuales (solo `vaciar()`, que borra todo el
índice), así que los 6 vectores del tomo de prueba en `data/vectors/`
quedaron huérfanos — inofensivo (`Repo.filtrar_chunks` los descarta de
cualquier resultado real porque ya no hay fila en `chunks` para esos ids),
pero es una limitación real de la librería que vale la pena anotar.

## Dudas que quedaron

- **Sin mecanismo para reintentar una etapa fallida** (ver "qué decidí").
  Es una limitación heredada de PR-19, no algo que este PR introduce, pero
  ahora es más visible: antes solo se veía en la terminal de quien corría
  `spectre ingest`; ahora cualquiera que abra Biblioteca ve un tomo trabado
  con su error y no tiene ningún botón que lo arregle.
- **`IndiceVectorial` no puede borrar vectores puntuales** (ver "qué
  verifiqué") — hoy no importa (nada en el producto borra un tomo
  individual todavía), pero si PR-23 o un PR futuro agregara "borrar un
  tomo" desde la Biblioteca, haría falta ese método primero.
- **Sin catálogo de la CSJN en la UI** (ver "qué decidí") — queda para
  cuando alguien lo pida de verdad; el `csjn_tomo_id` a mano cubre el
  criterio de aceptación tal como está escrito.
- **No se probó `/indexar` contra el sitio real de la CSJN** (solo con
  `descargar_tomo` mockeado). El camino real ya lo prueba
  `tests/test_download.py`/`test_catalog.py` (marcados `red`) por separado;
  acá lo que hacía falta probar era la orquestación (background + progreso
  + error), no la descarga en sí, que no cambió.
