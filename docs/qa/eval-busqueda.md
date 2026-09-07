# Set de evaluación de la búsqueda (PR-A6)

20 consultas con el fallo que la búsqueda *debería* traer, en
`tests/fixtures/eval-busqueda.jsonl` (una por línea:
`{"consulta", "cita_esperada", "nota"}`). Sirve para dos cosas del plan v2:

- ver si un cambio de ranking (PR-A1 agrupar por fallo, y lo que venga)
  **empeoró** algo;
- ver si el **reranker de PR-C3** mejora algo — se corre esto antes y
  después y se comparan los números.

## Métricas

- **recall@10** — en cuántas de las 20 consultas el fallo esperado aparece
  entre los 10 resultados (ya agrupados por fallo, PR-A1).
- **MRR** (mean reciprocal rank) — promedio de `1 / rango` del fallo esperado
  (rango 1-based; 0 si no está en el top 10).

## Cómo se mide

`tests/test_eval_busqueda.py`:

- `test_fixture_tiene_20_casos_bien_formados` — corre siempre (el fixture es
  parte del repo).
- `test_recall_y_mrr_sobre_el_indice_real` — `slow` + `skipif`: corre cada
  consulta por `buscar_hibrido` + `agrupar_por_fallo` contra el **índice real
  local** (`data/spectre.db` + `data/vectors/`, no versionado) con el modelo
  real (`[embed]`), y exige `recall@10 ≥ 0,85` y `MRR ≥ 0,65` — un piso de
  regresión, un poco por debajo de la línea de base.

```
pytest -m slow tests/test_eval_busqueda.py
```

## Línea de base

Medido el **06/09/2026** sobre `data/spectre.db` con los **tomos 348 + 349**
(286 fallos, 2.199 chunks — la misma base del relevamiento §2), modelo
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
`k=60 / candidatos=60`, `limite=10` fallos.

| # | consulta | cita esperada | rango |
|---|----------|:-------------:|:-----:|
| 1 | Fallos: 337:315 | 348:189 | 1 |
| 2 | Zárate Pablo Federico | 348:380 | 1 |
| 3 | prescripción de la acción penal | 348:611 | 3 |
| 4 | despido injustificado | 348:834 | 1 |
| 5 | extradición de un ciudadano extranjero | 348:644 | 3 |
| 6 | medida cautelar contra el municipio | 348:95 | 1 |
| 7 | seguridad social jubilación | 348:31 | 4 |
| 8 | amparo contra el Estado Nacional | 348:895 | 2 |
| 9 | tenencia de estupefacientes para consumo personal | 348:113 | 1 |
| 10 | promoción a la corrupción de menores agravada | 348:611 | 1 |
| 11 | daño moral por publicaciones periodísticas | 348:821 | 1 |
| 12 | responsabilidad del Estado por su actividad lícita | 348:419 | 1 |
| 13 | verificación de créditos en el concurso preventivo | 348:917 | 1 |
| 14 | reajuste de haberes previsionales movilidad | 349:735 | — |
| 15 | impuesto a las ganancias determinación de oficio | 348:589 | 1 |
| 16 | derecho a la salud cobertura de medicamentos | 349:894 | 1 |
| 17 | lesiones culposas y duración razonable del proceso | 348:659 | — |
| 18 | acción de hábeas data | 349:407 | 2 |
| 19 | extradición artículo 54 de la ley | 349:318 | 1 |
| 20 | medida cautelar innovativa suspensión de un acto administrativo | 348:48 | 3 |

**recall@10 = 18 / 20 = 0,900**
**MRR = 0,7125**

### Las dos que fallan

- **14 — "reajuste de haberes previsionales movilidad" → 349:735** (Ayudarte
  c/ ANSES s/ reajuste de haberes). El top se lo llevan otros previsionales
  y un amparo colectivo (348:895). El fallo objetivo es el correcto por
  carátula; el ranking no lo sube. Candidato claro a mejorar con PR-C3.
- **17 — "lesiones culposas y duración razonable del proceso" → 348:659**
  (Jorge s/ lesiones culposas, art. 94). La consulta mezcla dos ejes
  (tipo penal + garantía) y el índice no los cruza bien. Con "plazo razonable
  del proceso penal" a secas, 348:659 aparecía en el puesto 2 — el problema
  es la formulación combinada, que es justo lo que un reranker semántico
  debería manejar.

## Cómo mantener esto

- Si un PR cambia el ranking, correr `pytest -m slow tests/test_eval_busqueda.py`
  antes y después y anotar el delta en su bitácora.
- Si el piso (`_RECALL_MINIMO` / `_MRR_MINIMO` en el test) hay que bajarlo,
  se anota por qué; no se baja en silencio.
- Si se agregan tomos al índice local, la línea de base de arriba queda
  vieja: re-medir y actualizar la tabla y la fecha.
- Las `cita_esperada` se eligieron por carátula / materia distintiva. Un par
  son opinables; lo que importa es que están **fijas**, para que el número
  sea comparable entre corridas.
