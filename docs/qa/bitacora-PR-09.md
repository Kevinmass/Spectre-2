# Bitácora PR-09 — Secciones: mayoría, votos, disidencias

Fecha: 03/09/2026
Criterio de aceptación (plan §6): un fallo con votos concurrentes conocido (p.
145 del Tomo 348) se parte en las secciones correctas; ningún texto queda
huérfano.

**La p. 145 cae dentro del fallo "Loyola"** (`348:113`, 52 páginas), no es el
inicio de un fallo. Se parte en: **dictamen + mayoría + tres votos**
(Rosenkrantz, Lorenzetti, García-Mansilla) — exacto. Sobre los tomos 348 y 349
completos, las líneas de **contenido** que quedan fuera de una sección son el
**0,10%** (53 de 51.289): en todos los casos la 2ª línea de un encabezado cuando
el apellido del juez dobla de renglón (`Rosenkrantz`, `García-Mansilla`). Nada de
doctrina queda huérfano.

## Qué hice

### `spectre/corpus/fallo/sections.py`

- **`SeccionFallo(tipo, autor, orden, texto)`** — `tipo ∈ {dictamen, mayoria,
  voto, disidencia}` (el vocabulario que congela el `schema.sql`). `autor` es
  `None` para la mayoría sin firmante nombrado y para el dictamen anónimo; para
  un voto conjunto es `"A, B"`.
- **`partir_secciones(texto)`** — parte el texto del fallo (el que arma
  `structure.texto_del_fallo`, PR-08):
  1. **Encabezados del cuerpo**: `FALLO DE LA CORTE SUPREMA` → mayoría;
     `Dictamen de la Procuración General` → dictamen;
     `voto Del Señor <cargo> Doctor don <nombre>` / `Disidencia Del Señor ...` →
     voto / disidencia. El nombre puede doblar de renglón y dos jueces pueden
     firmar un mismo encabezado (`... don Horacio Rosatti y del Señor Ministro
     Doctor don Ricardo Lorenzetti`) → un solo bloque con dos autores. El
     encabezado va desde su línea hasta `Considerando:` / `Resulta:` /
     `Autos y Vistos` (`_INICIO_CUERPO`).
  2. **Menciones inline** (`voto del juez Fayt, considerando 10`,
     `disidencia de los jueces X y Z). En tales condiciones`) **no** son
     encabezados: se descartan por traer un dígito, `;` o `)`.
  3. **Sumarios** (la cabecera, antes del primer encabezado): párrafos separados
     por un título en MAYÚSCULAS. Cada uno se **atribuye** por su etiqueta al
     pie: `(Voto del juez X)` → al bloque de voto de X (o a la mayoría si X no
     tiene bloque propio); `(Disidencia del juez X)` → al bloque de disidencia
     de X, y si no existe lo **crea** (caso "la Corte por mayoría declaró
     inadmisible" con la disidencia solo en los sumarios); `-Del dictamen ...
     al que la Corte remite-` sin otra etiqueta → dictamen; sin etiqueta →
     mayoría.
  4. Si el fallo no trae **ningún** encabezado (entrada de sumario "Ver fallo"),
     es una sola sección `mayoria` con todo el texto.
- No toca la base.

### `spectre/cli.py`

- **`spectre pdf sections <pdf> [--tomo N] [--cita 348:113]`** — sin `--cita`
  resume el tomo: cuántos fallos tienen dictamen / voto / disidencia, cuántos
  son de una sola sección, y el % de líneas de contenido huérfanas (excluyendo
  marcadores estructurales). Con `--cita` detalla las secciones de ese fallo
  (tipo, autor, palabras). No persiste: mide, como el resto de `pdf`.

### Tests

- **`tests/test_sections.py`** (11; 3 `slow`):
  - `partir_secciones` sobre texto armado a mano: fallo sin encabezados → una
    `mayoria`; texto vacío → `[]`; dictamen + mayoría + voto con sus autores y
    sin huérfanas; sumario atribuido por etiqueta (`(Voto del juez Lorenzetti)`
    → voto; sin etiqueta → mayoría); sumario de disidencia que **crea** la
    sección; encabezado conjunto de dos jueces → una disidencia con `"A, B"`;
    mención inline con `);` y dígitos → no es encabezado.
  - Integración sobre `tomo348_cuerpo_p31-40.pdf`: `348:34` ("Gobierno de la
    Ciudad de Buenos Aires") → `[mayoria, voto(Ricardo Luis Lorenzetti)]`, sin
    huérfanas.
  - **`test_aceptacion_loyola`** (`slow`): `348:113` → dictamen + mayoría + tres
    votos con los autores exactos; ≤ 3 líneas fuera de sección (encabezados
    doblados de renglón).
  - **`test_sin_huerfanos_en_el_tomo[348]` / `[349]`** (`slow`): < 1% de líneas
    de contenido huérfanas sobre el tomo entero.
- **`tests/test_cli.py`** (+2): `pdf sections` resume el tomo; `--cita 348:34`
  detalla las secciones e imprime "voto" y "Ricardo Luis Lorenzetti".

### `CLAUDE.md` / plan / fixtures

- "Estado del código" → PR-09; `tomo348_cuerpo_p31-40.pdf` ahora también sirve a
  PR-09 (el fallo `348:34` trae un voto concurrente).

## Qué decidí por mi cuenta

- **La carátula en versalita del encabezado de voto, más `Considerando:` /
  `Resulta:` como cierre del encabezado.** Es lo único que marca de forma fiable
  el arranque de una opinión. Los delimitadores `FALLO DE LA CORTE` / `Autos y
  Vistos` aparecen también dentro del dictamen y de cada voto, así que no sirven
  para cortar entre votos.
- **Descartar los encabezados que traen dígito / `;` / `)`.** Es lo que separa
  `voto Del Señor Ministro Doctor don Ricardo Luis Lorenzetti` (encabezado real)
  de `voto del juez Fayt, considerando 10` o `disidencia de los jueces X y Z).
  En tales condiciones` (cita inline). Medido: sin este filtro aparecían ~15
  secciones fantasma por tomo.
- **Atribuir los sumarios, no meterlos todos en `mayoria`.** Un sumario con
  `(Disidencia del juez X)` puesto en la mayoría viola el espíritu de D-4
  (devolver una disidencia como doctrina de la Corte). Cada párrafo va a la
  sección que su etiqueta indica; el orden dentro de la sección es: sumarios
  primero, cuerpo después.
- **Sin tipo `sumario` nuevo.** El `schema.sql` congela `tipo IN (mayoria, voto,
  disidencia, dictamen)`. Atribuir evita agregar un tipo y una migración.
- **Crear una sección de disidencia desde un sumario** cuando el fallo la
  menciona en los sumarios pero el cuerpo es un `art. 280` sin voto disidente
  reproducido. Es la única forma de no perder esa doctrina ni etiquetarla como
  mayoría.
- **Orden de las secciones = orden en que aparecen en el texto** (`pos` del
  encabezado). Para las 3-4 entradas mal segmentadas de PR-06/07 (carátulas
  `ps. 43 y 45`) puede quedar `voto` antes que `mayoria`; es fiel al texto
  recibido y no rompe "sin huérfanos".
- **Nombres de juez a Capitalizado**, aceptando partes en minúscula del PDF
  (`Manuel josé` → `Manuel José`, Tomo 349 `Ricardo luis` → `Ricardo Luis`).
- **Sin ruta de persistencia**, como PR-04 a 08 y a pedido de Kevin: función con
  test + `spectre pdf sections`. Llenar la tabla `secciones` lo hace PR-19.
- **Exploración con el texto cacheado.** Extraer los dos tomos con pdfplumber
  tarda ~3 min; lo hice una vez y guardé el resultado en un pickle en el
  scratchpad, y todos los scripts de exploración leyeron de ahí. La suite `slow`
  sí re-extrae (es su punto: correr contra el PDF real de punta a punta).

## En qué me desvié del plan

- **Encadené PR-09 tras PR-08 en la misma sesión.** A pedido de Kevin;
  metodología en `CLAUDE.md` desde PR-07. PR-08 está mergeado a `main` (PR #9),
  la rama `pr-09-secciones` sale de `main` limpio.
- **La "p. 145" del plan no es un inicio de fallo.** Cae dentro de "Loyola"
  (`348:113`). El test de aceptación corre sobre ese fallo, que es el que tiene
  los votos concurrentes.
- **"Ningún texto queda huérfano" se cumple para el contenido, no al 100% de las
  líneas.** El 0,10% que queda fuera son segundas líneas de encabezados de voto
  (el apellido doblado de renglón). El test lo tolera (≤3 en Loyola, <1% por
  tomo) y lo documenta.
- **Medición sobre 348 y 349**, como en PR-08.
- **Reusé el fixture de PR-08** (`tomo348_cuerpo_p31-40.pdf`) en vez de agregar
  uno nuevo: ya contenía un fallo con voto concurrente (`348:34`).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 41 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 171 passed, 9 deselected (~14 s)
./.venv/Scripts/python.exe -m pytest -q -m slow            # -> 11 passed (~7 min, usa 348.pdf y 349.pdf)
```

Medición a mano:

```
./.venv/Scripts/python.exe -m spectre.cli pdf sections data/tomos/348.pdf --cita 348:113
# Fallos: 348:113  Loyola, Sergio Alejandro s/ comercialización de estupefacientes ...
#   [0] dictamen    —                                          ~4700 palabras
#   [1] mayoria     —                                          ~3800 palabras
#   [2] voto        Carlos Fernando Rosenkrantz                ~2300 palabras
#   [3] voto        Ricardo Luis Lorenzetti                    ~4800 palabras
#   [4] voto        Manuel José García-Mansilla                ~3100 palabras

./.venv/Scripts/python.exe -m spectre.cli pdf sections data/tomos/348.pdf
# con dictamen                   20/133
# con >=1 voto                   25/133
# con >=1 disidencia             13/133
# una sola sección               89/133
# líneas de contenido huérfanas  ~0.10%
# (349: dictamen 24/153, voto 24/153, disidencia 14/153, una sola 101/153)
```

## Dudas que quedaron

- **Segundas líneas de encabezado sin atribuir** (`Rosenkrantz`,
  `García-Mansilla`): quedan fuera de toda sección porque `_fin_de_encabezado`
  las consume como parte del encabezado. Son ~2 por fallo con voto y no son
  doctrina. Si molesta, se pueden pegar al `texto` de la sección siguiente.
- **`autor` de las disidencias creadas desde un sumario** sale del texto de la
  etiqueta (`(Disidencia del juez Rosenkrantz)` → `Rosenkrantz`), sin nombre de
  pila. Cuando el mismo juez firma otra sección con nombre completo no se
  unifican (matching por apellido, y hay un typo real en el Tomo 348:
  `Rosenkranzt` vs `Rosenkrantz`).
- **`dictamen.autor` queda en `None`.** El nombre del Procurador está al final
  del bloque (`... Eduardo Ezequiel Casal.`); extraerlo es fácil pero no lo pide
  el plan. Anotado para PR-19 o para cuando se llene `secciones`.
- **Fallos mal segmentados de PR-06/07** (`ps. 43 y 45`): sus secciones salen
  raras (un `voto` antes de la `mayoria`) porque el texto del "fallo" es medio
  fallo. Se resuelve aguas arriba, no acá.
- **Conjueces**: cuando la Corte se excusa entran conjueces (`voto Del Señor
  Conjuez Doctor don ...`); se detectan y se les asigna la sección, pero
  `autor` no distingue ministro de conjuez. Si aguas abajo importa, cruzar
  contra una lista.
