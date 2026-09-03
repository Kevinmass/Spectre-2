# Bitácora PR-08 — Metadatos del fallo

Fecha: 03/09/2026
Criterio de aceptación (plan §6): ≥90% de los 126 fallos del Tomo 348 con fecha
y jueces; los que fallan quedan marcados, no inventados.

**Medido sobre dos tomos** (348 y 349, para no sesgar con un solo archivo — Kevin
agregó el 349 a `data/tomos/`):

| tomo | fecha | jueces | fecha y jueces |
|---|---|---|---|
| 348 | 133/133 (100%) | **123/133 (92,5%)** | **123/133 (92,5%)** |
| 349 | 153/153 (100%) | **140/153 (91,5%)** | **140/153 (91,5%)** |

Los ~8% sin jueces son entradas del índice que reproducen **solo el sumario** con
la nota `(*) Sentencia del <fecha>. Ver fallo.`: el cuerpo del fallo, con las
firmas, no está en esas páginas. Quedan con `jueces=()` — marcados, no
inventados (D-05). Es el mismo fenómeno del gap 126→133 de PR-06/07.

## Qué hice

### `spectre/corpus/fallo/structure.py`

- **`MetadatosFallo(fecha, jueces, tipo_recurso, tribunal_origen, actor,
  demandado)`** — `fecha` ISO (`"2025-02-06"`), `jueces` es tupla, el resto
  `str | None`. `None` / `()` = no se encontró; nunca se inventa.
- **`texto_del_fallo(paginas_por_oficial, *, pagina_inicio,
  pagina_inicio_siguiente, pagina_fin_cuerpo)`** — arma el texto limpio del
  fallo: sus páginas de rango **más la página donde arranca el siguiente** (el
  pie de un fallo y la carátula del que sigue comparten página), cortando en esa
  carátula. El corte se busca sobre el **texto crudo** (después de `limpiar` las
  versalitas se normalizan y la carátula deja de reconocerse) y recién después
  se limpia lo que se conserva. La nota `(*) Sentencia del <fecha>` va al pie,
  *después* de la carátula del siguiente, pero es de este fallo: se rescata.
- **`extraer_metadatos(texto, *, caratula)`**:
  - **fecha**: la última `Buenos Aires, <día> de <mes> de <año>` (la de la Corte
    viene después del dictamen del Procurador). Si no hay, la de la nota
    `Sentencia del <día> de <mes> de <año>`. Meses en español, con `setiembre`.
  - **jueces**: (1) una línea con em dash `—` que arranca en mayúscula y no tiene
    dígitos —a veces partida en dos, terminada en punto—; se quitan las
    aclaraciones `(según su voto)` / `(en disidencia)` y se parte en `—`. (2) si
    no hubo, la firma de un solo juez (`Horacio Rosatti.`) tras una fórmula de
    cierre (`Notifíquese`, `Archívese`, `devuélvase`, ...). Cada nombre se
    normaliza a Capitalizado (el PDF los trae en versalita; el Tomo 349, con el
    apellido en minúscula). Un fragmento entre em dashes se descarta si arranca
    con una palabra funcional o contiene "prosa" (`sentencia`, `voto`, ...): así
    una frase con `—` no se confunde con firmas.
  - **tipo de recurso**: la línea `Recurso ... interpuesto/deducido por ...`
    (`recurso de queja`, `recurso extraordinario`, `recurso de hecho`, ...);
    si no, la primera mención en el texto; para las carátulas de competencia,
    `"competencia"`.
  - **tribunal de origen**: `Tribunal de origen: ...` (sigue en la línea de
    abajo hasta el punto).
  - **partes**: de la carátula, partida en `c/` (case-insensitive). Sin `c/`,
    una sola parte (`actor`), `demandado=None`.

`es_versalita` / `limpiar` vienen de `corpus/pdf/clean`; `_linea_es_caratula` de
`segmenter`. No toca la base.

### `spectre/corpus/fallo/segmenter.py`

- **`_linea_es_caratula` ahora es case-insensitive** en `c/` / `s/`. El Tomo 349
  imprime algunas carátulas con `C/` mayúscula (`Fundación Club de Derecho
  argentina C/ Banco Supervielle`); sin esto, `texto_del_fallo` no cortaba y se
  colaba el fallo siguiente. Sin efecto en la segmentación por índice (usa el
  índice, no esta función); sí mejora el fallback de PR-07.

### `spectre/corpus/pdf/clean.py`

- **`_es_versalita` → `es_versalita`** (pública), reexportada en
  `corpus/pdf/__init__.py`. Ya se hizo en PR-07; PR-08 la usa de nuevo. Sin
  cambio de comportamiento.

### `spectre/cli.py`

- **`spectre pdf meta <pdf> [--tomo N] [--muestra N]`** — segmenta, arma el texto
  de cada fallo, extrae los metadatos e imprime el % con fecha / jueces / fecha
  y jueces / tribunal de origen / tipo de recurso / demandado, más la lista de
  citas sin fecha o jueces. `--muestra N` imprime los N primeros con todo. No
  persiste: mide, como `stats` / `clean` / `index` / `segment`.

### Fixture: `tests/fixtures/tomo348_cuerpo_p31-40.pdf`

`pdf_page` 37–42 del Tomo 348 (oficiales 31–36): tres fallos cortos y completos
("Albarracín", "N.N. ... Denunciante", "Gobierno de la Ciudad de Buenos Aires")
con `FALLO DE LA CORTE`, fecha, firmas, `Tribunal de origen:` y `Recurso de
queja interpuesto por`. 96 KB.

### Tests

- **`tests/test_structure.py`** (18; 2 `slow` parametrizados):
  - `extraer_metadatos` sobre texto armado a mano: fecha de la Corte / última no
    la del dictamen / nota "Ver fallo" / variante `setiembre`; jueces en bloque
    partido / con aclaraciones pegadas (`(según su voto)—`) / apellido en
    minúscula (349) / firma de uno solo / sin firmas → `()` / una frase con `—`
    no es firma; tribunal de origen partido en dos líneas; tipo de recurso;
    partes con y sin `c/`.
  - `texto_del_fallo` sobre el fixture: arma el texto, corta en la carátula del
    fallo siguiente; metadatos de "Albarracín" completos (fecha 2025-02-06, los
    tres jueces, tribunal, `recurso de hecho`, actor y demandado).
  - **`test_aceptacion[348]` y `[349]`** (`slow`): fecha, jueces y fecha+jueces
    ≥ 90% sobre cada tomo completo.
- **`tests/test_cli.py`** (+3): `pdf meta` imprime los porcentajes y la línea
  "con fecha y jueces"; `--muestra` imprime un fallo con sus jueces; nombre sin
  número → `SystemExit` pidiendo `--tomo`.

### `data/tomos/349.pdf`

Kevin lo dejó como `LibroVol349-1.pdf`; lo renombré a `349.pdf` para seguir la
convención `<numero>.pdf`. Gitignored, igual que el 348.

### `CLAUDE.md` y plan

- "Estado del código" → PR-08; "Fixture de referencia" ahora menciona el 349 y la
  regla de correr las mediciones sobre los dos tomos.

## Qué decidí por mi cuenta

- **La carátula en versalita, no un delimitador de texto, marca el corte entre
  fallos** en `texto_del_fallo` — misma decisión que el fallback de PR-07, por la
  misma razón (D-2: los delimitadores sobre-parten). El corte se hace sobre el
  crudo porque `limpiar` borra las versalitas.
- **Rescatar la nota `(*) Sentencia del <fecha>`** aunque caiga después de la
  carátula del siguiente: es un pie de página, va al fondo, pero la fecha es del
  fallo que estoy armando. Sin esto, `fecha` bajaba a ~98% en vez de 100%.
- **jueces por forma de la línea, sin exigir una fórmula de cierre antes.** A
  veces la dispositiva termina en `"... a los fines que hubiere lugar."` sin
  `Notifíquese`. La línea de firmas (mayúscula inicial + `—` + sin dígitos) se
  reconoce sola. El camino "firma de uno solo" sí necesita el cierre, porque
  `Horacio Rosatti.` sin `—` es más ambiguo.
- **`—` (em dash) es específico de las firmas** en estos tomos: las carátulas y
  los incisos usan `–` (en dash) o `-` (guion). Eso hace segura la detección por
  forma.
- **Nombres a Capitalizado**, no MAYÚSCULAS ni tal cual. El Tomo 348 trae
  `HoRacio Rosatti`, el 349 `Horacio rosatti`; `Horacio Rosatti` es lo legible y
  comparable. Para la búsqueda da igual.
- **`tipo_recurso` y `tribunal_origen` best-effort, sin umbral.** El plan solo
  pide ≥90% de fecha y jueces. `tribunal_origen` da ~80% (las remisiones al
  dictamen no lo traen), `tipo_recurso` ~85–90%. Se miden y se muestran; no
  bloquean.
- **Sin ruta de persistencia**, como PR-04 a 07 y a pedido de Kevin: funciones
  con test + `spectre pdf meta`. Llenar `fallos.fecha` / `jueces` (json) /
  `tribunal_origen` / `tipo_recurso` lo hace PR-19 desde el pipeline.
- **Fixture de 6 páginas con 3 fallos cortos completos**, en vez del tomo entero,
  para el test de integración.

## En qué me desvié del plan

- **Encadené PR-08 tras PR-07 en la misma sesión.** A pedido de Kevin, que
  además pidió la metodología nueva (trabajar el PR, push, `gh pr create`,
  esperar), ya en `CLAUDE.md` desde PR-07. PR-07 está mergeado a `main`
  (PR #8), la rama `pr-08-metadatos` sale de `main` limpio.
- **Medición sobre dos tomos (348 y 349), no uno.** El plan ancla al 348; Kevin
  agregó el 349 justamente para chequear que las heurísticas no estén ajustadas
  a un solo archivo. Los dos criterios de aceptación se verifican sobre ambos.
- **`_es_caratula` case-insensitive** — cambia código de PR-07 (sin regresión;
  los tests de PR-07 siguen verdes).
- **`data/tomos/349.pdf` renombrado** desde `LibroVol349-1.pdf`.
- **`clean._es_versalita` → `es_versalita`** (ya venía de PR-07).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 38 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 161 passed, 6 deselected (~12 s)
./.venv/Scripts/python.exe -m pytest -q -m slow            # -> 6 passed (~5 min, usa 348.pdf y 349.pdf)
```

Medición de aceptación a mano:

```
./.venv/Scripts/python.exe -m spectre.cli pdf meta data/tomos/348.pdf
# fallos               133
# con fecha            133/133  (100.0%)
# con jueces           123/133  (92.5%)
# con fecha y jueces   123/133  (92.5%)

./.venv/Scripts/python.exe -m spectre.cli pdf meta data/tomos/349.pdf
# fallos               153
# con fecha            153/153  (100.0%)
# con jueces           140/153  (91.5%)
# con fecha y jueces   140/153  (91.5%)
```

## Dudas que quedaron

- **El ~8% sin jueces coincide con las entradas de sumario "Ver fallo"** — las
  mismas que inflan el conteo 126→133. PR-09 (secciones) o una pasada de
  reconciliación deberían decidir si esas entradas son un fallo aparte o una
  referencia al mismo. Si dejan de contarse como fallos, el % sube solo.
- **`tipo_recurso` es grueso.** No distingue `recurso de queja` de `recurso de
  hecho` (son lo mismo procesalmente) ni saca `per saltum` / `avocación` /
  `competencia originaria`. Alcanza para etiquetar; afinarlo es fuera de alcance.
- **`tribunal_origen` no aparece en las remisiones al dictamen** (~20%). Está en
  el fallo completo, que para esas entradas no está en las páginas indexadas.
- **`_capitalizar_nombre` puede pisar un `von` / `mc` / `di`** de un apellido
  compuesto raro. No vi ninguno en 348/349; entra como regresión.
- **Firma de panel provincial** (349:43: `beatriz estela aranguren`, etc.): se
  extraen como jueces, y está bien —son los firmantes de esa decisión— pero no
  son ministros de la Corte. Si aguas abajo hace falta distinguir "jueces de la
  CSJN" de "tribunal que dictó", habrá que cruzar contra una lista.
