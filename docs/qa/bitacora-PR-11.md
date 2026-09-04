# Bitácora PR-11 — Chunker consciente de secciones

Fecha: 03/09/2026
Criterio de aceptación (plan §6): **ningún chunk con texto de dos secciones.**
Referencia: el cuerpo del Tomo 348 des-hifenado (~333.000 palabras) a 400
palabras con 80 de solape da **~1.041 chunks** contando global. "Muy lejos"
indica que la limpieza o la segmentación se rompieron.

## Resultado en una línea

**0 chunks fuera de su sección** en el Tomo 348 y el 349 — cada chunk es una
ventana contigua de palabras de **una sola** `SeccionFallo`, por construcción.
El Tomo 348 da **1.112 chunks** (referencia global 330.840 / 320 = 1.033; +7,6 %,
el redondeo por sección: 197 secciones, cada una cierra su última ventana). El
99 % de los chunks hereda su página oficial ubicándose en el texto por página;
el 1 % restante cae en la página de inicio del fallo (no se inventa).

| tomo | fallos | secciones | chunks | ref. global | fuera de su sección | página ubicada |
|---|---|---|---|---|---|---|
| 348 | 133 | 197 | **1.112** | 1.033 (330.840/320) | **0** | 1.099/1.112 (98,8 %) |
| 349 | 153 | 226 | 1.087 | 970 (310.427/320) | **0** | 1.070/1.087 (98,4 %) |

El cuerpo des-hifenado del 348 mide **330.840 palabras**, igual que en PR-05
(el plan fijó 332.999 para PR-11; la diferencia de 0,65 % ya estaba anotada en
PR-05). La mediana de palabras por chunk es 400; la media, 371 (las colas de
sección tiran para abajo).

## Qué hice

### `spectre/chunking/chunker.py` (nuevo paquete `chunking/`)

- **`ventanas(palabras, *, objetivo=400, solape=80) -> list[list[str]]`** — la
  ventana deslizante pura sobre una lista de palabras. Paso = `objetivo - solape`
  (320). Una lista más corta que `objetivo` es una sola ventana. La última llega
  hasta el final; **no se abre una ventana nueva si lo que queda ya está entero
  en la anterior** (`i + solape >= len`). Parámetros fuera de
  `0 <= solape < objetivo` → `ValueError`.
- **`Chunk(cita, seccion_tipo, seccion_autor, seccion_orden, orden,
  pagina_oficial, texto, n_palabras)`** — frozen dataclass, mapea a una fila de
  `chunks` (el `fallo_id` / `seccion_id` los resuelve PR-19).
- **`fragmentar_seccion(seccion, *, cita, pagina_inicio, paginas_norm, ...)`** —
  los chunks de **una** sección. El texto sale de `seccion.texto` y de nada más:
  por eso un chunk nunca mezcla mayoría con disidencia (D-4), no hay que
  "cuidarlo", es imposible.
- **`fragmentar_fallo(secciones, paginado, *, cita, pagina_inicio, ...)`** —
  concatena los chunks de cada sección, en orden. `paginado` es
  `structure.texto_del_fallo_paginado(...)`.
- **Herencia de página**: `ubicar_pagina(chunk_norm, paginas_norm)` busca el
  arranque del chunk (primeros 80, si no 40 caracteres, sin dobles espacios) en
  el texto de cada página del fallo y devuelve la primera que lo contiene, o
  `None`. Si es `None`, el chunk hereda `pagina_inicio` del fallo (D-05: no se
  inventa una página exacta, se usa la del fallo).
- No toca la base. `modelo_embedding` / `embedding_at` los pone PR-12/13.

### `spectre/corpus/fallo/structure.py`

- **`texto_del_fallo_paginado(...) -> list[tuple[int, str]]`** — el mismo texto
  limpio del fallo que arma `texto_del_fallo`, pero troceado por página oficial.
  `"\n".join(t for _, t in paginado)` reproduce `texto_del_fallo(...)` **exacto**
  (test de estabilidad en `test_structure.py` vía la suite `slow` de PR-08, que
  sigue en verde). `texto_del_fallo` ahora es un wrapper de una línea sobre esta.
  El chunker lo necesita para heredar `pagina_oficial` sin volver a abrir el PDF.

### `spectre/cli.py`

- **`spectre pdf chunks <pdf> [--tomo N] [--cita 348:34] [--objetivo 400]
  [--solape 80]`** — sin `--cita` resume el tomo: fallos, secciones, chunks,
  referencia global, chunks/fallo, mediana de palabras, **chunks fuera de su
  sección** (verificado como "ventana contigua de palabras de su sección" → 0),
  y cuántos chunks heredan la página por texto vs por caída a `pagina_inicio`.
  Con `--cita` lista los chunks de ese fallo (sección, autor, página, palabras,
  arranque). **No persiste**, mide, como el resto de `pdf`.

### Base de datos

- **Sin migración.** La tabla `chunks` y sus índices (`idx_chunks_fallo`,
  `idx_chunks_modelo`) ya están en `0001_initial.sql`.

### Tests

- **`tests/test_chunker.py`** (15; 2 `slow`):
  - `ventanas`: lista vacía → `[]`; texto corto / justo el objetivo → 1 ventana;
    700 palabras → 2 con las 80 del solape idénticas entre ventana N y N+1;
    1.000 → `[400, 400, 360]`; no abre una 2ª ventana de puro solape;
    parámetros inválidos → `ValueError`.
  - `fragmentar_seccion` / `fragmentar_fallo`: hereda cita, tipo, autor, orden;
    ningún chunk es subsecuencia de **otra** sección; hereda la página por texto
    (145 vs 146) y cae en `pagina_inicio` cuando no está.
  - Integración sobre `tomo348_cuerpo_p31-40.pdf`: `348:34` (mayoría + voto de
    Lorenzetti) → chunks que son ventanas contiguas de su sección, con la cita
    heredada.
  - **`test_aceptacion[348]` / `[349]`** (`slow`): `fuera_de_seccion == 0`;
    `ubicados / total > 0,95`; para el 348, `total` entre el 90 % y el 120 % de
    la referencia global (medido 1.112 vs 1.033).
- **`tests/test_cli.py`** (+3): `pdf chunks` resume; `--cita 348:34` lista con
  "mayoria" / "voto" / "Ricardo Luis Lorenzetti"; `--solape 400` (≥ objetivo)
  revienta.

### Docs

- `CLAUDE.md`: "Estado del código" → PR-11 (paquete `chunking/` ya no es
  objetivo); bloque `spectre pdf` de `## Comandos` + `chunks`.
- `docs/plan-spectre.md`: casilla PR-11 marcada (§6) con el número medido; §9 →
  "Próximo: PR-12".

## Qué decidí por mi cuenta

- **Fragmentar por sección, no por fallo con un guardia.** El plan dice "nunca
  cruza el borde de D-4". La forma robusta de garantizarlo es que el chunker
  reciba una sección por vez: el texto de un chunk sale de `seccion.texto` y de
  ninguna otra parte. No hay chequeo de borde que pueda fallar.
- **Ventana por palabras (`str.split()`), no por caracteres ni tokens.** El plan
  habla de "400 palabras con 80 de solape". El chunk pierde los `\n` internos
  (se re-une con espacio simple); da igual para embeber.
- **`texto_del_fallo_paginado` nuevo, `texto_del_fallo` como wrapper.** El texto
  del fallo perdía los bordes de página al concatenarse; sin eso el chunk no
  puede heredar `pagina_oficial`. El wrapper garantiza que PR-08 y PR-09 (que
  llaman `texto_del_fallo`) ven exactamente lo de antes.
- **Herencia de página por búsqueda de substring**, no reconstruyendo offsets.
  `partir_secciones` re-arma el texto de cada sección (mueve sumarios), así que
  no hay un mapeo char→página confiable. Buscar el arranque del chunk en el
  texto de cada página anda para el 98-99 % y es simple. El resto cae en
  `pagina_inicio` del fallo.
- **La verificación de D-4 en el CLI/test es "el chunk es una ventana contigua
  de palabras de su sección"**, no "su texto no aparece en otra sección".
  Medí que sobre el 349 hay 4 chunks cuyo texto **también** aparece textual en
  otra sección — pero no porque el chunker cruce un borde, sino porque
  `partir_secciones` produce dos secciones con texto duplicado en los ~3 fallos
  mal segmentados de PR-06/07 (`ps. 43 y 45`) y en secciones cortas de puro
  `art. 280`. La subsecuencia-contigua-de-su-sección da 0 en los dos tomos y es
  la propiedad que importa.
- **Tolerancia del 90-120 % sobre la referencia global** en el test del 348. El
  número real es por sección y siempre da más que la cuenta global (cada sección
  redondea para arriba su última ventana). 1.112 está a +7,6 %.
- **Sin ruta de persistencia**, como PR-04 a 10: función con test + `spectre pdf
  chunks`. Llenar la tabla `chunks` lo hace PR-19.
- **Exploración con el texto cacheado** (pickle de los dos tomos en el
  scratchpad); la suite `slow` re-extrae.

## En qué me desvié del plan

- **1.112 ≠ ~1.041.** +7,6 % sobre la cuenta global. Causa: el chunking real es
  por sección (197 en el 348), y cada sección cierra su última ventana aunque
  sean pocas palabras. La referencia del plan (`palabras / 320`) ignora los
  bordes de sección. El test tolera 90-120 %.
- **Cuerpo = 330.840 palabras, no 332.999.** Es el número que ya midió PR-05
  (0,65 % de diferencia con lo que el plan anotó para PR-11). El pipeline está
  intacto.
- **`chunking/` importa de `corpus/fallo`.** La regla del plan prohíbe
  `corpus/ -> index|embed` y `search/ -> corpus`; no dice nada de `chunking/`.
  El flujo natural es parsear → fragmentar → embeber, así que `chunking/` corriente
  arriba consume `corpus/fallo` (secciones + texto por página). No importa
  `embed/` ni `index/`.
- **Medición sobre 348 y 349**, como PR-08/09/10 (el plan ancla el número al
  348).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 49 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 208 passed, 13 deselected (~60 s)
./.venv/Scripts/python.exe -m pytest -q -m slow tests/test_chunker.py
#   -> 2 passed, 15 deselected (799 s: re-extrae 348.pdf y 349.pdf)
```

El refactor de `texto_del_fallo` (ahora wrapper de `texto_del_fallo_paginado`) no
cambia su salida: los tests rápidos de `test_structure.py` / `test_sections.py` /
`test_citations.py`, que lo llaman sobre el fixture y comparan metadata y texto
exactos, siguen en verde en los 208.

Medición a mano (script de calibración sobre el texto cacheado, misma cadena
que el test `slow`):

```
TOMO 348
  fallos:                   133
  secciones:                197
  chunks:                   1112
  cuerpo (des-hifenado):    330840 palabras   (plan PR-11: 332.999; PR-05: 330.840)
  referencia global:        330840 / 320 = 1033   (plan: ~1.041)
  palabras/chunk:           mediana 400, media 371
  chunks fuera de su seccion: 0
  pagina dentro del rango:  1095/1112
  pagina ubicada por texto: 1099/1112  (98.8%)

TOMO 349
  fallos 153, secciones 226, chunks 1087, cuerpo 310427
  chunks fuera de su seccion: 0
  pagina ubicada por texto: 1070/1087  (98.4%)
```

`spectre pdf chunks tests/fixtures/tomo348_cuerpo_p31-40.pdf --tomo 348` → 3
fallos, 4 secciones, 6 chunks, 0 fuera de su sección, 6/6 páginas ubicadas.
`--cita 348:34` → `[0.0] mayoria` y `[1.0] voto  Ricardo Luis Lorenzetti`, cada
uno en la p. 34.

## Dudas que quedaron

- **17 chunks del 348 con `pagina_oficial` fuera de `[pagina_inicio,
  pagina_fin]`.** Son colas de fallo que caen en la página que el fallo comparte
  con el siguiente (antes de su carátula): `texto_del_fallo_paginado` incluye esa
  página y `pagina_fin` del segmentador es `siguiente.pagina_inicio - 1`. La
  página es correcta; el rango del segmentador es el que se queda corto por 1.
  PR-19 debería guardar `pagina_fin = pagina_inicio_siguiente` cuando comparten
  pie, o aceptar `pagina_fin + 1`.
- **Secciones con texto duplicado** (los ~3 fallos `ps. 43 y 45` de PR-06/07 y
  algún `art. 280`): sus chunks salen de una de las dos copias. Se resuelve
  aguas arriba (cerrar el 129/133 → 126), no en el chunker.
- **El solape es de palabras, no de oraciones.** Un chunk puede empezar a mitad
  de oración. Para búsqueda semántica con el modelo chico del MVP alcanza; si
  PR-15 muestra cortes feos, se puede ajustar el límite a la oración más cercana.
- **`Chunk.seccion_autor`** arrastra lo que dé `partir_secciones` (apellido solo
  para disidencias creadas desde un sumario, "A, B" para votos conjuntos). No lo
  toca PR-11.
- **Fallos sin secciones** (texto vacío): `partir_secciones` devuelve `[]` y el
  fallo no genera chunks. Son las entradas de índice "Ver fallo" sin cuerpo;
  correcto no fabricar un chunk vacío.
