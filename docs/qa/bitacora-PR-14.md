# Bitácora PR-14 — Índice léxico

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **FTS5 configurado para español. Buscar
"artículo 14 de la ley 48" devuelve los fallos correctos.**

## Resultado en una línea

`chunks_fts` (FTS5, `unicode61 remove_diacritics 2`) vive dentro de la propia
base SQLite como tabla "external content" sobre `chunks`, sincronizada sola por
triggers (migración `0003_chunks_fts.sql`) — a diferencia del índice vectorial
(PR-13, un archivo LanceDB aparte), acá no hay nada que abrir ni reindexar a
mano. `IndiceLexico.buscar()` corre sobre el Tomo 348 completo (1.112 chunks,
igual que PR-11): el índice queda con 1.112 filas indexadas y buscar "artículo
14 de la ley 48" (48 apariciones reales, verificado aparte con una regex sobre
el texto limpio) devuelve resultados no vacíos, con la frase literal ya en el
primer puesto del ranking bm25.

## Qué hice

### `spectre/db/migrations/0003_chunks_fts.sql`

- **`CREATE VIRTUAL TABLE chunks_fts USING fts5(texto, content='chunks',
  content_rowid='id', tokenize='unicode61 remove_diacritics 2')`** — external
  content: no duplica `texto`, indexa lo que ya vive en `chunks`.
  `remove_diacritics 2` porque SQLite no trae un stemmer en español: sin
  reducir "artículos"/"artículo" a la misma raíz, pero "artículo" y "articulo"
  matchean igual, que es lo que importa para citas legales.
- **Triggers `chunks_fts_ai` / `_ad` / `_au`** (`AFTER INSERT/DELETE/UPDATE ON
  chunks`) — el patrón estándar de FTS5 para external content: el `DELETE`
  manda el comando especial `('delete', old.id, old.texto)`, el `UPDATE` es un
  delete + insert. Disparan también en un borrado en cascada (`fallos`/`tomos`
  con `ON DELETE CASCADE`), así que `db/repo.py` y el job runner no necesitan
  saber que el índice existe.
- **`INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')`** después de crear
  la tabla — puebla el índice si `chunks` ya tenía filas (no pasa hoy: nada
  persiste chunks todavía, eso es PR-19; es gratis no asumirlo).

### `spectre/index/lexical.py` (nuevo en el paquete `index/`)

- **`IndiceLexico(conn, *, tabla="chunks_fts")`** — envuelve la tabla virtual de
  una conexión ya migrada. Sin gestión de esquema ni de conexión propia (eso lo
  resuelve la migración): a diferencia de `IndiceVectorial`, acá no hay un
  archivo aparte que abrir.
- **`buscar(consulta, *, k=10)`** → `[Resultado(chunk_id, rank)]`, mejor
  primero (`rank` = bm25 de FTS5, más negativo = más relevante).
  `_consulta_fts` arma la consulta `MATCH`: extrae los términos con `\w+` y
  manda cada uno entre comillas dobles — un AND implícito de FTS5, y ningún
  carácter de sintaxis que tipee el usuario (`-`, `:`, `*`, `"`, paréntesis...)
  rompe la consulta.
- **`contar()`** — **no** es `SELECT count(*) FROM chunks_fts`. Esa consulta,
  sin `MATCH`, no toca el índice invertido en una tabla external content: lee
  directo de `chunks` y da el mismo número aunque el índice esté vacío o
  desincronizado (lo até con un repro, ver "qué decidí"). Cuenta
  `chunks_fts_docsize` (la tabla-sombra que FTS5 sí mantiene por documento
  indexado) en su lugar.
- **`reconstruir()`** — `INSERT INTO chunks_fts(chunks_fts) VALUES
  ('rebuild')`, para el caso raro de desincronización (una carga masiva que
  deshabilite triggers a propósito).

### `spectre/db/repo.py`

- **`get_chunk(chunk_id)`** — lectura por PK, en el mismo estilo que
  `get_tomo`/`get_fallo`. La necesita `spectre index buscar` (CLI) para
  resolver `chunk_id` → texto/fallo, y sirve igual para PR-15.

### `spectre/cli.py`

- **`spectre index status`** ahora reporta también "chunks en el índice léxico
  (FTS5)".
- **`spectre index buscar <consulta> [--k N]`** (nuevo) — corre la consulta
  contra `IndiceLexico`, resuelve cada `chunk_id` a su fallo (`Fallos: cita`,
  carátula) y muestra un extracto. Mide/prueba a mano; la búsqueda de verdad
  (con el ranking fusionado) es PR-15.

### Tests

- **`tests/test_lexical.py`** (nuevo, 11 casos; 1 `slow`):
  - mecánica: los chunks insertados quedan buscables; orden por relevancia
    (bm25, más menciones rankea primero); `k` limita resultados; consulta sin
    términos reconocibles (`"   "`) → `ValueError`; diacríticos no importan
    ("articulo"/"artículo" matchean igual); caracteres de sintaxis FTS5
    (`"`, `-`, `*`, `(`, `:`) en la consulta no rompen nada; sin match → `[]`.
  - **sincronización real**: borrar un `fallo` (cascada a `chunks`) baja
    `contar()` a 0 y el chunk deja de aparecer en `buscar()`.
  - **`reconstruir()`**: se dropea el trigger de INSERT a mano (simulando una
    escritura que lo saltee), se inserta un chunk que queda fuera del índice
    (`contar() == 0` aunque `chunks` tenga la fila), `reconstruir()` lo repone.
  - **integración `chunker → repo → FTS5`** sobre `tomo348_cuerpo_p31-40.pdf`:
    buscar "Ricardo Luis Lorenzetti" (firma el voto de 348:34, PR-09) encuentra
    el chunk correcto.
  - **`test_aceptacion`** (`slow`, necesita `data/tomos/348.pdf`): pipeline
    completo (índice → segmentar → secciones → chunks → `repo.insert_*`) sobre
    el Tomo 348, `idx.contar() == total` (1.112), y buscar "artículo 14 de la
    ley 48" devuelve resultados con la frase literal entre los primeros 25.
- **`tests/test_db.py`**: `MIGRACIONES` ahora incluye `0003_chunks_fts`;
  `chunks_fts` se agregó a las tablas esperadas del esquema completo.

### Docs

- `docs/plan-spectre.md`: casilla PR-14 (§6) con el resultado medido; §9 →
  "Próximo: PR-15".
- Este archivo.

## Qué decidí por mi cuenta

- **AND implícito de términos, no frase exacta.** `_consulta_fts` manda cada
  palabra entre comillas por separado (`"palabra1" "palabra2" ...`), que en
  FTS5 es "cada una en cualquier orden", no "la frase textual". Elegido porque
  es el comportamiento estándar de un buscador léxico (BM25/Lucene/Postgres
  FTS): forzar frase-exacta-siempre haría inútil una búsqueda de conceptos no
  adyacentes ("responsabilidad civil médica"), que es justamente para lo que
  sirve el lado léxico de D-6 más allá de citas textuales. La consecuencia
  medida: con "de"/"la" tan comunes en español legal, no todo lo que matchea
  repite la frase literal exacta — la ranqueo con bm25 alcanza para que
  aparezca temprano (posición 0 de 25 en la corrida medida), pero **no hay
  garantía de que sea siempre el primer resultado**; ese afinado es RRF (PR-15)
  o, si hiciera falta, una opción de frase exacta explícita en `buscar()`. No
  lo agregué porque el plan no lo pide y estaría adivinando la interfaz que
  necesita PR-15.
- **`contar()` sobre `chunks_fts_docsize`, no sobre `chunks_fts`.** Descubierto
  con un repro directo (ver comando abajo): en una tabla FTS5 "external
  content", una consulta sin `MATCH` —incluido `count(*)`— no usa el índice
  invertido, lee de la tabla de respaldo. Bare `DELETE FROM chunks_fts` o
  dropear el trigger de INSERT y forzar una escritura fuera de sincro **no
  cambia** lo que devuelve `count(*) FROM chunks_fts` (queda pegado al número
  de filas de `chunks`), aunque `buscar()` ya no encuentre esas filas. Si no
  agarraba esto, `spectre index status` y el test de `reconstruir()` habrían
  reportado un número que no refleja el estado real del índice.
- **`get_chunk` en `db/repo.py`, no en `index/lexical.py`.** Es una lectura por
  PK de `chunks`, la regla de dependencias dice que el cruce con la base pasa
  por `repo.py`; `IndiceLexico` no toca `chunks` directo, solo `chunks_fts`.
- **`spectre index buscar` en el CLI**, no solo tests. El criterio de
  aceptación es literalmente "buscar X devuelve los fallos correctos"; tener
  un comando para probarlo a mano (no solo en pytest) hace verificable la
  frase del plan tal cual está escrita, y es consistente con que `pdf …` y
  `embed …` ya sirven para lo mismo en sus PRs.
- **Sin filtrar `k` en el propio `_consulta_fts` ni normalizar acentos a mano.**
  El tokenizer ya resuelve diacríticos; agregar una segunda normalización en
  Python habría sido redundante y una fuente más de desincronización con lo
  que FTS5 realmente indexa.

## En qué me desvié del plan

- Ninguna desviación de fondo. El plan solo pedía "FTS5 configurado para
  español"; agregar `get_chunk` y `spectre index buscar` es soporte mínimo para
  poder ejercer y verificar ese criterio, no una ampliación de alcance hacia
  PR-15 (no hay fusión, no hay filtros, no hay ranking combinado).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). `lancedb` instalado (PR-13);
`sentence-transformers` no (no hace falta para este PR).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 60 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 250 passed, 16 deselected (~70 s)
./.venv/Scripts/python.exe -m pytest -m slow tests/test_lexical.py -v
#   -> 1 passed (test_aceptacion, ~2-3 min sobre data/tomos/348.pdf)
```

Medido en `test_aceptacion` y con un script aparte (mismo pipeline, `k=30`):
total de chunks del Tomo 348 = **1.112** (igual a PR-11); `IndiceLexico.
contar()` = **1.112** (índice y `chunks` perfectamente sincronizados); buscar
"artículo 14 de la ley 48" con `k=30`: **18 de 30** resultados repiten la frase
literal, y el **primer** resultado (posición 0) ya la tiene.

Repro de por qué `contar()` no puede ser `count(*) FROM chunks_fts`:

```python
# tabla vacía de triggers, chunk insertado "fuera de sincro":
# chunks count            -> 1
# select count(*) from chunks_fts       -> 1  (¡lee `chunks`, no el índice!)
# select count(*) from chunks_fts_docsize -> 0  (el número real: no se indexó)
```

`spectre index status` / `spectre index buscar` a mano contra una base tmp con
un chunk sintético: reporta "chunks en el índice léxico (FTS5)  1" y la
búsqueda "articulo 14 de la ley 48" devuelve ese chunk con su cita.

## Dudas que quedaron

- **Ranking sin filtros ni frase exacta.** D-6 promete filtrar por año /
  tribunal / tipo de sección y fusionar con RRF — nada de eso está acá a
  propósito, es PR-15. Tampoco hay una opción de "frase exacta" en `buscar()`;
  si PR-15 la necesita, es un cambio chico (una sola frase entre comillas en
  vez de N de una palabra).
- **`unicode61` sin stemmer.** "recurso"/"recursos" no se unifican. Si hace
  falta, FTS5 no trae stemmer en español nativo; la alternativa sería un
  tokenizer custom o normalizar en la escritura, que **no** se evaluó acá.
- **Tamaño de `chunks_fts` sobre la colección completa** (~380.000 chunks, D-5)
  no se midió — el Tomo 348 (1.112 chunks) es chico comparado con la colección
  entera. Queda para PR-25.
