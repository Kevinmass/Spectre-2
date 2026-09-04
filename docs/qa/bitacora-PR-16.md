# Bitácora PR-16 — Catálogo CSJN

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **listar los tomos disponibles (número,
volumen, año, id de la CSJN). Empieza con un spike: confirmar cómo se obtiene
el PDF de un tomo antes de construir nada. Acepta: catálogo con los 349 tomos
y el año de cada uno.**

## Resultado en una línea

El spike confirmó que sí hay descarga programática (riesgo R-3 del plan,
cerrado): `GET verTomo?tomoId=N` entrega el PDF directo. `spectre/corpus/
csjn/catalog.py` — `listar_catalogo()` pagina el listado real de la
Secretaría de Jurisprudencia (`POST /sj/tomosFallos`) y devuelve **421 filas,
349 números de tomo distintos, 1 a 349 sin huecos** — el criterio de
aceptación. El spike encontró además dos formas de dato que el esquema actual
no contempla (documentadas, no resueltas acá): un número de tomo puede tener
más de un volumen físico, y el año de los tomos viejos es un rango de texto.

## Qué hice

### El spike (antes de escribir código)

Con `WebSearch`/`WebFetch`/`curl` contra el sitio real de la Secretaría de
Jurisprudencia de la CSJN:

- El listado se ve por primera vez en `https://sjservicios.csjn.gov.ar/sj/
  tomosFallos.do?method=iniciar` (GET) pero **pagina por `POST /sj/
  tomosFallos`** (sin `.do` — la acción real del `<form>`, con un solo campo
  `desdePagina`). HTML plano, sin API ni JSON: 5 páginas de hasta 90 filas.
- Cada fila trae la etiqueta de volumen (`"349-I"`, `"216"`, ...), el año y
  un link `verTomo?tomoId=N`.
- **`GET verTomo?tomoId=N` entrega el PDF directo**: un `HEAD` real devuelve
  `content-type: application/pdf`, `content-disposition: attachment;
  filename=LibroVolNNN-M.pdf`, sin sesión ni token. Esto resuelve R-3: PR-17
  (descarga) se implementa directo sobre esta URL.
- **Hallazgo 1**: un `numero` de tomo puede repetirse con volúmenes
  distintos — `347-I` (tomoId 443) y `347-II` (tomoId 446) son dos filas
  reales del sitio, mismo número. 44 de los 349 números del catálogo actual
  tienen más de un volumen (hasta III en algunos casos). El esquema de
  `0001_initial.sql` tiene `tomos.numero INTEGER NOT NULL UNIQUE` — no
  admitiría insertar los dos sin romper la restricción.
- **Hallazgo 2**: el año no siempre es un año único. Los tomos hasta ~1917 lo
  publican como rango (`"1898/1899"`), confirmado con `tomo 1` (`"1863/1865"`)
  y otros 35 en el catálogo actual. `tomos.anio` es `INTEGER` en el esquema
  actual — no admite un rango como texto.

Ninguno de los dos hallazgos se resuelve en este PR (el catálogo no persiste
nada); quedan documentados para quien encare la persistencia (PR-17 en
adelante).

### `spectre/corpus/csjn/catalog.py` (paquete `csjn/` nuevo)

- **`EntradaCatalogo(numero: int, volumen: str | None, anio: str,
  csjn_tomo_id: str)`** — una fila del catálogo. `anio` es `str` a propósito
  (hallazgo 2). `csjn_tomo_id` es lo único que identifica la fila de forma
  única (hallazgo 1: `numero` no alcanza).
- **`parsear_pagina(html)`** — función pura (sin red), regex sobre el HTML de
  una página: entradas + `(página actual, total de páginas)`. Revienta
  (`ValueError`) si no encuentra el pie de paginación (D-05: no finge que
  parseó algo que no está).
- **`listar_catalogo(*, pedir_pagina=_pedir_pagina)`** — pagina hasta agotar
  el sitio. `pedir_pagina` es un punto de inyección: los tests pasan páginas
  fabricadas a mano sin tocar la red; sin pasarlo, usa `_pedir_pagina` (POST
  real con `urllib.request`, sin dependencias nuevas).
- Sin persistencia: como `corpus/pdf` y `corpus/fallo`, mide/lista en
  memoria — llenar `tomos` es cosa de PR-17 en adelante.

### `spectre/cli.py`

- **`spectre csjn catalog [--muestra N]`** — imprime el resumen (filas,
  números distintos, rango, cuántos tienen más de un volumen) y, con
  `--muestra`, las primeras N filas.

### `pyproject.toml`

- Marca `red` nueva (`pytest.ini_options`): tests que pegan contra un sitio
  real por HTTP. `addopts` pasa de `-m 'not slow'` a `-m 'not slow and not
  red'` — CI no depende de que el sitio de la CSJN esté arriba. No hace falta
  tocar `.github/workflows/ci.yml`: ya corre `pytest` a secas, que hereda el
  `addopts` del `pyproject`.

### Tests

- **`tests/fixtures/csjn_catalogo_p1.html`** (nuevo) — recorte real de la
  página 1 del sitio (5 filas, incluido el par `347-I`/`347-II`, más el pie
  de paginación).
- **`tests/test_catalog.py`** (nuevo, 7 casos; 1 `red`):
  - `_parsear_etiqueta` con y sin volumen.
  - `parsear_pagina` contra el fixture real: entradas exactas, y que detecta
    el mismo `numero` en dos volúmenes distintos.
  - `parsear_pagina` sin pie de paginación → `ValueError`.
  - `listar_catalogo` con dos páginas fabricadas a mano (prueba el bucle de
    paginación sin red: se piden en orden, se agregan las entradas de las
    dos).
  - **`test_listar_catalogo_real`** (`red`): pega contra el sitio real.
    **No fija un total exacto** (el sitio es un recurso vivo — la CSJN
    publica tomos nuevos): verifica que los números sean contiguos desde 1,
    con al menos los 349 del plan, que ningún `csjn_tomo_id` se repita, y que
    el hallazgo 1 sea reproducible (`347` con volúmenes `["I", "II"]`).
- **`tests/test_cli.py`** (+3, 2 `red`): `csjn catalog` imprime el resumen y,
  con `--muestra`, filas; `csjn` sin acción revienta.

### Docs

- `tests/fixtures/README.md`: sección para el nuevo fixture HTML (con receta
  de regeneración vía `curl`, no `pypdf`).
- `docs/plan-spectre.md`: casilla PR-16 (§6) con los números medidos; **R-3
  (§7) marcado cerrado**; §9 → "Próximo: PR-17".
- `CLAUDE.md`: "Estado del código" → PR-16; `## Comandos` + `spectre csjn
  catalog`; `## Tests` documenta la marca `red`.

## Qué decidí por mi cuenta

- **`urllib.request` de la librería estándar, no `requests`.** Es una sola
  llamada POST con un campo de formulario; agregar una dependencia nueva por
  eso no se justifica (mismo criterio que ya aplicó el proyecto para no
  agregar cosas "por si acaso").
- **Regex en vez de un parser HTML (`BeautifulSoup`/`lxml`).** La fila es una
  estructura muy regular y repetida (mismo patrón de `div`s); un regex acotado
  a esa forma alcanza, como ya hace `index_parser.py` con el índice del PDF.
  Si el sitio cambia de maquetación, el regex revienta ruidosamente (no
  silencioso) — correcto para D-05.
- **`anio: str`, no `int`.** Forzar un `int` habría significado inventar una
  regla para los rangos (¿el primer año? ¿el segundo?) sin que el plan lo
  pida. Mejor guardar lo que el sitio realmente dice y que quien persista
  decida.
- **No cambié el esquema (`tomos.numero UNIQUE`) ni agregué un
  `insert_seccion`-style método para csjn.** Los dos hallazgos del spike
  afectan a *cómo persistir* el catálogo, que es explícitamente PR-17 en
  adelante ("descarga: reintentos, caché por sha256..." trabaja con tomos ya
  identificados). Cambiar la migración ahora sería adivinar el diseño que
  PR-17 todavía no definió (¿una migración `0004` con `UNIQUE(numero,
  volumen)`? ¿guardar el año-rango en una columna aparte?) — se documenta acá
  para que no sea una sorpresa.
- **Marca `red` separada de `slow`.** Son motivos de exclusión distintos:
  `slow` es "mide sobre un fixture grande no versionado" (determinístico,
  solo pesado); `red` es "depende de que un sitio de terceros esté arriba y
  responda igual" (nunca determinístico del todo). Mezclarlas habría hecho
  perder esa distinción en `pytest -m slow` (alguien que solo quiere medir
  sobre el Tomo 348 no necesita que además le pegue a internet).
- **`test_listar_catalogo_real` no fija el total exacto (421/349), solo
  relaciones que siguen valiendo si la CSJN publica tomos nuevos** (contiguo
  desde 1, ≥349, sin ids repetidos, al menos un número con >1 volumen). Fijar
  el número exacto habría hecho que el test fallara solo, sin que nada se
  haya roto, el día que se publique el tomo 350.

## En qué me desvié del plan

- Ninguna desviación de fondo. El plan pide explícitamente empezar con el
  spike "antes de construir nada" — eso es lo que se hizo, y el resultado
  (sí hay descarga programática) está documentado en el propio módulo y en
  R-3.
- El plan menciona `corpus/csjn/download.py` en la arquitectura (§4), pero es
  explícitamente de PR-17; acá solo se creó `catalog.py`.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> todos formateados
./.venv/Scripts/python.exe -m pytest -q                # -> 273 passed, 3 skipped, 20 deselected
./.venv/Scripts/python.exe -m pytest -m red -q         # -> 3 passed (~6 s)
```

(Los 3 `skipped` son de PR-12, no de este PR — ver bitácora PR-15: tests que
verifican el mensaje de error cuando `sentence-transformers` no está
instalado, correctamente salteados porque sí lo está.)

Medido con `spectre csjn catalog` contra el sitio real:

```
filas del catálogo         421
números de tomo distintos  349
rango de números           1–349
con más de un volumen      44 números
```

Confirmado con un `HEAD` real que `verTomo?tomoId=443` (347-I) entrega
`content-type: application/pdf`, `content-disposition: attachment;
filename=LibroVol347-1.pdf`.

**Nota sobre el proceso**: la primera versión de `_pedir_pagina` apuntaba a
`tomosFallos.do` (con el sufijo que tiene la página inicial) y devolvía
`405 Method Not Allowed` en cada corrida — un `curl` manual con los mismos
verbo/headers pero contra `tomosFallos` (sin `.do`, la acción real del
`<form>`) sí andaba. La URL equivocada, no el header `Accept` (que también
hizo falta agregar, esa parte sí era necesaria) explicaba el 405; quedó
corregida antes de escribir los tests contra red.

## Dudas que quedaron

- **Persistencia del catálogo**: los dos hallazgos del spike (multi-volumen,
  año-rango) los tiene que resolver PR-17 antes de insertar en `tomos`. No los
  evalué en profundidad más allá de documentarlos: quedan como decisión de
  diseño abierta, no como bug.
- **Robustez del regex ante cambios de maquetación**: si el sitio de la CSJN
  cambia el HTML (nombres de clase CSS, estructura de `div`s), `parsear_
  pagina` va a romper. Es esperable y correcto (D-05: falla ruidosa, no un
  catálogo vacío silencioso) pero no hay forma de anticiparlo sin que pase.
- **Rate limiting / bloqueo por volumen de pedidos**: 5 páginas por corrida
  anduvo sin problema en esta sesión; no se probó qué pasa si `download.py`
  (PR-17) pide cientos de PDFs seguidos — probablemente necesite backoff o
  ritmo respetuoso, que el propio plan (PR-17) ya prevé ("ritmo respetuoso
  con el servidor").
- **User-Agent identificable**: se dejó un UA que se anuncia como bot
  (`Spectre/0.0; +github...`) porque no pareció afectar el resultado (anduvo
  igual que un UA de navegador genérico); si el sitio empezara a bloquearlo,
  revisar esto primero.
