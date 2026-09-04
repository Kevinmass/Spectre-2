# Bitácora PR-21 — Búsqueda y resultados

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **Campo de consulta, resultados con cita
`Fallos: 348:145`, fragmento con el término resaltado, etiqueta de sección
(mayoría / disidencia). Acepta: buscar y llegar al fragmento correcto en
menos de 3 segundos sobre 2 tomos indexados.**

## Resultado en una línea

`GET /api/buscar` (`spectre/api/app.py`) envuelve `buscar_hibrido` (PR-15) y
arma, por resultado, `cita`, `caratula`, `seccion_tipo`/`seccion_autor` y un
`extracto` recortado alrededor de la primera aparición de un término de la
consulta. El modelo de embeddings se cachea por instancia de app; si
`sentence-transformers` no está instalado, degrada sola a léxico puro y lo
dice en `modo` (nunca finge `hibrido`). En `spectre/web/`, la pestaña Buscar
tiene el campo de consulta real, con el resultado resaltado en `<mark>` y una
tarjeta con cita/badge de sección/extracto, todo armado con DOM plano (sin
`innerHTML`). **Verificado de punta a punta contra los 2 tomos reales**
(348 + 349, 2.199 chunks, `data/spectre.db`/`data/vectors/` del propio
repo): la primera búsqueda de un proceso recién levantado tarda 21,6 s (carga
del modelo de embeddings, costo único); cada búsqueda siguiente, entre 85 ms
y 140 ms — muy por debajo de los 3 segundos del criterio, que es sobre la
búsqueda en sí.

## Qué hice

### `spectre/api/app.py` — `GET /api/buscar`

- Parámetros: `q` (obligatorio, se rechaza vacío o solo espacios con 422),
  `k`/`candidatos` (mismos defaults que el CLI: 10/50), `anio`, `tribunal`,
  `seccion` (`Literal["mayoria", "voto", "disidencia", "dictamen"]`, 422 si
  no es uno de esos cuatro) y `solo_lexico` — la misma superficie que
  `spectre search buscar` (PR-15), reexpuesta como HTTP.
- Reutiliza `buscar_hibrido` tal cual (ninguna lógica de ranking nueva): la
  API es una capa de presentación sobre PR-15, no una reimplementación.
- **El modelo de embeddings se cachea por instancia de app**
  (`_modelo_cache: dict[str, EmbeddingModel]`, cerrado sobre `crear_app()`).
  Sin esto, cada búsqueda cargaría `sentence-transformers` desde cero — el
  costo que midió esta sesión en 21,6 s — y el criterio de "menos de 3
  segundos" sería imposible de cumplir en la segunda búsqueda, no solo en la
  primera.
- **Degradación a léxico puro si falta `sentence-transformers`**: se llama
  `modelo.embed_uno(consulta)` dentro de un `try`; si tira
  `ModuleNotFoundError`, se seguí sin vector (`buscar_hibrido` ya sabe correr
  así, D-6) y la respuesta lleva `"modo": "solo_lexico"` en vez de
  `"hibrido"` — la UI lo muestra («búsqueda solo por texto») en vez de fingir
  que hubo comparación semántica (D-05 aplicado a la API).
- **`_extracto(texto, terminos)`**: recorta el chunk completo (~400 palabras)
  a una ventana de ~220 caracteres centrada en la primera aparición de algún
  término de la consulta, con elipsis en los bordes si recorta. Sin esto, un
  extracto de "las primeras 220 letras" muchas veces no contiene ni una
  palabra que el usuario buscó (los chunks son ventanas de sección completas,
  no párrafos cortos) — el criterio pide "fragmento con el término
  resaltado", y no hay nada que resaltar si el término no está en la ventana.
- **`_terminos(consulta)`**: la lista de palabras >2 letras de la consulta,
  reusada tanto para ubicar el extracto en el servidor como (la misma lista,
  recalculada) para resaltar en el cliente — no hay un contrato de "el
  servidor manda HTML ya resaltado"; manda texto plano + implícitamente sus
  propios términos (el cliente los vuelve a tokenizar de la consulta que él
  mismo mandó), y decide cómo pintarlos.
- Sin base (`db_path` no existe): `{"consulta": ..., "modo": "sin_datos",
  "resultados": []}`, mismo espíritu honesto que `/api/estado` de PR-20.

### `spectre/web/` — la pestaña Buscar de verdad

- `index.html`: `<form id="form-buscar">` con el campo de texto (arranca
  `disabled` hasta que `/api/estado` confirma que hay algo indexado — no
  tiene sentido ofrecer buscar contra una base vacía) + `<ol id="resultados">`.
- `app.js`:
  - `habilitarBuscador(estado)` reemplaza el mensaje fijo de PR-20 ("la
    búsqueda llega en el próximo PR"): ahora habilita el campo si
    `chunks > 0` y avisa cuántos fragmentos hay.
  - `buscar(consulta)` pega a `/api/buscar`, muestra "Buscando…" mientras
    espera, y "No se encontraron resultados" si la lista vuelve vacía (nunca
    un resultado en blanco silencioso).
  - `resaltarEn(contenedor, texto, terminos)` arma el resaltado con
    `document.createTextNode` / `<mark>` vía DOM, no `innerHTML` — el texto
    de un chunk viene de un PDF de la CSJN, no hay razón para confiar en él
    como HTML seguro, y construir nodos de texto evita el problema de raíz en
    vez de tener que sanitizar.
  - `renderResultado(r, terminos)` arma la tarjeta: cita (`Fallos: N:N`,
    monoespaciada), badge de sección con color propio por tipo, carátula,
    extracto resaltado.
- `style.css`: `.badge-mayoria` / `.badge-voto` / `.badge-disidencia` /
  `.badge-dictamen` con colores distintos a propósito — D-4 dice que
  devolver una disidencia como si fuera la doctrina de la Corte es un riesgo
  profesional, no un bug de calidad; que se distinga a simple vista qué tipo
  de sección es cada resultado es la traducción de esa decisión a la
  interfaz, no una decoración.

### Tests

- **`tests/test_api.py`** (+16 sobre PR-20, incluye los 6 que ya
  existían): validación de `q` (vacío, solo espacios, `seccion` inválida →
  422 los tres); `solo_lexico=true` encuentra por FTS5 y arma
  cita/carátula/`seccion_tipo`/`seccion_autor`/extracto correctos; sin
  resultados da lista vacía con 200 (no error); filtro por año (con/sin
  filtro, mismo texto, cambia el resultado); modo `hibrido` con un
  `EmbeddingModel` falso + `IndiceVectorial` de juguete; caída a
  `solo_lexico` cuando el modelo falso tira `ModuleNotFoundError` en
  `embed_uno` (simula "sin `sentence-transformers`" sin depender de si el
  venv lo tiene instalado); **el modelo se carga una sola vez por instancia
  de app** — 3 búsquedas sobre el mismo `TestClient`, `cargar_modelo` se
  llamó una sola vez (la prueba directa de que el caché existe, no solo que
  "funciona").

## Qué decidí por mi cuenta

- **No hay un mínimo de score ni un corte de relevancia.** La API devuelve
  exactamente lo que `buscar_hibrido` decide, sin filtrar. Lo comprobé a
  propósito con una consulta sin sentido
  (`xyzxyz-esto-no-deberia-existir`) contra los datos reales: devuelve 10
  resultados igual, porque la búsqueda vectorial por vecinos más cercanos
  siempre encuentra "el más cercano" aunque esté lejos en términos
  absolutos. No es un bug de este PR — es el mismo comportamiento que ya
  tenía `spectre search buscar` desde PR-15 — y un reranker o un umbral de
  relevancia es trabajo explícitamente fuera del MVP (plan §8.1, "el salto
  de calidad más grande que queda"). Agregar un corte ad hoc acá hubiera sido
  inventar un número sin el reranker que lo justifique.
- **El modelo de embeddings NO se precarga al arrancar `spectre serve`.**
  Lo pensé como alternativa (cargar el modelo dentro del `lifespan` de
  FastAPI, antes de `yield`, para que hasta la primera búsqueda sea rápida) y
  lo descarté: el `lifespan.startup()` de
  uvicorn tiene que completarse antes de que el servidor empiece a atender
  *cualquier* request — no solo `/api/buscar`, también `/`, `/style.css`,
  `/api/estado`. Precargar el modelo ahí demoraría 21,6 s la aparición de la
  página entera (para una usuaria no técnica, un navegador que abrió pero no
  carga nada por 20 segundos es peor que una página que carga al toque y
  cuya primera búsqueda tarda un rato con un "Buscando…" visible, que es lo
  que ya hay). Evalué además dispararla en un hilo de fondo sin bloquear el
  arranque (`loop.run_in_executor` dentro del `lifespan`, sin `await`), pero
  la descarté para este PR: en los tests que sí entran al `lifespan` real
  (`test_on_startup_...`), ese hilo de fondo quedaría corriendo más allá del
  `with TestClient`, cargando un modelo real en CI/local sin que el test lo
  espere ni lo necesite — riesgo de un test que cuelga la suite unos segundos
  sin beneficio a cambio (el modelo real no se usa en ese test). El costo de
  21,6 s es real, medido, y cae exactamente una vez por proceso de
  `spectre serve` — aceptable para el MVP; si se vuelve un problema real, la
  precarga en background es la solución natural para un PR aparte, con sus
  propios tests dedicados a no bloquear la suite.
- **El extracto no manda HTML pre-resaltado.** El servidor manda texto plano
  y el cliente arma el resaltado (con la lista de términos que el propio
  cliente ya tiene, porque es su propia consulta). La alternativa —el
  servidor manda `<mark>...</mark>` embebido— hubiera significado escapar
  HTML en el server (el texto viene de PDFs, no es HTML de confianza) para
  volver a parsearlo en el cliente; texto plano + resaltado del lado del
  cliente con `createTextNode` es la superficie de ataque más chica posible
  para JSON con texto arbitrario.
- **`_extracto` centra la ventana en el primer término encontrado con `str.find`, no con las posiciones que ya sabe FTS5/embeddings.** Ninguno de los dos índices expone "en qué offset del texto matcheó" (FTS5 sí tiene `snippet()`, pero solo para el lado léxico — un resultado que llegó por el vectorial no tiene ese dato). Una búsqueda de texto simple en Python, aplicada por igual a los dos casos, es menos precisa que `snippet()` pero es la misma lógica para toda la lista fusionada — coherencia sobre precisión de más.

## En qué me desvié del plan

Ninguna desviación de fondo. El plan describe PR-21 en una frase ("campo de
consulta, resultados con cita, fragmento con el término resaltado, etiqueta
de sección") sin especificar la forma de la API ni cómo se recorta el
extracto — esas son las únicas decisiones de diseño no prescriptas
explícitamente, justificadas arriba.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Sin dependencias nuevas sobre
PR-20.

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 83 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 339 passed, 3 skipped, 23 deselected
```

**De punta a punta, contra datos reales.** Primero se indexó el Tomo 349
completo (no estaba indexado todavía en este repo; solo 348 lo estaba desde
PR-19) para tener los "2 tomos indexados" que pide el criterio:

```
spectre ingest 349 --pdf data/tomos/349.pdf
# tomo 349 / estado indexado / calidad digital / etapas 8/8 / fallos 153 / chunks 1087
spectre index status
# 2199 vectores, dimensión 384 — chunks en SQLite 2199 — 0 sin embedding
# chunks en el índice vectorial 2199 — chunks en el índice léxico (FTS5) 2199
```

Con eso, `spectre serve --port 8741 --no-browser` real (contra
`data/spectre.db` / `data/vectors/` del propio repo) y `curl`/`time` contra
`/api/buscar`:

```
time curl ".../api/buscar?q=prescripción+de+la+acción+penal"     # 21.625s (frío: carga el modelo)
#   -> modo=hibrido, primer resultado Fallos: 348:782 (dictamen, PRESCRIPCION
#      DE LA ACCION PENAL en el extracto)
time curl ".../api/buscar?q=despido+injustificado"                # 0.124s
#   -> Fallos: 348:834, Ceballos c/ Ford Argentina, mayoria
time curl ".../api/buscar?q=voto+en+disidencia&seccion=disidencia" # 0.138s
#   -> Fallos: 349:737, seccion_tipo=disidencia, seccion_autor="Horacio Rosatti"
time curl ".../api/buscar?q=recurso+extraordinario&anio=2025"      # 0.123s -> 10 resultados, todos 2025
time curl ".../api/buscar?q=amparo+contra+el+estado&solo_lexico=true" # 0.085s -> modo=solo_lexico
curl ".../"                                                          # 200
curl ".../api/buscar?q="                                             # 422
```

Cada búsqueda después de la primera midió entre 85 ms y 140 ms — el
criterio de 3 segundos sobra de sobra. La única que no lo cumple es la
primera del proceso (21,6 s, carga del modelo), documentada arriba como
decisión consciente, no como una falla oculta.

También se verificó a mano que la respuesta es JSON válido en UTF-8 sin
corrupción: una carátula con "Á" (`Cabrera, Roberto Ángel...`) se veía
mangleada en la terminal de Windows al imprimirla, pero decodificando el
archivo de respuesta explícitamente como UTF-8 con Python el texto es
correcto (`\xc3\x81` = "Á") — el problema era el code page de la consola de
esta sesión, no los datos ni la API.

## Dudas que quedaron

- **Sin corte de relevancia** (ver "qué decidí por mi cuenta"): una consulta
  sin ninguna relación con el corpus igual devuelve `k` resultados. Es
  esperable dado D-6 + el reranker fuera del MVP, pero vale la pena que
  quien revise la UI lo sepa antes de mostrársela a la hermana de Kevin: hoy
  "no hay resultados" solo pasa cuando *ni el léxico ni el vectorial* traen
  nada, no cuando lo que traen es irrelevante.
- **21,6 s en la primera búsqueda de cada proceso.** Documentado y con la
  alternativa de precarga en background evaluada y descartada por ahora (ver
  arriba). Si se vuelve una queja real de uso, la solución queda anotada.
- **No se probó con `[embed]` desinstalado de verdad** (el venv de esta
  máquina lo tiene instalado desde PR-15). El camino de `ModuleNotFoundError`
  se probó con un modelo falso que lo simula (mismo patrón que usa
  `test_cli.py` para `ingest`), no contra un venv real sin torch — cubre la
  rama de código, no el escenario de instalación real; no debería haber
  diferencia porque el `try/except` atrapa la excepción tal cual la lanza
  `ModeloLocalST._cargar()`, pero no se verificó en un entorno realmente
  desprovisto del paquete.
