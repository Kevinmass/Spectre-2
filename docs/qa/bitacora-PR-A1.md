# Bitácora PR-A1 — Agrupar los resultados por fallo

## Qué pedía el plan

> **PR-A1 `[N]` Agrupar los resultados por fallo.** Un resultado = un caso,
> con sus pasajes anidados y un contador ("3 pasajes más en este fallo").
> Toca `search/hybrid.py`, `/api/buscar` y el render. Conservar el mejor
> pasaje por tipo de sección, no solo el mejor absoluto: una mayoría y una
> disidencia del mismo fallo son cosas distintas.
> *Acepta:* las 8 consultas de referencia devuelven 10 fallos distintos cada
> una (hoy: entre 2 y 10, promedio 5,25).

## Qué se hizo

- **`spectre/search/agrupar.py`** (nuevo): `agrupar_por_fallo(conn,
  resultados, *, limite)`. Toma la lista de `ResultadoHibrido` que ya devuelve
  `buscar_hibrido` (chunks ranqueados por RRF, el mejor primero) y la colapsa
  a `list[FalloAgrupado]`:
  - Un `FalloAgrupado` por fallo, en el orden en que aparece su primer chunk
    (que, como la entrada viene de mejor a peor, es también su mejor chunk).
    `score` = el de ese primer chunk; marca la posición del fallo en la lista.
  - Dentro de cada fallo, **un `Pasaje` por tipo de sección** (`mayoria` /
    `voto` / `disidencia` / `dictamen` / `None` si el chunk no tiene
    sección), el de más puntaje. Dos votos del mismo tipo se colapsan a uno.
  - `total_pasajes` = cuántos chunks del fallo trajo la búsqueda antes de
    ese recorte. Es lo que alimenta el contador "N pasajes más en este
    fallo" de la UI (`total_pasajes - len(pasajes)`).
  - `limite` recorta la cantidad de **fallos**, no de pasajes.
- **`spectre/api/app.py`** (`GET /api/buscar`): en vez de serializar chunk
  por chunk, ahora llama `buscar_hibrido(..., k=candidatos)` (fusiona hasta
  `candidatos`, no `k`) y después `agrupar_por_fallo(conn, fusionados,
  limite=k)`. La respuesta cambia de forma: cada `resultado` tiene `cita`,
  `caratula`, `fecha`, `tribunal_origen`, `score`, `total_pasajes` y una
  lista `pasajes`, cada uno con `seccion_tipo`, `seccion_autor`,
  `pagina_oficial`, `extracto`, `score`. El recorte del extracto
  (`_extracto`, PR-21) se hace ahora por pasaje.
- **`spectre/web/app.js`**: `renderResultado` arma el encabezado a nivel
  fallo (cita + fecha), la carátula, y un bloque `renderPasaje` por cada
  pasaje (badge de sección + extracto resaltado). Si `total_pasajes >
  pasajes.length`, agrega "N pasajes más en este fallo". Al clickear la cita
  se abre el fallo en la página del PDF del **mejor** pasaje (saltar al
  pasaje exacto dentro del fallo es PR-B2).
- **`spectre/web/style.css`**: `.resultado-fecha`, `.pasajes`, `.pasaje`,
  `.pasajes-mas`, y `.pasaje .extracto { margin: 0 }` para que el `gap` del
  contenedor no se duplique.
- **`spectre/search/__init__.py`**: exporta `FalloAgrupado`, `Pasaje`,
  `agrupar_por_fallo`.

## Qué decidí por mi cuenta

- **No toqué `search/hybrid.py`.** El plan lo lista entre los archivos que
  "toca", pero la fusión RRF ya estaba bien y agrupar es un paso posterior y
  separable: un módulo nuevo (`agrupar.py`) en vez de meterle
  responsabilidad de presentación a `buscar_hibrido`. `hybrid.py` sigue
  devolviendo `ResultadoHibrido` planos; quien quiera la lista sin agrupar
  (los tests de aceptación de PR-15, un futuro reranker de PR-C3) la tiene
  igual.
- **`agrupar_por_fallo` consulta `db/repo.py` directo** (`get_chunk`,
  `get_fallo`, `get_seccion`), igual que `hybrid.py`. No rompe la regla de
  dependencias (`search/` no importa `corpus/`; la base pasa por `repo.py`).
  Antes ese trabajo lo hacía el loop de `/api/buscar`; ahora vive en
  `search/` y el endpoint sólo serializa.
- **El endpoint fusiona `k=candidatos` en vez de `k=k`.** Si se cortara la
  fusión en `k` chunks, `k` fallos distintos no entrarían nunca (una
  sentencia con varios pasajes se comería los lugares). Con `candidatos=50`
  (default) hay material de sobra para 10 fallos — medido, ver abajo.
- **"Un pasaje por tipo de sección", no "por sección".** El plan dice "por
  tipo de sección" y ese es el criterio que implementé: dos votos de jueces
  distintos se colapsan a uno (se conserva el de más puntaje y se ve su
  `seccion_autor`). Distinguir voto-de-Rosatti de voto-de-Rosenkrantz sería
  "por `seccion_id`" y multiplicaría los pasajes; el plan pide lo primero y
  el contador "N pasajes más" cubre lo que se colapsó.
- **El contador puede decir números grandes.** En la base real, "prescripción
  de la acción penal" trae 19 chunks del fallo 348:611 (todos mayoría) → se
  muestra 1 pasaje y "18 pasajes más en este fallo". Es honesto: ese caso es
  muy on-topic. No lo caposé.
- **Las "8 consultas de referencia" del plan no están versionadas una por
  una.** El §2.1 del plan v2 las menciona (y da "daño moral" como ejemplo)
  pero no las lista. Usé las 8 que sí están en el repo:
  `_CONSULTAS_SIN_FILTRO` de `tests/test_hybrid.py`, documentadas en
  `docs/qa/consultas-PR-15.md`. PR-A6 arma el set de evaluación formal (20
  consultas).

## Qué verifiqué

- **Criterio de aceptación, sobre la base real** (`data/spectre.db` +
  `data/vectors/`, 2 tomos, 286 fallos, 2.199 chunks — la misma del
  relevamiento §2), modelo real `paraphrase-multilingual-MiniLM-L12-v2`,
  las 8 consultas de `consultas-PR-15.md`:

  | consulta | fallos distintos antes (top-10 chunks) | después (`agrupar`, limite 10) |
  |---|---|---|
  | `Fallos: 337:315` | 6 | 10 |
  | `Zárate Pablo Federico` | 6 | 10 |
  | `prescripción de la acción penal` | 5 | 10 |
  | `despido injustificado` | 8 | 10 |
  | `extradición de un ciudadano extranjero` | 9 | 10 |
  | `medida cautelar contra el municipio` | 5 | 10 |
  | `seguridad social jubilación` | 6 | 10 |
  | `amparo contra el Estado Nacional` | 9 | 10 |
  | **promedio** | **6,75** (suma 54) | **10,00** (suma 80) |

  Con estas 8 consultas el "antes" da 6,75, no el 5,25 del plan (que se midió
  sobre otro set, no versionado, a través del endpoint HTTP en su momento).
  El "después" cumple: **10 fallos distintos en cada una**.
  Script de medición: `scratchpad/medir_a1.py` (no se versiona; PR-A6 hace
  el harness de evaluación de verdad).

- **Tests nuevos:**
  - `tests/test_agrupar.py` (8 casos): agrupa varios chunks de un fallo en un
    resultado; conserva el mejor pasaje por tipo de sección y descarta el
    segundo del mismo tipo; ordena los pasajes por puntaje aunque lleguen al
    revés; el orden de los fallos sigue al primer chunk de cada uno;
    `limite` recorta fallos, no pasajes; chunk sin sección → pasaje con
    `seccion_tipo=None`; chunk inexistente se saltea; lista vacía → lista
    vacía.
  - `tests/test_api.py::test_buscar_agrupa_los_pasajes_de_un_fallo_en_un_solo_resultado`:
    dos secciones del mismo fallo matchean → 1 resultado, `total_pasajes=3`,
    2 pasajes (`mayoria` + `disidencia`), la cita no se repite.
  - `tests/test_api.py::test_buscar_solo_lexico_encuentra_por_texto`:
    actualizado a la forma nueva (`resultado["pasajes"][0]["seccion_tipo"]`,
    etc.).

- **Suite completa:** `python -m pytest` → `387 passed, 3 skipped` (antes
  378; +8 en `test_agrupar`, +1 en `test_api`). `ruff check .` limpio,
  `ruff format --check .` limpio.
  `tests/test_hybrid.py::test_aceptacion` (`slow`) no se tocó — prueba
  `buscar_hibrido` directo, no la agrupación.

## En qué me desvié del plan

- `search/hybrid.py` no se modificó (ver "qué decidí por mi cuenta"). El
  resto de los archivos que el plan nombra (`/api/buscar`, el render) sí.
- El "hoy" del criterio de aceptación medido da 6,75, no 5,25 — distinto set
  de consultas. El número que importa (10/10 después) se cumple.

## Dudas que quedaron abiertas

- **La forma de la respuesta de `/api/buscar` cambió** (los campos de
  sección y el extracto se movieron adentro de `pasajes[]`). No hay otros
  consumidores además de `spectre/web/app.js`, que se actualizó en el mismo
  PR; si aparece uno externo, es un breaking change.
- **`candidatos=50` es lo que garantiza 10 fallos distintos.** Si una
  consulta muy específica trajera menos de 10 fallos entre sus 50
  candidatos, el resultado tendría menos de 10 — y estaría bien (no hay que
  inventar fallos). Ninguna de las 8 de referencia cae en ese caso.
- El enlace de la cita abre el PDF en la página del mejor pasaje. Llegar al
  pasaje exacto dentro de la vista de fallo es PR-B2; por ahora es "cerca".
