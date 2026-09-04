# Bitácora PR-20 — Servidor y UI base

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **FastAPI sirviendo el estático; layout,
navegación, estados vacíos honestos. Acepta: `spectre serve` levanta y abre
el navegador.**

## Resultado en una línea

`spectre/api/app.py` — `crear_app()` arma una FastAPI que expone
`GET /api/estado` (tomos con número/estado/calidad + total de chunks, leído
de la base real) y monta `spectre/web/` (HTML/CSS/JS planos, sin build) como
estático en `/`. La UI tiene dos tabs (Buscar / Biblioteca, JS plano sin
router) que arrancan mostrando lo que diga `/api/estado`, nunca datos
fabricados: sin nada indexado dicen "no hay nada indexado todavía"; con
datos, cuentan cuántos fragmentos hay o listan los tomos. `spectre serve
[--host] [--port] [--no-browser]` en el CLI: migra la base si hace falta,
arma la app y corre `uvicorn.run`; el navegador se abre desde un hook de
arranque del lifespan de FastAPI, no desde un `sleep` adivinado. **Verificado
de punta a punta**: `spectre serve` real contra `curl` (`/`, `/style.css`,
`/app.js`, `/api/estado` responden 200, el estado vacío es el real) y un test
que entra al lifespan real de `TestClient` (no un mock) para confirmar que el
hook de apertura del navegador corre cuando el servidor ya está escuchando.

## Qué hice

### `spectre/api/` — la app FastAPI

- `app.py::crear_app(*, on_startup=None)`: arma la `FastAPI`. Antes que nada,
  ~~registra~~ define `GET /api/estado`, y al final monta
  `StaticFiles(directory=WEB_DIR, html=True)` en `/` — el orden importa:
  Starlette resuelve las rutas en el orden en que se registran, y el mount en
  `/` es un catch-all, así que si fuera antes se comería `/api/estado`.
- `/api/estado` es de solo lectura, pasa por `Repo` (D-12) y nunca inventa
  nada: si `db_path` no existe todavía (clon nuevo, nunca corrió `db
  migrate`), devuelve `{"tomos": [], "chunks": 0}` sin abrir una conexión —
  es el mismo estado que devolvería una base migrada y vacía, así que la UI
  no necesita distinguir los dos casos.
- `on_startup`: un callback opcional que corre desde un `lifespan` de FastAPI
  (`@asynccontextmanager`, no el `@app.on_event("startup")` deprecado). Lo
  arma `spectre serve` para abrir el navegador; `crear_app()` no sabe nada de
  navegadores, solo ofrece el gancho — separación de responsabilidades entre
  "armar la app" (api/) y "cómo se levanta desde la terminal" (cli.py).

### `spectre/web/` — estático, sin build

- `index.html`: layout con `<header>` (título + nav de dos tabs) y `<main>`
  con dos `<section>` (`#tab-buscar`, `#tab-biblioteca`; la segunda arranca
  `hidden`). Sin framework, sin bundler: son los mismos activos que sirve
  `StaticFiles` tal cual están en el repo.
- `app.js`: `activarTab()` alterna qué `<section>` está `hidden` y qué botón
  tiene `aria-current`; `cargarEstado()` pega a `/api/estado` una vez al
  cargar y pinta los dos paneles. Si el fetch falla (servidor caído a medio
  cargar, por ejemplo), el panel de Buscar lo dice explícito en vez de
  quedarse en "Cargando…" para siempre.
- `style.css`: tipografía serif, paleta neutra, nada de dependencias
  externas (ninguna CDN — el servidor es 100% local, D-11).

### `spectre/cli.py` — `spectre serve`

- `_cmd_serve`: `ensure_dirs()` + `migrate(conn)` (mismo patrón que
  `_cmd_ingest`, para que un clon nuevo no reviente por falta de
  `data/spectre.db`), arma `on_startup` con `webbrowser.open(url)` salvo
  `--no-browser`, construye la app y llama `uvicorn.run(app, host, port,
  log_level="warning")` — bloqueante, un solo proceso (sin threads propios
  más allá de los que uvicorn arma para el event loop; nada de control de
  recursos casero).
- Se sacaron `_PENDIENTES` y `_hacer_stub`: `serve` era el único subcomando
  que quedaba ahí (D-05, "ningún stub que reporte éxito" — ahora tampoco hay
  ningún stub, punto, así que el mecanismo entero quedó sin uso).

### Tests

- **`tests/test_api.py`** (nuevo, 6 casos): `/api/estado` sin base, con base
  migrada vacía, y con tomos/chunks reales insertados por `Repo` (los tres
  casos, comparando el JSON exacto); `/` sirve el layout (título + los dos
  nombres de tab en el HTML); `/style.css` y `/app.js` responden 200; el
  `on_startup` de `crear_app` corre exactamente una vez al entrar al
  `lifespan` real de un `TestClient` (sin mockear nada de FastAPI/Starlette —
  es la prueba de que el hook está enganchado donde dice el criterio de
  aceptación, "levanta y abre").
- **`tests/test_cli.py`** (+3, −1): `serve` migra la base y llama
  `uvicorn.run` con el `--host`/`--port` pasados (con `uvicorn.run`
  mockeado — no se puede bloquear un test en un servidor real); un segundo
  test mockea `spectre.api.crear_app` para capturar el `on_startup` que
  arma `_cmd_serve` y confirma que, invocado, abre exactamente
  `http://127.0.0.1:8123/` (la URL construida a partir de `--host`/`--port`);
  un tercero confirma que `--no-browser` pasa `on_startup=None`. Se borró el
  caso `["serve"]` de `test_subcomandos_vacios_fallan_ruidosamente`
  (parametrizado): era el único que quedaba, así que el test entero se fue
  con él.

## Qué decidí por mi cuenta

- **El navegador se abre desde el `lifespan` de FastAPI, no desde un hilo con
  `sleep` antes de `uvicorn.run`.** La alternativa típica
  (`threading.Timer(1.0, webbrowser.open, [url]).start()` justo antes de
  `uvicorn.run`) es un número adivinado: si la máquina tarda más de un
  segundo en levantar el proceso, el navegador pega contra un puerto que
  todavía no escucha. El hook de arranque del lifespan de ASGI corre después
  de que uvicorn ya creó y bindeó el socket del servidor (el *accept loop* ya
  existe en ese punto), así que abrir el navegador ahí es correcto por
  construcción, no por tiempo. De paso, es más fácil de testear: un
  `TestClient` real entrando al `lifespan` prueba el enganche sin sockets ni
  sleeps en la suite.
- **Sin `/api/estado` la UI no podía cumplir "estados vacíos honestos" de
  verdad.** El criterio del PR menciona la frase explícita; sin un endpoint
  que diga cuántos tomos/chunks hay de verdad, "vacío" en el HTML sería un
  texto fijo indistinguible de una base con datos que la UI simplemente no
  supo leer — el mismo problema de fondo que D-05 (nunca fingir éxito),
  trasladado a la interfaz. Por eso el PR incluye ese endpoint de lectura
  aunque el plan no lo nombra explícitamente: es lo mínimo para que
  "honesto" signifique algo verificable, no una promesa.
- **JS plano, sin router de URLs.** Los dos tabs cambian con
  `element.hidden`, no con `/buscar` y `/biblioteca` como rutas del server
  ni del navegador. Con dos pestañas y sin necesidad todavía de compartir un
  link a un resultado (eso lo trae PR-21/22, con la cita `Fallos: N:N` como
  identificador), un router es complejidad sin beneficio hoy; si PR-21/22
  necesitan URLs profundas (por ejemplo `/fallo/348:145`), se agrega ahí,
  cuando haya algo real que direccionar.
- **`fastapi`/`uvicorn` como dependencias duras, no un extra opcional.** D-11
  fija FastAPI como parte del stack desde el plan original (no es una
  decisión nueva de este PR); a diferencia de `sentence-transformers`
  (pesado, evitable si solo se usa búsqueda léxica), no hay un Spectre sin
  servidor — es la interfaz completa del producto.
- **`httpx` en `dev`, no en las dependencias del paquete.** Solo lo usa
  `TestClient` en los tests; en producción nadie hace requests HTTP salientes
  desde Spectre.

## En qué me desvié del plan

Ninguna desviación de fondo. El plan describe PR-20 en una frase ("FastAPI
sirviendo el estático; layout, navegación, estados vacíos honestos") sin
especificar rutas ni forma de la API — la única decisión de diseño no
prescripta explícitamente es `/api/estado` (justificada arriba) y el uso del
`lifespan` de FastAPI para el hook del navegador en vez de un timer.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Se agregaron `fastapi>=0.115`,
`uvicorn>=0.30` (dependencias duras) y `httpx>=0.27` (dev, para
`TestClient`); instalados con `pip install -e ".[dev]"` (fastapi 0.141.1 /
uvicorn 0.52.4 quedaron resueltos).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 82 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 329 passed, 3 skipped, 23 deselected
```

`spectre serve` real, con `SPECTRE_DATA_DIR` apuntando a un tmp (sin tocar
`data/` del repo), en background con `--no-browser`, contra `curl`:

```
SPECTRE_DATA_DIR=/tmp/spectre-serve-test/datos spectre serve --port 8734 --no-browser &
curl -s http://127.0.0.1:8734/api/estado
# {"tomos":[],"chunks":0}
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8734/          # -> 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8734/style.css # -> 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8734/app.js    # -> 200
```

Apertura real de navegador (con display) no se pudo probar en esta sesión
(sin entorno gráfico); lo que sí se verificó son las dos piezas que,
combinadas, la garantizan: `webbrowser.open` se llama con la URL correcta
armada desde `--host`/`--port` (test de CLI con `crear_app` mockeado) y el
hook realmente corre cuando el servidor ASGI está levantado, no mockeado
(`test_on_startup_corre_una_vez_el_servidor_esta_listo`, con `TestClient`
real entrando al `lifespan`).

## Dudas que quedaron

- **No hay favicon.** El navegador va a pedir `/favicon.ico` y recibir 404
  (silencioso, no rompe nada); no lo até a este PR porque no hay una imagen
  de marca definida todavía y no es parte del criterio de aceptación.
- **`/api/estado` no pagina.** Con 349 tomos como máximo (el catálogo
  completo de la CSJN, PR-16) la lista entera nunca es grande, así que no
  hace falta paginar para el MVP — pero si PR-23 (Biblioteca) termina
  necesitando más campos por tomo (progreso de indexación en curso, tamaño
  del PDF), probablemente valga la pena separarlo en su propio endpoint en
  vez de seguir engordando este.
- **Sin manejo de error si el puerto ya está ocupado.** `uvicorn.run` va a
  reventar con su propio traceback si `--port` está tomado; no se agregó un
  mensaje más amigable porque no es parte del criterio de este PR y D-05
  pide fallar ruidosamente, no silenciar — el traceback de uvicorn ya
  cumple con "ruidoso", aunque no sea lindo para una usuaria no técnica
  (posible mejora de UX, no de corrección, para más adelante).
