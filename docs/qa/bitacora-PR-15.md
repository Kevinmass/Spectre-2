# Bitácora PR-15 — Búsqueda híbrida

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **fusión RRF de las dos listas; filtros por
año, tribunal y tipo de sección. Un set de 10 consultas de prueba escritas a
mano, con el resultado esperado documentado en el repo.**

## Resultado en una línea

`spectre/search/hybrid.buscar_hibrido` trae candidatos de `IndiceLexico`
(FTS5, PR-14) e `IndiceVectorial` (LanceDB, PR-13), los filtra por metadatos
(`Repo.filtrar_chunks`: año de `fallos.fecha`, `tribunal_origen`,
`secciones.tipo`) y fusiona lo que queda por Reciprocal Rank Fusion
(`k_rrf=60`). Verificado con el modelo real (`sentence-transformers/
paraphrase-multilingual-MiniLM-L12-v2`) sobre el Tomo 348 completo (1.112
chunks, igual que PR-11/13/14): las 10 consultas de
`docs/qa/consultas-PR-15.md` dan el resultado esperado, incluida una
("extradición de un ciudadano extranjero") que el índice léxico **no**
encuentra y el vectorial sí — la razón de ser de D-6.

## Qué hice

### `spectre/db/repo.py`

- **`filtrar_chunks(ids, *, anio=None, tribunal_origen=None,
  tipo_seccion=None)`** — de un conjunto de `chunk_id` candidatos, cuáles
  cumplen los filtros pedidos. Un `JOIN chunks → fallos` (+ `LEFT JOIN
  secciones`), año por `substr(fecha, 1, 4)`. Sin filtros, `set(ids)`. Vive acá
  (no en `search/`) porque cruza `chunks`/`fallos`/`secciones`, y la regla de
  dependencias dice que ese cruce pasa por `db/repo.py`.
- **`get_chunk(chunk_id)`** ya existía (PR-14); no se tocó.

### `spectre/search/hybrid.py` (paquete `search/` nuevo)

- **`_rrf(listas, *, k=60)`** — la fórmula de Cormack et al. (2009): cada
  `chunk_id` suma `1/(k + rango + 1)` por cada lista en la que aparece (rango
  0-based). Fusiona por *rango*, no por el puntaje crudo de cada índice: bm25
  (FTS5) y distancia coseno (LanceDB) no son comparables en la misma escala, y
  RRF evita normalizarlos. `k=60` es la constante de siempre en la literatura
  (Elasticsearch/Weaviate la usan de default); nada en este corpus pide otra.
- **`buscar_hibrido(conn, idx_vectorial, consulta_texto, vector_consulta, *,
  k=10, candidatos=50, anio=None, tribunal_origen=None, tipo_seccion=None)`**
  → `[ResultadoHibrido(chunk_id, score, rank_lexico, rank_vectorial)]`. Trae
  `candidatos` de cada índice (no `k`: un candidato que el filtro descarta no
  debería reducir cuántos sobreviven), **filtra después** de traerlos (ni
  LanceDB ni FTS5 saben de metadatos), y fusiona lo que queda.
  `vector_consulta=None` corre en modo léxico puro — no es un error: D-6 no
  ata la búsqueda a que el modelo real esté instalado.
- `search/` no importa `corpus/` (regla de dependencias del plan §4):
  recibe una conexión ya migrada, un índice ya construido y (si hay) un vector
  ya embebido — embeber texto es cosa de `embed/`.

### `spectre/cli.py`

- **`spectre search buscar <consulta> [--k N] [--candidatos N] [--anio N]
  [--tribunal T] [--seccion mayoria|voto|disidencia|dictamen]
  [--solo-lexico]`** — embebe la consulta con el modelo real (`spectre.embed.
  cargar_modelo`) salvo `--solo-lexico` (para probar sin el extra `[embed]`),
  corre `buscar_hibrido` y muestra cada resultado con su cita, carátula, en
  qué lista(s) apareció y un extracto.

### Tests

- **`tests/test_hybrid.py`** (nuevo, 21 casos; 1 `slow`):
  - **`_rrf` aislada**: la suma por lista da el `1/(k+rango+1)` exacto;
    aparecer en las dos listas supera a aparecer en una sola; una lista sola
    preserva el orden; listas simétricas empatan los extremos; listas vacías
    → `[]`.
  - **`buscar_hibrido` con DB real + `IndiceVectorial` de juguete** (vectores
    de mano, no el modelo real — rápido, corre siempre): fusiona léxico +
    vectorial (el que está en las dos listas rankea primero); sin vector de
    consulta corre en modo solo-léxico; `k` limita el resultado fusionado;
    filtro por año; filtro combinado por tribunal + tipo de sección (y que un
    filtro que no matchea nada da `[]`).
  - **`test_aceptacion`** (`slow`, necesita `data/tomos/348.pdf` **y**
    `[embed]`): pipeline completo (índice → segmentar → metadatos → secciones
    → chunks → repo, embeddings reales → LanceDB) sobre el Tomo 348 entero,
    corre las 10 consultas de `docs/qa/consultas-PR-15.md` y verifica que el
    fallo esperado esté en la posición documentada, más los dos filtros
    (tribunal, tipo de sección).
- **`tests/test_db.py`** (+9): `get_chunk` (existente / inexistente);
  `filtrar_chunks` sin filtros, lista vacía, por año, por tribunal, por tipo
  de sección, combinando los tres, y que un chunk sin `seccion_id` (`NULL`) no
  matchea un filtro de tipo de sección.

### Docs

- **`docs/qa/consultas-PR-15.md`** (nuevo) — las 10 consultas con su porqué,
  el resultado esperado y lo medido, más una sección final de qué demuestran
  en conjunto (los 5 casos donde las dos listas coinciden, el caso donde solo
  el vectorial encuentra algo, el caso donde RRF sin reranker trae más de un
  resultado válido, y los dos filtros).
- `CLAUDE.md`: "Estado del código" → PR-15; nota de que `[embed]` **está
  instalado en el `.venv` de esta máquina** desde esta sesión (sentence-
  transformers 6.0.1 / torch 2.14.0); `## Comandos` + `spectre search buscar`.
- `docs/plan-spectre.md`: casilla PR-15 (§6); §9 → "Próximo: PR-16".

## Qué decidí por mi cuenta

- **Instalar `[embed]` en el `.venv` de esta máquina.** PR-13 había dejado
  pendiente correr su `slow` de aceptación por esta misma razón. Para este PR
  la medición real (10 consultas contra el modelo real) es el criterio de
  aceptación en sí, no un extra — así que instalé el extra (consulté antes:
  Kevin lo confirmó) y corrí `-m slow` completo, no solo el de este PR, para
  no dejar mediciones pendientes de PRs anteriores que ahora sí se pueden
  correr.
- **Filtrar después de traer candidatos, no antes.** Ni LanceDB ni FTS5 saben
  de año/tribunal/sección (esos metadatos viven en `fallos`/`secciones`
  SQLite). La alternativa —traer *todo* de cada índice y filtrar sobre el
  índice entero— no escala (D-5: la colección completa son ~380.000 chunks).
  La consecuencia, documentada en la consulta 9: un fallo que cumple el filtro
  pero no fue candidato de ninguna de las dos listas para esa consulta
  puntual, no aparece. No es un bug, es cómo funciona un filtro post-
  candidatos; si hiciera falta un `WHERE` real sobre todo el corpus habría que
  filtrar *antes* de buscar en LanceDB (soportado) y reconstruir el FTS5 con
  un subconjunto, que es mucho más caro y no lo pide el plan.
- **`candidatos=50` por defecto**, no `k`. Si se trajeran solo `k=10` de cada
  índice antes de filtrar, un filtro restrictivo podría dejar muy pocos o
  ningún resultado aunque existan más candidatos razonables un poco más abajo
  en cualquiera de las dos listas.
- **RRF por rango, no por puntaje normalizado.** Bm25 (sin cota superior) y
  distancia coseno (0 a 2) no son comparables sin inventar una normalización;
  RRF es exactamente el método pensado para evitar eso, y es el que menciona
  la literatura estándar de búsqueda híbrida.
- **Las 10 consultas se eligieron después de correr candidatas reales contra
  el Tomo 348** (no al revés): mezclan cita textual, nombre propio, varios
  conceptos jurídicos parafraseados y los dos filtros — elegidas para que cada
  una muestre algo distinto (ver la sección final de `consultas-PR-15.md`), no
  para maximizar que todas rankeen #1.
- **Persistir `secciones` reales dentro del test `slow`**, no en `db/repo.py`.
  Ningún PR anterior persiste la tabla `secciones` todavía (PR-19 lo hará para
  el pipeline completo); como el criterio de PR-15 pide probar el filtro por
  tipo de sección, el test arma esas filas él mismo con SQL directo
  (`fallo_id, tipo, autor, orden`) a partir de lo que el chunker (PR-11) ya
  calcula por chunk (`seccion_tipo`/`seccion_autor`/`seccion_orden`). No agregué
  un `insert_seccion` a `Repo` porque hoy solo lo usaría este test; si PR-19 lo
  necesita, lo agrega ahí con el diseño que le convenga a la ingesta real.

## En qué me desvié del plan

- Ninguna desviación de fondo. `search/` no existía; se creó con un solo
  módulo (`hybrid.py`), como el plan lo nombra en §4.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Desde esta sesión, `[embed]`
**instalado** (`sentence-transformers==6.0.1`, `torch==2.14.0`).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> todos formateados
./.venv/Scripts/python.exe -m pytest -q -m "not slow"  # -> 266 passed, 3 skipped, 17 deselected
./.venv/Scripts/python.exe -m pytest -m slow tests/test_hybrid.py -v
#   -> 1 passed (test_aceptacion, ~1 min 45 s sobre data/tomos/348.pdf + modelo real)
./.venv/Scripts/python.exe -m pytest -m slow -q        # -> suite `slow` completa (PR-12/13/14/15)
```

(Los 3 `skipped` en la corrida rápida son tests de PR-12 que verifican el
mensaje de error cuando `sentence-transformers` **no** está instalado —
correctamente se saltean ahora que sí está.)

Medido en `test_aceptacion` (y en la exploración previa con un script aparte,
mismo pipeline): 1.112 chunks indexados en las dos listas (igual a
PR-11/13/14). Las 10 consultas y lo medido en cada una están en
`docs/qa/consultas-PR-15.md`; en resumen: 5 casos donde las dos listas
coinciden y el resultado esperado queda primero, 1 caso (extradición) que
**solo** el vectorial encuentra, 1 caso (prescripción) donde RRF trae más de
un resultado válido sin que eso sea un fallo, y los 2 filtros (tribunal,
tipo de sección) funcionando sobre los candidatos ya traídos.

`spectre search buscar` probado a mano con `--solo-lexico` contra una base
chica (sin necesitar el modelo real) y con filtros `--anio`/`--tribunal`/
`--seccion` que excluyen correctamente un resultado que no cumple.

## Dudas que quedaron

- **Sin reranker semántico** (D-6 lo deja fuera del MVP a propósito). RRF
  puede traer más de un resultado "correcto" sin ordenar por cuál es más
  relevante de verdad — visible en la consulta 3 de `consultas-PR-15.md`.
- **El filtro post-candidatos puede dejar afuera un fallo que cumple el
  filtro** si ninguna de las dos listas lo trajo entre los `candidatos`
  (default 50) para esa consulta puntual. Documentado, no es un bug, pero es
  una limitación real que un `--candidatos` más alto atenúa a costa de más
  trabajo por consulta.
- **`substr(fecha, 1, 4)` para el año** asume `fallos.fecha` en formato ISO
  (`YYYY-MM-DD`), que es lo que persiste PR-08. Si algún día `fecha` queda
  `NULL` (fallos sin fecha detectada, ~0% en el Tomo 348 medido en PR-08), esos
  chunks simplemente no matchean un filtro por año — correcto, no se inventa
  un año.
- **Rendimiento de `filtrar_chunks` con miles de candidatos** no se midió; con
  `candidatos=50` por índice (máx. 100 ids) el `IN (...)` es chico. Sobre la
  colección completa (~380.000 chunks, D-5) habría que revisar si conviene un
  índice sobre `fallos.tribunal_origen`/`fecha` — no se agregó (no hace falta
  todavía y es prematuro sin medir).
