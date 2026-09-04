# Bitácora PR-13 — Índice vectorial

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **indexar el Tomo 348 completo y recuperar el
vecino más cercano de un chunk conocido.**

## Resultado en una línea

`IndiceVectorial` (LanceDB, `data/vectors/`) guarda un vector por chunk
(`chunk_id`, `modelo`, `vector`) y `buscar(v, k)` devuelve los `k` `chunk_id` más
cercanos por coseno. La escritura (`upsert`, `merge_insert` sobre `chunk_id`) es
**idempotente**: reintentar una indexación cortada no duplica. Verificado en
LanceDB real con vectores de juguete y con el pipeline `chunker → índice` sobre
el fixture; el criterio completo (Tomo 348 + embeddings reales) es un test
`slow` que necesita el extra `[embed]` y **no se corrió en esta sesión** (falta
`sentence-transformers` en el venv).

## Qué hice

### `spectre/index/vectors.py` (paquete `index/` nuevo)

- **`IndiceVectorial(ruta, *, dimension=None, tabla="chunks")`** — envuelve una
  tabla LanceDB. Perezoso: no abre nada hasta que se usa. Si no se pasa
  `dimension` y la tabla existe, la lee del esquema; si difiere → `ValueError`.
- **`upsert(filas)`** — `filas` = `(chunk_id, vector, modelo)`. `merge_insert`
  sobre `chunk_id` (`when_matched_update_all` + `when_not_matched_insert_all`):
  correrlo dos veces deja lo mismo. **Dedup por `chunk_id` en la entrada,
  último gana** — LanceDB rechaza un `merge_insert` con claves repetidas y "el
  último" es lo que espera un reintento. Valida la dimensión.
- **`buscar(vector, *, k=10)`** — `[Vecino(chunk_id, distancia)]` por coseno
  (0 = misma dirección). Lista vacía si el índice no existe o está vacío.
- **`contar()`**, **`ids()`** (los `chunk_id` ya indexados),
  **`modelos()`** (filas por modelo — si hay más de uno, quedó a medio
  reindexar), **`vaciar()`** (drop de la tabla, para rehacer con otra
  dimensión).
- `lancedb` / `pyarrow` se importan perezoso; si faltan → `ModuleNotFoundError`
  claro (D-05).

**Reanudable**: qué chunks rehacer lo decide `Repo.chunks_pendientes_de_
embedding` en SQLite (PR-12); el índice solo tiene que ser idempotente, y lo es.
Cortar el pipeline entre "upsert" y "marcar embebido en SQLite" y reanudar
re-embebe y re-`upsert`ea ese lote sin duplicar.

### `spectre/cli.py`

- **`spectre index status`** — `vectors_dir`, cuántos vectores hay y de qué
  dimensión, el desglose por modelo, y (si la base existe) chunks en SQLite /
  sin embedding / ya en el índice vectorial. Mide, no persiste.

### `pyproject.toml`

- **`lancedb>=0.13,<1.0`** como dependencia **dura** (no extra). Arrastra
  `pyarrow` + `numpy`, **no torch**: es moderada y es el almacenamiento elegido
  por D-5, así que CI la instala y los tests del índice corren de verdad en CI.
- Se instaló en el `.venv` de esta máquina (`pip install "lancedb>=0.13"` →
  lancedb 0.38.0, pyarrow 25.0.1, numpy 2.5.2). Antes no había numpy; ahora sí,
  como dep transitiva. Ningún módulo del proyecto importa numpy directo.

### Base de datos

- **Sin migración.** La tabla `chunks` ya existe; el índice vectorial es un
  archivo aparte (LanceDB), no una tabla SQLite.

### Tests

- **`tests/test_vectors.py`** (12; 1 `slow`; `importorskip("lancedb")`):
  - mecánica: `upsert` + `buscar` + `contar`; el vecino más cercano del vector
    de un ítem es ese ítem (distancia ~0); índice vacío/inexistente → `[]`.
  - **idempotencia / reanudable**: mandar el lote A, y después A+B solapados,
    deja `|A ∪ B|` filas sin duplicar.
  - `upsert` reemplaza vector y modelo de un `chunk_id` existente.
  - `modelos()` muestra el split cuando hay una reindexación a medias.
  - dimensión incompatible al escribir o al reabrir → `ValueError`.
  - **persistencia**: reabrir `IndiceVectorial` en la misma ruta ve las filas y
    lee la dimensión del esquema.
  - `vaciar()` permite rehacer con otra dimensión.
  - **integración `chunker → índice`** sobre `tomo348_cuerpo_p31-40.pdf` con
    embeddings **falsos** deterministas: se indexan todos los chunks y el vecino
    más cercano del vector de un chunk conocido es ese chunk.
  - **`test_aceptacion`** (`slow`, `importorskip("sentence_transformers")`):
    pipeline entero sobre el Tomo 348 (segmentar → chunk → `modelo.embed` en
    lotes de 256 → `upsert`), `contar() == nº de chunks`, y el vecino más
    cercano del embedding de un chunk conocido es ese chunk (distancia < 1e-3).
- **`tests/test_cli.py`** (+3): `index status` con índice vacío y sin base; con
  vectores y chunks (cuenta "2 vectores", "chunks en SQLite", "chunks en el
  índice vectorial"); `index` sin acción revienta.

### Docs

- `CLAUDE.md`: "Estado del código" → PR-13; `## Comandos` + `spectre index
  status`; nota de que `lancedb` es dep dura y CI la instala.
- `docs/plan-spectre.md`: casilla PR-13 (§6); §9 → "Próximo: PR-14".

## Qué decidí por mi cuenta

- **`lancedb` como dependencia dura, no extra.** A diferencia de
  `sentence-transformers` (que D-7 hace explícitamente intercambiable y arrastra
  torch), LanceDB es *el* almacenamiento vectorial que fija D-5. Es moderada
  (pyarrow + numpy, sin torch) y conviene que CI la ejercite de verdad. El
  import sigue siendo perezoso: `corpus/` no la toca.
- **Se instaló `lancedb` en el `.venv`.** Para poder escribir y **correr** los
  tests del índice en esta sesión (el `.venv` no lo tenía). Es lo mismo que hará
  `pip install -e ".[dev]"` con el `pyproject` nuevo.
- **Métrica coseno explícita** (`.metric("cosine")`). El modelo por defecto
  normaliza (PR-12), así que L2 daría el mismo orden, pero pedir coseno
  explícito lo hace robusto a un modelo que no normalice.
- **`chunk_id` es la PK de `chunks` en SQLite**, no un id propio del índice. El
  índice es una proyección de `chunks`; unir por `chunk_id` es directo.
- **Dedup de la entrada de `upsert`, último gana.** LanceDB no lo hace y aborta;
  un reintento que reprocesa la misma cadena manda ids repetidos entre lotes.
- **`db.list_tables()` devuelve un objeto** (`ListTablesResponse`) en lancedb
  0.38, no una lista: `"chunks" in db.list_tables()` da `False`. Se lee
  `.tables` (o `list(res)` en versiones viejas) con un helper.
- **`spectre index status` y nada más de CLI.** Indexar de verdad necesita el
  pipeline entero (embeddings) y eso es PR-19; buscar necesita embeber la
  consulta y eso es PR-15. `status` alcanza para ver el estado del índice.
- **Sin `create_index` (IVF/HNSW).** Con ~1.100 vectores por tomo (y ~380.000
  la colección entera) el flat search de LanceDB va sobrado; construir un índice
  ANN es optimización de PR-25 si hace falta.

## En qué me desvié del plan

- **El criterio de aceptación completo no se ejecutó**: "indexar el Tomo 348
  completo" necesita embeddings reales (extra `[embed]`, torch) que el venv no
  tiene. El test está escrito (`slow`, `importorskip`); la cadena
  `chunker → índice` sí se probó con vectores falsos, y la mecánica del índice
  con LanceDB real. Kevin lo cierra con
  `pip install -e ".[embed]" && pytest -m slow -k "vectors or embed"`.
- **`numpy` entró al entorno** como dep transitiva de LanceDB. No lo pedía el
  plan; es inevitable con pyarrow/lancedb y no se usa directo en el código.
- **Paquete `index/` estrenado con solo `vectors`**; `lexical` (FTS5) es PR-14,
  `search/` es PR-15.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). `lancedb` **sí** instalado;
`sentence-transformers` **no**.

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 58 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 240 passed, 15 deselected (~75 s)
./.venv/Scripts/python.exe -m pytest -q tests/test_vectors.py
#   -> 12 passed, 1 deselected (LanceDB real, vectores de juguete + fixture)
```

`spectre index status` sobre una base tmp con 5 chunks (3 marcados con
`m-real`) y 3 vectores (2 `m-real`, 1 `m-viejo`):

```
índice vectorial               3 vectores, dimensión 4
  con modelo m-real            2
  con modelo m-viejo           1
chunks en SQLite               5
chunks sin embedding           5  (modelo <config, != m-real>)
chunks en el índice vectorial  3
```

Pendiente de correr (necesita `[embed]`): `pytest -m slow -k vectors`.

## Dudas que quedaron

- **El test `slow` de aceptación** re-extrae el Tomo 348 (~8 min) y además baja
  torch + el modelo (~470 MB). Es caro; se corre a mano.
- **`buscar` sin filtros.** D-6 pide filtrar por año / tribunal / tipo de
  sección — eso es PR-15 y probablemente convenga guardar esas columnas en la
  tabla LanceDB (o cruzar contra SQLite después del ANN). Hoy la tabla solo
  tiene `chunk_id, modelo, vector`.
- **`vaciar()` y reindexar** es todo-o-nada. Cambiar de modelo hoy implica
  `vaciar()` + reindexar el tomo entero. Un reindex incremental (solo los chunks
  que `chunks_pendientes_de_embedding` marca) también funciona con `upsert`,
  pero deja la tabla con dos modelos hasta terminar; `modelos()` lo hace
  visible.
- **`merge_insert` con lotes grandes**: no medí el rendimiento con miles de
  filas. PR-19 / PR-25 lo van a ver sobre la colección real.
- **Versión de LanceDB**: `>=0.13,<1.0` es amplio; probado con 0.38.0. El
  `list_tables()` que devuelve objeto en vez de lista ya obligó a un shim;
  puede haber más drift de API en ese rango.
