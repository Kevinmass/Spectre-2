# Bitácora PR-C1 — Persistir las citas y mostrar quién cita a quién

Fecha: 07/09/2026
Rama: `pr-c1-persistir-citas` (de `main` con PR-A6 ya mergeado, #36).

## Qué pedía el plan

> **PR-C1 `[N]` Persistir las citas y mostrar quién cita a quién.** Terminar el
> PR-10: guardar en `citas` durante el pipeline y agregar las citas
> *entrantes*. Con dos tomos ya hay grafo; con veinte es una función que ningún
> buscador gratuito da.
> *Acepta:* 887 citas para el Tomo 348 en la tabla; un fallo muestra quién lo
> cita dentro del corpus indexado.

## Qué se hizo

### Persistencia (pipeline)

- **`spectre/jobs/pipeline.py`, `_h_estructurar`**: además de los metadatos,
  corre `extraer_citas` (PR-10) sobre el mismo `texto_del_fallo` que ya arma
  para `extraer_metadatos`, y vuelca el resultado a la tabla `citas`. Antes de
  insertar, `repo.borrar_citas_de_fallo(f.id)` — un reintento de la etapa no
  acumula. **Sin etapa nueva, sin estado nuevo, sin migración**: la cita es una
  propiedad estructural del fallo y sale del texto que `estructurar` ya tiene
  en la mano. `borrar_fallos` (etapa `segmentar`) ya arrastraba `citas` por la
  FK `ON DELETE CASCADE` de `0001`.
- La nota **"Citas"** del docstring del módulo, que decía "esta cadena no la
  llena", ahora describe lo que hace.

### Lectura (repo)

- **`spectre/db/repo.py`**: dataclasses `Cita` (fila de `citas`) y
  `CitaEntrante` (fallo citante: cita + carátula + página + contexto).
  Métodos nuevos:
  - `insert_citas(fallo_id, filas)` — lote, `(tomo_citado, pagina_citada,
    contexto)` por fila (lo que da `extraer_citas`).
  - `borrar_citas_de_fallo(fallo_id)` — idempotencia de la etapa.
  - `list_citas_de_fallo(fallo_id)` — salientes, en orden de aparición.
  - `contar_citas_de_tomo(tomo_id)` — el número del criterio de aceptación.
  - `citas_entrantes(fallo_id)` — cruza `citas.tomo_citado` con el **número**
    del tomo del fallo consultado y `citas.pagina_citada` con su **rango de
    páginas** (`pagina_inicio..pagina_fin`), no con la página de inicio exacta:
    una cita puede apuntar a un considerando del medio (duda #3 de PR-10).
    Excluye la auto-cita (`f.id <> ?`).
  - `Cita` / `CitaEntrante` exportadas desde `spectre/db/__init__.py`.

### Endpoint y UI

- **`spectre/api/app.py`, `GET /api/fallos/{cita}`**: las salientes se leen de
  `repo.list_citas_de_fallo`; **si no hay filas** (tomo indexado antes de
  PR-C1) se recalculan al vuelo con `extraer_citas`, como hacía PR-22 — así no
  se rompe la vista de un corpus viejo. Nueva clave `citas_entrantes` con
  `repo.citas_entrantes`.
- **`spectre/web/app.js`**: `renderCitasEntrantes` — bloque "Citado por" con la
  cita del citante (botón, abre ese fallo con `mostrarFallo`), la carátula y el
  contexto. Estado vacío con texto llano ("Ningún otro fallo del corpus
  indexado cita a este…"). Se llama en `renderFallo` después de las salientes.
- **`spectre/web/style.css`**: los selectores de `.citas-salientes` ahora
  cubren también `.citas-entrantes` (mismo estilo de tarjeta).

### Tests

- **`tests/test_db.py`** (+8): `insert`/`list`/`contar`, `borrar` idempotente,
  cascada desde `borrar_fallos`, `citas_entrantes` (encuentra al citante por
  página interior, excluye auto-cita, ignora otro tomo con la misma página,
  vacío si el fallo no tiene `pagina_inicio`).
- **`tests/test_pipeline.py`**: `test_pipeline_completo_sobre_el_fixture_real`
  ahora exige `contar_citas_de_tomo(tid) == 8` y que 2 de los 3 fallos tengan
  citas (medido con `spectre pdf citations` sobre el fixture). `_resumen`
  incluye el conteo de citas → las pruebas de idempotencia y de
  corte/reanudación también lo cubren.
- **`tests/test_api.py`** (+2): las salientes salen de la tabla cuando hay
  filas; `/api/fallos/{cita}` muestra quién cita al fallo (con carátula y
  página). Los dos tests de PR-22 que ya existían chequean además
  `citas_entrantes == []`.

### Docs

- `CLAUDE.md`: descripción de `/api/fallos/{cita}` y de la vista de fallo
  actualizadas; el bloque "Deuda conocida" ya no dice "la tabla `citas` tiene
  0 filas"; la "Fixture de referencia" aclara que 887 son *referencias* y la
  tabla guarda ~2.006 filas.
- `docs/plan-v2.md`: casilla PR-C1 marcada con lo hecho y la salvedad del
  número; §10 actualizado.

## Qué decidí por mi cuenta

- **La persistencia va en `estructurar`, no en una etapa `citas` propia.** Una
  etapa nueva obliga a un `estado` nuevo en `tomos` → migración `0005` +
  tocar `_ORDEN_ESTADOS`, `ETAPAS`, `siguiente_etapa`, `progreso` y sus tests.
  `estructurar` ya calcula `texto_del_fallo` por fallo y ya es el lugar de
  "propiedades del fallo que salen de su texto" (metadatos). Menos superficie,
  misma semántica.
- **`citas_entrantes` matchea por rango de páginas, no por `pagina_inicio`
  exacta.** `Fallos: N:P` suele apuntar al inicio de un fallo, pero también se
  ve apuntando a una página interior (un considerando). Exigir igualdad
  perdería esas. El rango `pagina_inicio..pagina_fin` del fallo consultado es
  la aproximación correcta con lo que hay.
- **Fallback al recálculo al vuelo para las salientes.** Un corpus indexado
  antes de PR-C1 tiene 0 filas en `citas`; sin fallback, la vista de fallo
  perdería las salientes hasta reindexar. Las entrantes **no** tienen fallback
  posible (no se pueden calcular sin las citas de todos los demás fallos ya
  guardadas) y eso está dicho en el docstring del endpoint y en `CLAUDE.md`.
- **Se excluye la auto-cita de las entrantes** (`f.id <> fallo_id`). Un fallo
  que se cita a sí mismo no es "quién me cita". Una cita de *otro* fallo del
  mismo tomo sí cuenta y se conserva.
- **No agregué un CLI para inspeccionar la tabla `citas`.** El criterio de
  aceptación se verifica desde el test del pipeline y desde el endpoint; un
  `spectre citas …` sería scope extra. `spectre pdf citations` (PR-10) sigue
  midiendo sin persistir, como el resto de `pdf`.

## En qué me desvié del plan

- **"887 citas en la tabla" no se cumple literal y no se fuerza.** 887 es el
  conteo de *referencias* `Fallos:` (`contar_referencias`, PR-10), no de
  precedentes. La tabla `citas` guarda una fila por precedente citado, así que
  el Tomo 348 da ~2.006 filas (número medido en PR-10, no re-medido acá:
  requiere `pytest -m slow` con el modelo real y `data/tomos/348.pdf`). El
  criterio "un fallo muestra quién lo cita dentro del corpus indexado" sí se
  cumple y está testeado.
- **La verificación del número real sobre el Tomo 348 quedó pendiente de una
  corrida `slow`.** La suite rápida lo fija sobre el fixture chico (8 citas).
  Ver "Dudas".

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13; CI valida 3.11).

```
./.venv/Scripts/ruff.exe check .                 # -> All checks passed!
./.venv/Scripts/ruff.exe format --check spectre tests   # -> 64 files already formatted
./.venv/Scripts/python.exe -m pytest -q tests/test_db.py tests/test_api.py tests/test_pipeline.py
#   -> 129 passed
./.venv/Scripts/python.exe -m pytest -q          # -> 404 passed, 3 skipped, 24 deselected
node tests/verificar_resaltado.mjs               # -> TODO OK (app.js sigue cargando y parseando)
node tests/verificar_cita.mjs                    # -> TODO OK
./.venv/Scripts/python.exe -m spectre.cli pdf citations tests/fixtures/tomo348_cuerpo_p31-40.pdf --tomo 348
#   -> 3 referencias / 8 citas fallo->fallo / 2 de 3 fallos citantes  (fija el test del pipeline)
```

- Antes de la suite: `404 passed` vs `395` al cerrar PR-A6. +9 = 8 tests nuevos
  en `test_db.py` + 2 en `test_api.py` − 1 (ninguno borrado; el conteo previo
  del plan §2 decía 397, la bitácora de PR-A6 medía 395 en esta máquina).
- El `slow` sobre el Tomo 348 entero (`pytest -m slow tests/test_pipeline.py`)
  **no se corrió** en esta sesión.

## Dudas que quedaron abiertas

- **El número exacto de filas en la tabla para el Tomo 348.** PR-10 lo estimó
  en 2.006 (fallo→fallo, con la segmentación de 133 fallos). Habría que
  correr `spectre ingest 348 --pdf data/tomos/348.pdf` contra un `data_dir`
  limpio y `SELECT count(*) FROM citas` para fijarlo. No cambia el diseño;
  cambia el número que anota el criterio.
- **`pagina_citada` vs. el fallo destino real.** El match por rango asume que
  `pagina_inicio..pagina_fin` de cada fallo no se solapa con el vecino. PR-06/07
  arrastran carátulas de dos líneas que parten un fallo por página; si dos
  fallos comparten página, una cita entrante podría atribuirse a los dos.
  Chico, y se acota cuando se resuelva el 133 ≠ 126.
- **Citas a tomos no indexados.** Hoy la inmensa mayoría de `tomo_citado`
  apunta a tomos que no están en el corpus (solo 348 y 349 lo están). Las
  salientes se muestran igual (son texto), pero el "grafo" real recién tiene
  aristas cuando se carguen más tomos. Es lo que dice el plan ("con veinte es
  una función…").
- **Reindexado de lo ya cargado.** Para que la base local de esta máquina
  tenga las citas hay que reindexar 348 y 349. No lo hace este PR (no toca
  `data/`); queda como tarea de operación, anotada en `CLAUDE.md`.
- **Cadenas largas** (un `Fallos:` con 20+ precedentes) entran las 20+ como
  filas con el mismo `contexto`. Igual que en PR-10; si algún análisis quiere
  pesar distinto "citado solo" vs "en una lista de 20", el dato está.
