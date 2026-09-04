# Bitácora PR-12 — Interfaz de embeddings + implementación local

Fecha: 03/09/2026
Criterio de aceptación (plan §6): **cambiar el modelo en la config y ver que el
sistema identifica los chunks a reindexar sin tocar los PDFs.**

## Resultado en una línea

`Repo.chunks_pendientes_de_embedding(modelo)` devuelve los chunks con
`modelo_embedding IS NULL` **o** distinto de `modelo`. Marcás 10 chunks como
embebidos con `modelo-viejo`, cambiás la config a otro modelo, y
`spectre embed status` reporta **10/10 pendientes** — sin abrir un solo PDF (D-8).
La interfaz `EmbeddingModel` y la implementación local (`sentence-transformers`,
384 dim, CPU) quedan detrás de `spectre/embed/`; el paquete es una dependencia
**opcional** (arrastra torch) y si falta, **revienta con un mensaje claro**
(D-05), no finge embeber.

## Qué hice

### `spectre/embed/` (paquete nuevo)

- **`base.EmbeddingModel`** — ABC con `nombre` (lo que se guarda en
  `chunks.modelo_embedding`), `dimension`, `embed(textos) -> list[list[float]]`
  (sin numpy en el contrato) y `embed_uno`.
- **`local_st.ModeloLocalST`** — envuelve un `SentenceTransformer`. Carga
  **perezosa**: el import de `sentence_transformers` y la descarga del modelo
  recién ocurren al pedir `dimension` o `embed`. Si el paquete no está →
  `ModuleNotFoundError` con `pip install -e ".[embed]"`. Los vectores salen
  **normalizados** (norma 1): el índice de PR-13 usa producto interno como
  coseno sin más cuentas.
- **`cargar_modelo(nombre=None)`** — el modelo que dice la config
  (`embedding_model`) o el que se pase. No carga nada todavía.

### `spectre/db/repo.py`

- **`Chunk`** dataclass (una fila de `chunks`).
- **`insert_chunks(fallo_id, filas)`** — lote; cada fila
  `(seccion_id, orden, texto, pagina_oficial)`. `modelo_embedding` /
  `embedding_at` arrancan en NULL. Lo usará PR-19 para volcar lo de PR-11.
- **`chunks_pendientes_de_embedding(modelo, *, limite=None)`** — la consulta del
  criterio de aceptación: `WHERE modelo_embedding IS NULL OR modelo_embedding
  <> ?`.
- **`marcar_chunks_embebidos(ids, modelo)`** — `UPDATE ... SET modelo_embedding,
  embedding_at = ahora`.
- **`contar_chunks`**, **`contar_chunks_pendientes(modelo)`**,
  **`list_chunks_de_fallo`**.

### `spectre/cli.py`

- **`spectre embed status`** — imprime el modelo de la config, y (si la base
  existe) cuántos chunks hay y cuántos están pendientes de embedding con ese
  modelo. Es la demo del criterio de aceptación.
- **`spectre embed probe "<texto>" [...] [--modelo M]`** — carga el modelo
  **real** y embebe los textos; imprime nombre, dimensión y la cabeza del
  vector. Si `sentence-transformers` no está, sale con el mensaje de D-05.

### `pyproject.toml`

- Extra opcional **`embed = ["sentence-transformers>=3.0"]`**. **CI no lo
  instala** (torch es pesado y no hace falta para parsear/segmentar). Para el
  modelo real: `pip install -e ".[embed]"`.

### Base de datos

- **Sin migración.** La tabla `chunks` (con `modelo_embedding TEXT`,
  `embedding_at TEXT`) y sus índices ya están en `0001_initial.sql`.

### Tests

- **`tests/test_embed.py`** (10; 1 `slow`):
  - la interfaz: `EmbeddingModel` es abstracta; una implementación mínima
    cumple; `embed_uno` delega.
  - `cargar_modelo()` toma la config; acepta un nombre explícito; no carga nada
    al construir.
  - **contrato D-05** (corre porque `sentence-transformers` no está en el venv):
    `ModeloLocalST(...).dimension` y `.embed(...)` revientan con
    `ModuleNotFoundError` que menciona `[embed]`; `.nombre` no necesita el
    paquete.
  - **`slow` + skipif**: con `sentence-transformers` instalado, carga el modelo
    de la config, verifica `dimension == 384`, determinismo, norma ~1, y que dos
    paráfrasis quedan más cerca que una frase no relacionada. Se saltea si el
    paquete falta o si no se puede bajar el modelo (offline).
- **`tests/test_db.py`** (+8): insertar y listar chunks; FK al fallo; pendientes
  = todos cuando nunca se embebieron; `marcar_chunks_embebidos` baja los
  pendientes y sella `embedding_at`; **`test_cambiar_de_modelo_vuelve_a_marcar_
  todo_pendiente`** (el criterio); `limite`; borrar el tomo arrastra los chunks.
- **`tests/test_cli.py`** (+4): `embed status` sin base y con chunks;
  `embed probe` sin `sentence-transformers` sale con `.[embed]` (skipif si el
  paquete está, para no bajar el modelo en el test); `embed` sin acción revienta.

### Docs

- `CLAUDE.md`: "Estado del código" → PR-12; `## Comandos` + `spectre embed`;
  nota de que `sentence-transformers` es el extra `[embed]` y CI no lo instala.
- `docs/plan-spectre.md`: casilla PR-12 (§6); §9 → "Próximo: PR-13".

## Qué decidí por mi cuenta

- **`sentence-transformers` como extra opcional, no dependencia dura.** Arrastra
  torch (~cientos de MB); no hace falta para nada de la Fase 1-2 y haría el
  `pip install` de CI pesado y lento para cero beneficio (los tests que cargan
  el modelo son `slow` y CI no los corre). El módulo hace lazy-import y falla
  ruidosamente si falta.
- **La ABC vive en `base.py`, no un `Protocol`.** El resto del código usa clases
  concretas; una ABC da un lugar para el helper `embed_uno` y un error claro si
  una implementación se olvida un método.
- **Vectores normalizados en `embed()`.** El modelo por defecto está entrenado
  para coseno; normalizar acá deja el índice de PR-13 más simple (producto
  interno = coseno). Si algún modelo futuro no quiere, se agrega un flag.
- **`list[list[float]]`, no numpy.** El contrato de `EmbeddingModel` no ata a
  nadie a numpy; `ModeloLocalST` convierte la salida de `encode`.
- **`insert_chunks` con `seccion_id` nullable.** Todavía no hay filas en
  `secciones` (PR-08/09 no persistieron). PR-19 va a poblar `secciones` y pasar
  el `seccion_id` real; hoy los tests usan `None`.
- **Sin migración de UNIQUE sobre la identidad del chunk.** El `0001` dice que
  el UNIQUE de dominio lo agrega "el PR dueño"; la identidad del chunk
  (`fallo_id, seccion_id, orden`) es más de PR-11/PR-19 que de PR-12, y con
  `seccion_id` nullable el UNIQUE de SQLite no serviría igual. Se difiere.
- **`spectre embed probe` aparte de `status`.** `status` es la demo del criterio
  (no necesita el modelo). `probe` es la prueba de que la implementación **es
  real** (carga y corre el modelo), y por eso falla ruidoso sin el extra.
- **El test `slow` del modelo real no se corrió en esta sesión**: el venv no
  tiene `sentence-transformers` (ni `numpy`). Está escrito para correr con
  `pip install -e ".[embed]" && pytest -m slow -k embed`; se saltea si el
  paquete falta o si no hay con qué bajar el modelo.

## En qué me desvié del plan

- **La implementación de `sentence-transformers` está escrita pero no
  ejecutada** en esta sesión (falta el extra en el venv). El contrato "sin el
  paquete, revienta claro" sí se probó (es lo que pasa hoy). Kevin puede cerrar
  la verificación con `pip install -e ".[embed]"` + `pytest -m slow -k embed` +
  `spectre embed probe "texto de prueba"`.
- **`chunks` se llena desde `insert_chunks` (repo), no desde un pipeline.** PR-12
  necesita filas para demostrar el criterio; el pipeline que las genera de
  verdad es PR-19. Los tests insertan directo por el repo.
- **`numpy` no está en el venv**, así que el módulo evita depender de él
  (`list[list[float]]`); numpy entra igual como dep transitiva de
  `sentence-transformers` cuando se instale el extra.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). `sentence-transformers` **no**
instalado.

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 54 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 227 passed, 14 deselected (~80 s)
```

Demo del criterio a mano (base tmp):

```
SPECTRE_DATA_DIR=/tmp/edata spectre db migrate
# ...insertar 1 tomo, 1 fallo, 10 chunks; marcar 6 como embebidos con "modelo-viejo"
SPECTRE_DATA_DIR=/tmp/edata spectre embed status
#   modelo (config)          sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
#   chunks                   10
#   pendientes de embedding  10/10   (con <modelo de la config, != "modelo-viejo">)
```

```
./.venv/Scripts/python.exe -m spectre.cli embed probe "hola"
#   sentence-transformers no está instalado. Es una dependencia opcional:
#   corré `pip install -e ".[embed]"` en el venv del repo.        (exit 1)
```

Pendiente de correr (necesita el extra): `pytest -m slow -k embed`.

## Dudas que quedaron

- **El test `slow` del modelo real** baja ~470 MB la primera vez. Está marcado
  `slow` y skipif; si molesta que cuelgue de la red, se puede fijar un modelo
  chiquito de juguete para CI. Por ahora se corre a mano.
- **`normalize_embeddings=True` fijo.** Si PR-13/15 necesitan los vectores
  crudos (p. ej. para otra métrica), hace falta un parámetro.
- **`ModeloLocalST` no cachea el modelo entre procesos.** Cada `spectre embed
  probe` recarga. El pipeline (PR-19) va a instanciar una vez y reusar.
- **Sin `batch_size` configurable** en `embed()`. sentence-transformers usa su
  default (32). PR-13/19, que embeben miles de chunks, quizá quieran ajustarlo.
- **`chunks.seccion_id` queda NULL** hasta que PR-19 persista `secciones`. La
  consulta de pendientes no lo usa, pero `list_chunks_de_fallo` ordena por él
  (NULLs primero); da igual mientras sean todos NULL.
- **Elegir modelo**: si torch resulta demasiado para el target (una notebook de
  abogada), `fastembed` (ONNX, sin torch) tiene `multilingual-e5-small` a 384
  dim. Cambiaría solo `local_st.py`. Fuera de alcance de PR-12.
