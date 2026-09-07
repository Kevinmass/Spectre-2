# Bitácora PR-A6 — Set de evaluación de búsqueda

## Qué pedía el plan

> **PR-A6 `[N]` Set de evaluación de búsqueda.** 20 consultas con el fallo
> esperado, versionadas en el repo, y un test que mide *recall@10* y *MRR*.
> Sin esto no se puede decir si el reranker de la Tanda C mejora algo, y
> tampoco si A1 rompió el ranking.
> *Entrega:* `docs/qa/eval-busqueda.md` con el número de partida.

## Qué se hizo

- **`tests/fixtures/eval-busqueda.jsonl`** (nuevo): 20 líneas
  `{"consulta", "cita_esperada", "nota"}`. Las 8 primeras son las de
  `docs/qa/consultas-PR-15.md` (ya validadas por
  `test_hybrid.py::test_aceptacion`); las 12 nuevas las elegí explorando la
  base real y quedándome con consultas cuyo fallo objetivo es claro por
  carátula o materia distintiva (Loyola/estupefacientes, Ilarraz/corrupción
  de menores, Campodónico/América TV, Egusquiza Mamani/extradición art. 54,
  etc.).
- **`tests/test_eval_busqueda.py`** (nuevo):
  - `test_fixture_tiene_20_casos_bien_formados` — corre siempre (el fixture
    es parte del repo): 20 casos, campos presentes, `cita` con `:`, sin
    consultas duplicadas.
  - `test_recall_y_mrr_sobre_el_indice_real` — `slow` + `skipif`: corre cada
    consulta por `buscar_hibrido` + `agrupar_por_fallo` (`k=60/candidatos=60`,
    `limite=10`) contra `data/spectre.db` + `data/vectors/` con el modelo
    real, calcula recall@10 y MRR, y exige `recall ≥ 0,85` y `MRR ≥ 0,65`
    (piso de regresión). El mensaje de fallo imprime el rango de cada
    consulta.
- **`docs/qa/eval-busqueda.md`** (nuevo): las 20 consultas con su rango
  medido, la línea de base, cómo se corre, las dos que fallan y cómo
  mantener el set.

**Línea de base (06/09/2026, tomos 348+349): recall@10 = 0,900 (18/20) ·
MRR = 0,7125.**

## Qué decidí por mi cuenta

- **La medición corre contra `data/spectre.db`, no reindexando en el test.**
  `test_hybrid.py::test_aceptacion` reindexa el tomo 348 desde el PDF (~2
  min). Para PR-A6 preferí evaluar el índice **que sirve la app de verdad**:
  es más honesto, es rápido (~18 s con carga de modelo), y el propósito del
  set —comparar antes/después de un cambio de ranking— se cumple corriendo la
  vara sobre la misma base. El costo: la línea de base de la `.md` queda
  vieja si se agregan tomos al índice local; está anotado como tarea de
  mantenimiento.
- **`skipif` en vez de reindexar** para no depender de artefactos no
  versionados en CI (mismo criterio que `slow`/`red`). El test rápido del
  fixture sí corre siempre.
- **Piso de regresión (`0,85` / `0,65`) por debajo de la base (`0,90` /
  `0,71`).** Deja margen para ruido menor sin dejar pasar una caída real. El
  test dice explícitamente que bajar el piso se anota, no se hace en
  silencio.
- **Dejé dos consultas que hoy fallan en el set** ("reajuste de haberes
  previsionales movilidad" → 349:735; "lesiones culposas y duración razonable
  del proceso" → 348:659) en vez de reformularlas hasta que acierten. Un set
  donde todo da rango 1 no tiene con qué mostrar una mejora; estas dos son
  consultas razonables con la cita correcta, y son justo el tipo de caso
  (materia previsional, consulta de dos ejes) que un reranker semántico
  debería levantar — PR-C3 tiene con qué compararse.
- **Formato JSONL, no una tabla en el `.md` parseada por el test.** El `.md`
  es para leer; el `.jsonl` es la fuente para el test. Menos frágil que
  parsear markdown.
- **No corrí el eval "antes de A1"** para tener el delta que el plan
  menciona ("ver si A1 rompió el ranking"): A1 ya está mergeado y el eval se
  crea ahora. Lo que queda es la base para adelante. `test_aceptacion` de
  PR-15 (que no agrupa) sigue verde, así que A1 no rompió el ranking de
  chunks.

## Qué verifiqué

- `pytest -m slow tests/test_eval_busqueda.py` → pasa: recall@10 = 0,900,
  MRR = 0,7125 (≥ pisos). ~18 s.
- `pytest tests/test_eval_busqueda.py` (sin `slow`) → pasa el test del
  fixture.
- Suite completa: `python -m pytest` → `395 passed, 3 skipped` (antes 394;
  +1 el test rápido del fixture). `24 deselected` (antes 23; +1 el `slow`).
- `ruff check .` / `ruff format --check .` limpios.
- Cada `cita_esperada` la confirmé corriendo la consulta y mirando la
  carátula del fallo que devuelve (script en scratch, no versionado). Las
  citas del tomo son la página de **inicio** de cada fallo.

## En qué me desvié del plan

- El plan dice "un test que mide recall@10 y MRR"; hay dos (uno siempre, uno
  `slow`). El resto es como se pidió.

## Dudas que quedaron abiertas

- **Algunas `cita_esperada` son opinables.** En un corpus de 286 fallos,
  para una consulta conceptual ("responsabilidad del Estado por actividad
  lícita") hay varios fallos defendibles como "el" resultado. Elegí uno y lo
  fijé; lo que importa para la métrica es que sea **estable** entre corridas,
  no que sea indiscutible. Está dicho en el `.md`.
- **La base local puede cambiar** (reindexar, sumar tomos) y desactualizar la
  línea de base. No hay forma de versionar `data/spectre.db` (es grande y
  gitignored). Mitigación: la `.md` dice la fecha y el contenido exacto de la
  base al medir, y el test tiene un piso, no una igualdad.
- **20 consultas es poco** para números finos. Alcanza para detectar un
  cambio grande de ranking; para diferencias de pocos puntos habría que
  crecer el set. El plan pide 20; queda así.
