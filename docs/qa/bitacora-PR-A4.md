# Bitácora PR-A4 — Extractos que empiecen donde corresponde

## Qué pedía el plan

> **PR-A4 `[N]` Extractos que empiecen donde corresponde.** Recortar en borde
> de palabra, y en borde de oración si hay uno cerca.
> *Acepta:* ningún extracto de las 8 consultas de referencia empieza a mitad
> de palabra.

Contexto (§2.4 del plan v2): "extractos que empiezan a mitad de palabra".
`_extracto` cortaba en offsets de carácter crudos (`pos - ventana//3`).

## Qué se hizo

### `spectre/search/palabras_vacias.py` (nuevo)

`PALABRAS_VACIAS` — `frozenset` de 169 función-palabras del castellano
(artículos, preposiciones, conjunciones, pronombres, determinantes, cópulas
frecuentes). **Es el gemelo Python de `PALABRAS_VACIAS` en
`spectre/web/app.js`** (PR-A3); no comparten código (una es Python, la otra
JS servida sin build). Si se toca una, tocar la otra — está dicho en el
docstring del módulo y en `CLAUDE.md`. Exportada desde `spectre.search`.

### `spectre/api/app.py`

- **`_terminos`**: además del corte por longitud (`> 2`), descarta las
  palabras vacías. Sin esto, "responsabilidad del estado" centraba el
  extracto en el primer "del".
- **`_extracto`** reescrito:
  - Si el chunk entero entra en `ventana` (220), se devuelve tal cual (antes
    esto solo pasaba en la rama sin match).
  - Con término encontrado en `pos`: se prefiere **el comienzo de la oración
    que lo contiene**, si esa oración empieza a no más de `ventana // 2`
    caracteres hacia atrás. Fin de oración = `[.?!]` + espacio + **mayúscula**
    (la mayúscula evita cortar en abreviaturas: "art. 14", "inc. b", "Dr.
    Pérez").
  - Si no hay oración cerca, se retrocede `ventana // 3` y se **avanza al
    próximo borde de palabra** (`_borde_palabra_adelante`), sin pasarse de
    `pos` (si se pasara, se retrocede al principio de la palabra que contiene
    `pos`).
  - El fin se lleva a un borde de palabra hacia atrás
    (`_borde_palabra_atras`), garantizando además que el término entre
    (`fin >= pos + 2·ventana//3`).
  - `…` de prefijo solo si el extracto no arranca limpio (ni en `0` ni en
    comienzo de oración); `…` de sufijo si no llega al final del texto.
- Helpers nuevos: `_borde_palabra_adelante`, `_borde_palabra_atras`,
  `_inicio_de_oracion`.

No se tocó la firma de `/api/buscar` ni la forma de la respuesta.

## Qué decidí por mi cuenta

- **La lista de vacías vive en `spectre/search/`, no en `app.py`.** Es una
  cuestión de texto/búsqueda, no de la API, y así queda reutilizable (un
  reranker de PR-C3, por ejemplo). El costo es tener dos copias (Python y
  JS); me pareció mejor que una dependencia npm (rompería "vanilla JS sin
  build", D-15) o un endpoint para servir la lista al navegador.
- **Fin de oración exige mayúscula después del punto.** Es lo que corta bien
  las abreviaturas del lenguaje jurídico ("art.", "inc.", "conf.", "Fallos:"
  —este último ni siquiera lleva punto—). El precio: una oración que
  legítimamente empiece con número o comilla («...») no se detecta como
  comienzo; es raro y el fallback (borde de palabra) igual no corta mal.
- **Preferir la oración aunque quede un poco más largo que `ventana`.** Si el
  comienzo de oración está, digamos, 100 caracteres antes del término, el
  extracto puede pasar de 220 a ~270. Lo acoté con `max_atras = ventana // 2`
  (110): más que eso, el término está muy adentro de una oración larga y
  arrancar ahí no da contexto útil, así que se usa el borde de palabra.
- **No toqué el `chunker` ni la limpieza de texto.** Un caso real ("...que la
  tenía **por probada**. -Del dictamen...") produce un extracto
  `…probada. -Del...` que se ve raro pero **no** corta una palabra: "por
  probada" son dos palabras de verdad. Que "aprobada" aparezca separada, o
  que un dictamen arranque con "-Del", es material de PR-B1 (reflow de
  párrafos), no de esto.

## Qué verifiqué

- **Criterio de aceptación, sobre la base real** (`data/spectre.db`, 2
  tomos), las 8 consultas de `docs/qa/consultas-PR-15.md`, revisando **cada**
  extracto que devolvería `/api/buscar` (todos los pasajes de los 10 fallos
  de cada consulta): comprobar, contra el texto fuente del chunk, que el
  cuerpo del extracto arranca en un borde de palabra (posición 0 o precedida
  por espacio).

  | | |
  |---|---|
  | extractos revisados | **95** |
  | arrancan a mitad de palabra | **0** |
  | arrancan en oración limpia (sin `…` inicial) | 64 |

  Script: `scratchpad/medir_a4.py` (no se versiona).

- **Tests** (`tests/test_api.py`, sección nueva):
  - `test_terminos_saca_palabras_vacias_y_cortas`.
  - `test_extracto_corto_se_devuelve_entero_sin_puntos`.
  - `test_extracto_no_arranca_a_mitad_de_palabra` (texto armado para que el
    recorte crudo caería dentro de una palabra).
  - `test_extracto_prefiere_arrancar_en_una_oracion` (arranca en "La cámara
    admitió…", sin `…`).
  - `test_extracto_termino_cerca_del_inicio_no_lleva_puntos_suspensivos`.
- **Suite completa:** `python -m pytest` → `394 passed, 3 skipped` (antes
  389; +5). `ruff check .` / `ruff format --check .` limpios.

## En qué me desvié del plan

- Nada de alcance. El plan nombra "borde de palabra" y "borde de oración";
  los dos están. Sumé la lista de palabras vacías en `_terminos` (que el plan
  de PR-A3 ya había anticipado que caía acá).

## Dudas que quedaron abiertas

- **Dos copias de la lista de vacías** (Python + JS). Es una lista estática;
  el riesgo de que se desincronicen es bajo, pero existe. Un test que
  compare las dos sería posible (parsear el `Set([...])` de `app.js` desde
  Python) — no lo hice, lo dejé como nota en los dos archivos.
- **El fin del extracto puede cortar a mitad de palabra** en un caso
  degenerado (una "palabra" de más de 220 caracteres, imposible en prosa) —
  hay un fallback que en ese caso acepta el corte crudo del final. El
  criterio de aceptación es sobre el **comienzo**, que sí está garantizado.
- **"art. 14" y similares**: la regla de la mayúscula los evita como falso
  comienzo de oración, pero un `. 3°)` (numeración de considerandos) tampoco
  se toma como comienzo aunque a veces lo sea. Es conservador a propósito.
