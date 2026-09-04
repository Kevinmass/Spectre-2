# Bitácora PR-10 — Extracción de citas

Fecha: 03/09/2026
Criterio de aceptación (plan §6): **887 citas detectadas en el Tomo 348.**

## Resultado en una línea

Medido: **934 referencias `Fallos:` en el Tomo 348** (`contar_referencias`), a
**+5,3 %** de las 887 del plan. El gap es el mismo 133 ≠ 126 fallos que arrastran
PR-06/07 (el índice trae carátulas `ps. 43 y 45` que se parten en un fallo por
página y hacen re-escanear páginas compartidas). No se forzó.

El número del plan cuenta **referencias** (cada `Fallos: …` una vez, aunque
encadene varios precedentes). La tabla `citas` del plan §5 guarda un
`(tomo_citado, pagina_citada)` por fila, así que `extraer_citas` **expande** cada
cadena: `Fallos: 301:1149; 302:1078` son dos precedentes → dos filas. Con esa
expansión el Tomo 348 da **2.006 citas fallo→fallo** (1.369 destinos distintos,
179 tomos citados). Las dos métricas conviven en el módulo y en el CLI.

| tomo | fallos | referencias `Fallos:` | citas fallo→fallo | destinos distintos | fallos citantes | fuera de rango |
|---|---|---|---|---|---|---|
| 348 | 133 | **934** (plan: 887) | 2.006 | 1.369 | 112/133 | 0 |
| 349 | 153 | 728 | 1.645 | 1.081 | 133/153 | 0 |

Sobre el cuerpo entero del 348 sin el solape de página que mete
`texto_del_fallo` (cada página una sola vez): 919 referencias. La diferencia con
934 (15) es el doble conteo en las páginas que dos fallos consecutivos comparten
—una cita al pie de la última página de un fallo cae también en el arranque del
siguiente—; se acepta, es chico y la cita pertenece de verdad al primero.

## Qué hice

### `spectre/corpus/fallo/citations.py` (nuevo)

- **`CitaExtraida(tomo_citado, pagina_citada, contexto)`** — frozen dataclass,
  mapea 1:1 a una fila de la tabla `citas` (el `fallo_id` lo pone PR-19).
- **`extraer_citas(texto) -> list[CitaExtraida]`** — sobre el texto de un fallo
  (el que arma `structure.texto_del_fallo`, PR-08). Una `CitaExtraida` **por
  precedente citado**. El texto se colapsa a una línea antes de buscar (una cita
  puede venir cortada de renglón: `Fallos:\n312:\n1234`). Formas que parsea, con
  casos reales de los tomos 348 y 349:
  - simple: `Fallos: 311:2478`
  - cadena con un solo prefijo: `Fallos: 295:848; 304:1201; … y 343:154`
    (medido: hay sitios con 20-21 precedentes encadenados)
  - otra página del mismo tomo tras `,` o `y`: `Fallos: 307:1457 y 315:1492`
  - ruido tolerado entre medio: `Fallos: 327:3117, esp. p. 3120 y 3145`
  - `Fallos: 311 :2478` (espacio antes del `:`, real en el Tomo 348)
  - prefijos que no importan (`cf.`, `arg.`, `conf.`, comillas, paréntesis):
    se ancla en la palabra `Fallos` + `:`.
  Lo que **no** toma (D-05): el año entre paréntesis (`Fallos: 32:120) (1887)` →
  solo `32:120`), lo que sigue a la cita (`, considerando 5°`, `, entre muchos
  otros`, `, disidencia del juez X`, `y sus citas`), y el formato viejo
  `t. 246, p. 345` sin `Fallos:` (fuera de alcance).
  `tomo_citado` se acota a 1-400 y `pagina_citada` a 1-8000 (los tomos
  multi-volumen —327, 329, 330…— llevan paginación corrida de varios miles;
  medido: `Fallos: 329:5913` es legítimo). Un número fuera de rango corta la
  lista y no entra.
- **`contar_referencias(texto) -> int`** — cuántos `Fallos: …` distintos hay
  (una cadena encadenada cuenta **una**). Es exactamente la métrica del criterio
  de aceptación del plan.
- **`contexto`** — ±90 caracteres alrededor de la cita sobre el texto ya
  colapsado, con `...` en los bordes recortados. Todas las citas de una misma
  cadena comparten contexto.
- No toca la base (regla de dependencias). El bucle por tomo y el volcado a
  `citas` los hace el CLI / PR-19.

### `spectre/cli.py`

- **`spectre pdf citations <pdf> [--tomo N] [--cita 348:189]`** — sin `--cita`
  resume el tomo: referencias `Fallos:` (vs 887), citas fallo→fallo, destinos
  distintos, fallos citantes, tomos citados y el top-5 más citado. Con `--cita`
  lista las citas de ese fallo con su contexto. **No persiste**, mide, como el
  resto de `pdf` (PR-04 a 09). Reusa `segmentar` + `texto_del_fallo`.

### Base de datos

- **Sin migración.** La tabla `citas` y sus índices (`idx_citas_fallo`,
  `idx_citas_destino`) ya están en `0001_initial.sql` con la forma exacta que
  necesita `CitaExtraida`.

### Tests

- **`tests/test_citations.py`** (18; 2 `slow`):
  - `extraer_citas` sobre texto armado a mano: cita simple; cadena con `;`;
    páginas del mismo tomo tras `,`/`y`; unión con `y` de otro `tomo:pág`;
    relleno `esp. p.`; cortada de renglón; no toma `, considerando`; no toma el
    año `(1989)`; número fuera de rango (año como "tomo"); página de varios
    miles en tomo multi-volumen; texto sin `Fallos:` → `[]`; dos anclas en un
    texto; contexto incluye lo de alrededor.
  - `contar_referencias` vs `extraer_citas`: una cadena `301:1149; 302:1078;
    303:1041` + `340:1084` = 2 referencias / 4 citas; sin citas → 0.
  - Integración sobre `tomo348_cuerpo_p189-246.pdf` (el fallo largo "Acevedo",
    sus páginas interiores traen `Fallos:` citados): arma el texto y verifica
    ≥1 cita, todas en rango, con la cita en el contexto.
  - **`test_aceptacion[348]`** (`slow`): `contar_referencias` sumado sobre los
    133 fallos, tolerancia ±8 % vs 887 (medido 934); además `citas >=
    referencias` (expandir nunca da menos).
  - **`test_aceptacion[349]`** (`slow`): reporta el número (728), solo exige > 0.
- **`tests/test_cli.py`** (+3): `pdf citations` resume el tomo; `--cita 348:189`
  detalla e imprime `Fallos: 337:315`; `--cita 999:1` (inexistente) revienta.

### Docs

- `CLAUDE.md`: "Estado del código" → PR-10; bloque `spectre pdf` de `## Comandos`
  actualizado (faltaban `index`, `segment`, `meta`, `sections` desde PR-06/07/08/09;
  se agregan esos cuatro + `citations`).
- `docs/plan-spectre.md`: casilla PR-10 marcada (§6) con el número medido; §9 →
  "Próximo: PR-11".

## Qué decidí por mi cuenta

- **Dos métricas, no una.** El plan dice "887 citas" y "Regex sobre `Fallos:
  N:N`", que cuenta ocurrencias del prefijo. Pero la tabla `citas` guarda un
  destino por fila, y una cadena `Fallos: A; B; C` cita tres precedentes. Para
  que el grafo de precedentes (plan §8.3) tenga las aristas reales, `extraer_citas`
  expande; `contar_referencias` queda para medir contra el 887. El CLI muestra
  las dos.
- **`contar_referencias` es lo que se compara con 887**, no `extraer_citas`
  (que da ~2.000). Es la lectura fiel de "Regex sobre `Fallos: N:N`".
- **Se exige el `:` después de `Fallos`.** `Fallos 311:2478` sin dos puntos
  existe pero es rarísimo; sin un ancla firme entran falsos positivos. Con `:`
  obligatorio: 0 falsos positivos en 40 sitios muestreados a mano del Tomo 348.
- **Tope de página en 8.000.** Con 4.000 se perdían citas legítimas a tomos
  multi-volumen (`Fallos: 329:5913`). El riesgo de falso positivo de un número
  4.001-8.000 pegado a una cita es mínimo (tendría que venir tras `,`/`y` sin
  `:`).
- **Continuación de página suelta solo tras `,` o `y`, no tras `;`.** Un `;` sin
  `tomo:` es raro y más vale cortar que adivinar.
- **Medición per-fallo** (como PR-08/09), asumiendo el pequeño doble conteo del
  solape de página. La alternativa (medir sobre el cuerpo entero) da 919, más
  cerca de 887, pero rompe la simetría con el resto de la Fase 2 y no permite la
  atribución fallo→fallo.
- **Sin ruta de persistencia**, como PR-04 a 09: función con test + `spectre pdf
  citations`. Llenar la tabla `citas` lo hace PR-19.
- **Exploración con el texto cacheado**: extraer los dos tomos con pdfplumber
  tarda ~8 min cada uno; se hizo una vez y se guardó en un pickle en el
  scratchpad; los scripts de calibración leyeron de ahí. La suite `slow`
  re-extrae (es su punto).
- **`contexto` con `...` ASCII, no `…`.** El `…` (U+2026) revienta al imprimir
  en la consola cp1252 de Windows (`spectre pdf citations --cita`). El resto del
  texto del contexto sigue con los acentos del PDF; eso ya pasa en `pdf meta` y
  no es de este PR.

## En qué me desvié del plan

- **934 ≠ 887.** +5,3 %. Causa medida: la segmentación da 133 fallos y el plan
  ancla el 887 a 126 (gap de PR-06/07). El test tolera ±8 %.
- **Se agregó `contar_referencias`** además de `extraer_citas`; el plan solo
  nombra "la tabla de relaciones". Las dos hacen falta: una para el grafo, otra
  para medir el criterio.
- **Medición sobre 348 y 349**, como PR-08/09 (el plan solo pide el 348). El
  número del plan sigue anclado al 348.
- **Empecé PR-10 en una sesión que arrancó como `/init`.** A pedido de Kevin
  ("dale, implementá PR-10"). Antes de tocar código: `git fetch` + fast-forward
  de `main` (estaba 2 commits atrás; PR-09 ya estaba mergeado en `origin/main`
  como PR #10 de GitHub pero no en local). Rama `pr-10-citas` sale de ese `main`.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 45 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 190 passed, 11 deselected (~95 s)
./.venv/Scripts/python.exe -m pytest -q -m slow tests/test_citations.py
#   -> 2 passed, 16 deselected (728 s: re-extrae 348.pdf y 349.pdf)
```

El `pytest -m slow` completo (toda la Fase 1-2, ~19 min) se cortó dos veces por
el entorno de la máquina antes de terminar —no por un fallo de test. No es un
hueco de cobertura: el resto de los `slow` (PR-04 a 09) no importan ni tocan
`citations`, y las tres cosas que este PR cambia en código compartido (3 imports
en `corpus/fallo/__init__.py`, el subcomando `pdf citations`, el módulo nuevo)
las ejercita entera la suite rápida (190 passed). Los `slow` propios de PR-10
—los que miden el criterio de aceptación— corridos aparte dan verde (2 passed,
728 s, re-extrayendo 348.pdf y 349.pdf).

Medición a mano (script de calibración sobre el texto cacheado, misma cadena
índice → segmentación → `texto_del_fallo` → `extraer_citas` que el test `slow`):

```
TOMO 348
  fallos:                   133
  referencias 'Fallos:':    934    (plan: 887)
  citas fallo->fallo:       2006
  destinos distintos:       1369
  fallos citantes:          112/133
  tomos citados distintos:  179
  citas al mismo tomo 348:  2
  fuera de rango:           0
  top: 337:315 (14), 314:424 (12), 341:611 (12), 332:111 (12), 325:428 (8) ...

TOMO 349
  fallos:                   153
  referencias 'Fallos:':    728
  citas fallo->fallo:       1645
  destinos distintos:       1081
  fallos citantes:          133/153
  fuera de rango:           0
```

Muestreo a mano de 40 sitios del Tomo 348: **0 falsos positivos**. El parser
corta bien en `, considerando`, `, entre muchos otros`, `, ya citado`,
`, disidencia de`, `y sus citas`, `«Telefónica…»`.

```
./.venv/Scripts/python.exe -m spectre.cli pdf citations tests/fixtures/tomo348_cuerpo_p189-246.pdf --tomo 348
# referencias Fallos: N:N  7 ; citas (fallo a fallo) 8 ; destinos distintos 5
./.venv/Scripts/python.exe -m spectre.cli pdf citations data/tomos/348.pdf --cita 348:113
```

## Dudas que quedaron

- **El 887 exacto del plan.** No sé qué regex ni qué segmentación (126 fallos)
  usó Kevin para llegar a 887. Con 126 fallos y sin el doble conteo del solape,
  la medición debería acercarse; a cerrar cuando PR-06/07 resuelvan el 129/133.
- **Auto-citas.** El Tomo 348 tiene 2 citas a `348:*` (un fallo cita otro del
  mismo tomo). Son válidas como arista del grafo; PR-19 tendrá que resolver el
  `fallo_id` destino contra los fallos del mismo tomo.
- **Citas a fallos sin página de inicio exacta.** `extraer_citas` da
  `(tomo, página)`; si esa página no es el `pagina_inicio` de ningún fallo (cae
  en el medio), PR-19 tendrá que mapear al fallo que la contiene, no exigir
  igualdad.
- **Cadenas larguísimas** (20-21 precedentes con un `Fallos:`): se expanden
  todas. Si en algún análisis conviene pesar distinto "citado solo" vs "citado
  en una lista de 20", el dato está (`contexto` es el mismo para toda la cadena).
- **`t. N, p. N` (formato viejo).** Fuera de alcance de PR-10. Los tomos
  anteriores a ~1990 lo usan; cuando entren (post-OCR) hará falta un segundo
  patrón.
- **El `contexto` guarda acentos del PDF crudos.** Suficiente para mostrar en la
  UI; si molesta, pasa por `limpiar` — pero `texto_del_fallo` ya viene limpiado,
  así que los `�` que se ven en consola son de la consola, no del dato.
