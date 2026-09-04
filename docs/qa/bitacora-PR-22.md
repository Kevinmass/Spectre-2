# Bitácora PR-22 — Vista del fallo

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **Texto completo por secciones, metadatos,
citas salientes, enlace a la página del PDF original. Acepta: desde un
resultado se llega al fallo completo y de ahí al PDF en la página
correcta.**

## Resultado en una línea

`GET /api/fallos/{cita}` (`spectre/api/app.py`) devuelve el fallo completo:
metadatos (fecha, tribunal de origen, tipo de recurso, jueces), el texto de
cada sección tal cual está en `secciones.texto`, y las citas salientes
recalculadas al vuelo con `extraer_citas` (PR-10) — el pipeline (PR-19) las
dejó explícitamente sin persistir. `GET /api/tomos/{numero}/pdf` sirve el PDF
desde disco; la vista de fallo (`spectre/web/`) calcula la página del visor
con `pagina_oficial + offset_pagina`, usando la página del **chunk que trajo
el resultado**, no la primera del fallo. En la UI, clickear la cita de un
resultado de búsqueda abre esta vista; un botón vuelve. **Verificado con
datos reales** (348 + 349, ya indexados desde PR-21): el caso "Loyola"
(348:113, dictamen + mayoría + 3 votos concurrentes, el mismo que usó PR-09
de referencia) sale completo y bien seccionado, y la matemática de página se
confirmó contra el PDF real con `pdfplumber` — una página oficial 739 de un
resultado de búsqueda mapea exacto a `pdf_page` 745, que efectivamente dice
"739" en el encabezado del PDF.

## Qué hice

### `spectre/api/app.py` — `GET /api/fallos/{cita}` y `GET /api/tomos/{numero}/pdf`

- `/api/fallos/{cita}`: `Repo.get_fallo_por_cita` + `Repo.get_tomo` +
  `Repo.list_secciones_de_fallo` (todos ya existían, de PR-02/PR-19). 404
  con el detalle de la cita si no existe fallo o no hay base todavía —mismo
  patrón que `/api/buscar` con `db_path` faltante.
- **Citas salientes recalculadas, no leídas de una tabla.** La tabla `citas`
  existe en el esquema desde `0001_initial.sql`, pero PR-19 decidió a
  propósito no llenarla (bitácora PR-19: "es la materia prima del grafo de
  precedentes, que el plan pone explícitamente fuera del MVP"). Este PR
  necesita mostrar "citas salientes" igual, así que concatena
  `secciones.texto` de todas las secciones del fallo (en orden) y corre
  `extraer_citas` (PR-10) sobre ese texto — la misma función que ya usa
  `spectre pdf citations`, sin reabrir el PDF (el texto ya está en SQLite).
  Es honesto: no lee de una tabla vacía fingiendo que hay datos, ni persiste
  nada nuevo que compita con la decisión de PR-19 — cada vista recalcula, es
  barato (una regex sobre un fallo, no sobre el tomo entero) y siempre
  refleja el texto real guardado.
- **`jueces`**: `Fallo.jueces` es un `TEXT` con JSON adentro (lo serializa
  el pipeline en PR-19, `json.dumps(meta.jueces, ...)`); acá se
  `json.loads`-ea o se devuelve `[]` si es `NULL`.
- `/api/tomos/{numero}/pdf`: `FileResponse` sobre `tomo.pdf_path`. 404 con
  mensaje explícito («no existe el tomo N» / «el PDF del tomo N no está
  disponible en este servidor») si el tomo no existe o si el archivo no está
  realmente en disco — nunca un 200 vacío ni un placeholder (D-05).
- **La conversión página oficial → página del PDF vive en la respuesta, no
  en la fórmula que adivina el cliente.** `/api/fallos/{cita}` devuelve
  `offset_pagina` (de `tomos.offset_pagina`, PR-04) tal cual está en la
  base; el cliente arma `pdf_page = pagina_oficial + offset_pagina` para
  cualquier página oficial que ya tenga a mano (la del inicio del fallo, o
  la de un chunk específico que vino de un resultado de búsqueda) — no hace
  falta un endpoint por cada combinación posible de "qué página quiero".

### `spectre/web/` — la vista de fallo

- `index.html`: una tercera `<section id="tab-fallo">`, sin botón en el nav
  (no es un tab elegible, se llega solo clickeando un resultado) — reusa el
  mecanismo genérico `activarTab()` de PR-20/21 (que ya alterna
  `panel.hidden` por id) sin tener que tocarlo.
- `app.js`:
  - El `<span class="cita">` de cada resultado de búsqueda pasó a ser un
    `<button>` que llama a `mostrarFallo(r.cita, r.pagina_oficial)` — le
    pasa la página del **chunk concreto** que matcheó, no solo la cita.
  - `mostrarFallo` pide `/api/fallos/{cita}`, muestra "Cargando…" mientras
    tanto, y arma la vista con `renderFallo`.
  - `renderEnlacePdf(fallo, paginaSolicitada)`: si `pdf_disponible` es
    falso, dice explícito que el PDF no está disponible (nunca un enlace
    roto); si es cierto, calcula la página con `pagina_solicitada ??
    fallo.pagina_inicio` más `offset_pagina` y arma
    `/api/tomos/{numero}/pdf#page=N}` — el fragmento `#page=N` es el
    mecanismo estándar que los visores de PDF embebidos de los navegadores
    (Chrome, Firefox, Edge) entienden para abrir en una página específica.
  - `renderSeccionFallo` / `renderCitasSalientes`: reusan las clases
    `.badge-*` de PR-21 para el tipo de sección (mismo color = misma
    convención en toda la app), y muestran "no se encontraron citas" en vez
    de una lista vacía silenciosa cuando `citas_salientes` viene `[]`.
  - El texto de cada sección se pinta con `textContent` +
    `white-space: pre-wrap` en CSS (preserva los saltos de línea que ya
    trae `secciones.texto` sin tener que parsear `\n` a mano ni tocar
    `innerHTML`).

### Tests

- **`tests/test_api.py`** (+18 sobre PR-21): 404 sin base y con cita
  inexistente; metadatos/secciones/citas completos sobre un fallo armado a
  mano con una cita real (`Fallos: 337:315, «Acevedo»`) — confirma que
  `extraer_citas` la encuentra y arma `tomo_citado=337`/`pagina_citada=315`;
  jueces/citas vacíos dan `[]` (no `null`, no error); `pdf_disponible` en
  ambos sentidos (archivo real en `tmp_path` vs. ruta que no existe); y la
  familia de `/api/tomos/{numero}/pdf` — sin base, tomo inexistente, archivo
  ausente en disco, y sirviendo bytes reales con
  `content-type: application/pdf`.

## Qué decidí por mi cuenta

- **La vista de fallo no tiene URL ni tab propios.** Se llega solo
  clickeando un resultado (`activarTab("fallo")` sin botón de nav
  asociado); "volver" siempre manda a Buscar. El plan no pide URLs
  compartibles para PR-22 y agregar un router (aunque sea uno mínimo,
  basado en `location.hash`) es una pieza más para mantener sin un
  requisito concreto que la justifique todavía — la nota de PR-20 sobre
  esto ("si necesitan URLs profundas, se agrega cuando haya algo real que
  direccionar") sigue aplicando; ahora hay algo real (un fallo puntual),
  pero el criterio de aceptación de este PR no pide poder compartir el
  link, solo poder *llegar* navegando desde un resultado.
- **La página del PDF se calcula con la página del chunk que trajo el
  resultado, no con el inicio del fallo.** El criterio dice "el fragmento
  correcto", y un fallo puede tener hasta 57 páginas (plan §6, PR-07): abrir
  siempre en la página 1 del fallo para un resultado que matcheó en la
  página 40 no sería "la página correcta". Lo verifiqué con datos reales
  (ver "qué verifiqué") contra un resultado de disidencia en el Tomo 349:
  la página que abre el link es exactamente la que tiene el texto resaltado
  en el resultado de búsqueda, no la portada del fallo.
- **`extraer_citas` corre sobre el texto concatenado de las secciones
  persistidas, no reabre el PDF.** Alternativa descartada: releer el PDF y
  correr `texto_del_fallo` + `extraer_citas` como hace `spectre pdf
  citations`. `secciones.texto` ya tiene ese mismo contenido guardado desde
  el pipeline (PR-19) — reabrir el PDF para un dato que ya está en SQLite
  hubiera violado el espíritu de D-8 ("el parseo y el embedding están
  separados... reindexar no vuelve a abrir un PDF"), aunque D-8 hable de
  reindexar, no de servir una vista.

## En qué me desvié del plan

Ninguna desviación de fondo. La única decisión de diseño no prescripta
explícitamente por el plan es cómo mostrar "citas salientes" sin una tabla
persistida (justificado arriba) y que la página del PDF se ancle al chunk
del resultado en vez de al inicio del fallo.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Sin dependencias nuevas sobre
PR-21.

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 84 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 349 passed, 3 skipped, 23 deselected
```

**De punta a punta, contra los 2 tomos reales ya indexados** (348 + 349,
2.199 chunks, quedaron de PR-21 — no hizo falta reingestar nada):

```
spectre serve --port 8742 --no-browser
curl .../api/fallos/348:113
# Loyola, Sergio Alejandro s/ comercialización de estupefacientes...
# secciones: [('dictamen', None), ('mayoria', None), ('voto', 'Carlos
#   Fernando Rosenkrantz'), ('voto', 'Ricardo Luis Lorenzetti'),
#   ('voto', 'Manuel José García-Mansilla')]   <- exacto el caso de PR-09
# offset_pagina: 6, pdf_disponible: true, citas_salientes: 145
```

Matemática de página, verificada contra el PDF real con `pdfplumber` (no
solo confiando en la fórmula):

```
# fallo 348:113: pagina_inicio=113, offset=6 -> pdf_page 119
pdf.pages[118].extract_text()[:60]
# "DE JUSTICIA DE LA NACIÓN 113 / 348 / ..."   <- coincide

# resultado de búsqueda sobre "voto en disidencia" (seccion=disidencia):
# cita 349:737, pagina_oficial del CHUNK (no del fallo): 739
# fallo 349:737: offset_pagina=6 -> pdf_page 739+6=745
pdf.pages[744].extract_text()[:200]
# "DE JUSTICIA DE LA NACIÓN 739 / 349 / ...(Disidencia de juez Rosatti
#   y del juez Lorenzetti)..."   <- coincide, y es el mismo texto del
#   extracto que devolvió /api/buscar para ese resultado
```

`/api/tomos/348/pdf`: 200, `content-type: application/pdf`, tamaño acorde al
archivo real (~3 MB).

## Dudas que quedaron

- **Un hallazgo de datos, no de este PR**: `jueces` para 348:113 (Loyola)
  vino `['Provincia de San Luis', 'Poder Judicial']` — eso no son jueces,
  es el nombre de una de las partes demandadas (aparece tal cual en el
  cuerpo del fallo: "la acción promovida contra la Provincia de San Luis
  —Poder Judicial—"). Es un error de extracción de `structure.py` (PR-08),
  que mide ~92% de cobertura pero no necesariamente 92% de *corrección* —
  la métrica de PR-08 contaba "tiene jueces", no "los jueces son
  correctos". No lo toqué: está fuera del alcance de este PR (acá solo se
  muestra lo que ya está persistido), pero vale la pena que quede anotado
  antes de mostrarle la vista de fallo a alguien real — un campo de jueces
  incorrecto en una vista legal es peor que uno vacío.
- **Sin URL compartible para un fallo** (ver "qué decidí"): si en algún
  momento se quiere poder mandar un link directo a un fallo (razonable para
  una abogada que quiere compartir un caso), hace falta un router mínimo
  (`location.hash` + `popstate`), que hoy no existe en ninguna parte de la
  UI.
- **`extraer_citas` se recalcula en cada request** — no debería importar en
  la práctica: medido sobre el "Loyola" (348:113, el más citador de los dos
  tomos con 145 citas salientes sobre 118.002 caracteres), 20 corridas dan
  **7,2 ms promedio**. Muy por debajo de cualquier presupuesto de latencia
  razonable; no hace falta cachearlo. Queda anotado por si algún tomo futuro
  con fallos mucho más largos cambia el cálculo.
