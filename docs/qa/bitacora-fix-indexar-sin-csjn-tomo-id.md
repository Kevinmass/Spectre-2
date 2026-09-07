# Bitácora — fix: indexar desde la Biblioteca sin `csjn_tomo_id`

Fecha: 07/09/2026
Rama: `fix-indexar-sin-csjn-tomo-id` (de `main` con PR-C1 mergeado, #37).
No es un PR del plan: es un parche de bug. Sin casilla en `docs/plan-v2.md`
(sí una nota bajo PR-B4, que es el arreglo de fondo).

## El bug (reportado por Kevin)

Al indexar un tomo de la CSJN desde la Biblioteca:

> Falló en "descargar": ValueError: tomo 347: sin csjn_tomo_id, no se puede
> descargar (usá `spectre ingest --pdf` para subirlo a mano)

Se repite en todos los tomos probados.

### Causa

El formulario "Indexar desde la CSJN" tiene el campo `csjn_tomo_id` como
**opcional**, con un placeholder que manda a la terminal (`spectre csjn
catalog`). Ese id **no es el número de tomo** y no se puede deducir: es un
autoincrement interno del sitio de la Corte (`/sj/verTomo?tomoId=N`), y un
mismo número puede tener dos volúmenes con ids distintos (347-I → 443, 347-II
→ 446). Desde la UI no hay forma de obtenerlo.

Si se deja el campo vacío:

1. `POST /api/tomos/347/indexar` con `csjn_tomo_id: null`
2. `iniciar_tomo` registra igual el tomo con `csjn_tomo_id = NULL`, estado
   `registrado`
3. arranca el pipeline → etapa `descargar` → `_h_descargar` hace
   `if not tomo.csjn_tomo_id: raise ValueError(...)`
4. queda un tomo "zombie" en `registrado` mostrando ese error de dev en
   `/api/estado`

Es el problema #5 del `plan-v2.md` §2 ("La Biblioteca esconde el catálogo").

## Qué se hizo

Parche interino. El arreglo de fondo —elegir el tomo de un catálogo, sin
tipear ids— es **PR-B4**, hoy bloqueado por la segunda sesión de observación.

### `spectre/api/app.py` — `POST /api/tomos/{numero}/indexar`

- Normaliza el id: `(payload.csjn_tomo_id or "").strip() or None` (un `""` o
  `"   "` cuentan como ausente).
- Si no hay id **y** el tomo no existe todavía, o existe pero sin
  `csjn_tomo_id` ni `pdf_path`: **400** con mensaje legible ("Falta el id de
  la CSJN para el tomo N… lo da `spectre csjn catalog`. Si ya tenés el PDF,
  subilo con «Subir un PDF propio»."). No registra nada, no encola pipeline.
- Si el tomo ya existe con un id o con un PDF, un POST sin cuerpo se deja
  pasar: eso es **retomar** una indexación, no arrancar una sin con qué.

### `spectre/web/index.html` + `app.js` + `style.css`

- El `<input name="csjn_tomo_id">` pasa a `required`; la etiqueta deja de
  decir "(opcional)"; placeholder `p. ej. 445 — lo da `spectre csjn catalog``.
- Línea de ayuda (`.ayuda-form`): "No es el número de tomo: es un id interno
  del sitio de la Corte. Si ya tenés el PDF, usá «Subir un PDF propio»."
- El handler del submit corta antes de hacer `fetch` si el id está vacío, con
  el mismo mensaje en `#biblioteca-aviso` (defensa en profundidad con
  `required`). El 400 del backend ya se muestra solo: `_detalleDeError` lee
  `detail`.

### Tests — `tests/test_api.py`

Reescritos los 3 que asumían el comportamiento viejo (POST `{}` → 202):

- `test_indexar_sin_csjn_tomo_id_da_400_y_no_registra_nada` (era
  `..._responde_202_con_el_registro_inicial`): POST `{}` → 400, `detail`
  menciona `csjn catalog`, `/api/estado` queda sin tomos.
- `test_indexar_con_csjn_tomo_id_en_blanco_tambien_da_400` (nuevo): `""` y
  `"   "` → 400.
- `test_indexar_sin_id_se_permite_si_el_tomo_ya_tiene_uno` /
  `..._ya_tiene_pdf` (nuevos): tomo pre-sembrado `indexado` con id (o con
  pdf_path) → POST `{}` → 202, sin tocar la red (pipeline no-op sobre
  `indexado`).
- `test_indexar_sin_csjn_tomo_id_falla_en_descargar_y_queda_visible`
  **eliminado**: ese camino (registrar y reventar en `descargar`) es
  justamente lo que el parche saca.
- `test_indexar_es_idempotente_sobre_un_tomo_ya_registrado`: ahora siembra el
  tomo `indexado` con id antes de los dos POST.

## Qué decidí por mi cuenta

- **Solo el endpoint web, no el CLI.** `spectre ingest 347` sin `--pdf` ni
  `--csjn-tomo-id` sigue reventando en `descargar` con el `ValueError` de
  siempre (y su test `test_ingest_sin_pdf_ni_csjn_id_revienta_en_descargar`
  sigue verde). Es una herramienta de dev, el error en la terminal es
  aceptable, y el reporte fue sobre la Biblioteca. Tocar el CLI ampliaría el
  parche sin necesidad.
- **`required` en el input además del 400.** El `required` da el bloqueo
  inmediato del navegador; el 400 cubre a cualquier cliente que no sea ese
  form (otro POST directo). El guard en JS es el tercer nivel, por si el
  `required` se saca en el futuro.
- **Se permite POST sin id cuando el tomo ya tiene id o PDF.** Sin esa
  excepción, "retomar" un tomo a medio indexar desde el form obligaría a
  volver a tipear el id. Hoy no hay botón de "retomar" en la UI, pero el
  endpoint no debería cerrarse esa puerta.

## En qué me desvié del plan

- El plan no tiene un slot para esto (es un bug). Queda anotado bajo PR-B4 en
  `docs/plan-v2.md` como parche interino y en `CLAUDE.md` (descripción del
  endpoint).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13; CI valida 3.11).

```
./.venv/Scripts/ruff.exe check .                        # -> All checks passed!
./.venv/Scripts/ruff.exe format --check spectre tests   # -> 64 files already formatted
node tests/verificar_cita.mjs                           # -> app.js sigue cargando/parseando
./.venv/Scripts/python.exe -m pytest -q tests/test_api.py   # -> 46 passed
./.venv/Scripts/python.exe -m pytest -q                 # -> 406 passed, 3 skipped, 24 deselected
```

- 406 vs 404 al cerrar PR-C1: −2 tests reescritos/eliminados, +4 nuevos.
- No se probó a mano contra el sitio real de la CSJN (no hace falta para el
  parche: el 400 corta *antes* de cualquier red).

## Dudas / pendientes

- **El arreglo de fondo es PR-B4** (catálogo en la UI, elegir el tomo de una
  lista). Bloqueado por la segunda observación. Hasta entonces, indexar un
  tomo de la CSJN desde la web sigue necesitando que el usuario consiga el id
  con `spectre csjn catalog` en la terminal — el parche solo hace que el
  fracaso sea legible y no deje basura.
- **Tomos zombie ya existentes.** Si Kevin ya generó tomos en `registrado`
  con `csjn_tomo_id NULL` probando el bug, siguen en la base con su error.
  No los limpia este parche; se borran con `DELETE FROM tomos WHERE
  numero = ...` o reindexando bien con el id correcto.
- **Multi-volumen.** `347-I` y `347-II` comparten `numero=347` y el esquema
  tiene `tomos.numero UNIQUE` (hallazgo 1 de la bitácora PR-16). El parche no
  lo toca; es materia de PR-B4 / Tanda E.
