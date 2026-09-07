# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Spectre

Motor de búsqueda semántica sobre jurisprudencia argentina (colección Fallos de
la CSJN). Monousuario, local, Python 3.11 + FastAPI, interfaz servida en
localhost.

## Antes de tocar nada

**Leé `docs/plan-v2.md`. Es la fuente de verdad y el estado del desarrollo.**
Contiene las decisiones nuevas (D-13 a D-16), el relevamiento del MVP con los
seis problemas medidos, y las tandas A/B/C/D con su criterio de aceptación.

El plan del MVP está cerrado (27/27) y archivado en
`docs/planes_archivados/plan-spectre.md`. Sus decisiones D-1 a D-12 siguen
vigentes salvo que el plan v2 diga lo contrario.

## Estado del código (al cerrar PR-A6 — MVP 27/27 + Tanda A cerrada)

Existe y anda: `spectre/config.py`, `spectre/cli.py`, `spectre/db/` (repo +
migraciones; `spectre/jobs/runner.py` (cola durable) + `spectre/jobs/pipeline.py`
(PR-19: el pipeline completo — descargar → extraer → limpiar → segmentar →
estructurar → fragmentar → embeber → indexar — como una cadena de jobs, uno
por etapa por tomo; `tomos.estado` es el progreso consultable, con su
vocabulario fijado por el CHECK de `0004_tomos_estado_check.sql`),
`spectre/corpus/pdf/` (`extract` + `clean` + `quality`: clasifica un tomo en
`digital` / `requiere_ocr` según caracteres por página), `spectre/corpus/fallo/`
(`index_parser` + `segmenter` + `structure` + `sections` + `citations`),
`spectre/corpus/csjn/` (`catalog`: lista los tomos del sitio oficial — número,
volumen, año, id CSJN — sin persistir; `download`: baja el PDF de un tomo con
reintentos y caché por archivo, sin resume por Range —el servidor lo ignora—,
así que "reanudar" es a nivel de archivo completo), `spectre/chunking/`
(`chunker`: ventanas de ~400 palabras por sección), `spectre/embed/`
(`base.EmbeddingModel` + `local_st.ModeloLocalST`, sentence-transformers
detrás del extra opcional `[embed]`), `spectre/index/`
(`vectors.IndiceVectorial`, LanceDB embebido en `data/vectors/`;
`lexical.IndiceLexico`, FTS5 sobre `chunks_fts` dentro de la propia base
SQLite, sincronizada sola por triggers), `spectre/search/`
(`hybrid.buscar_hibrido`, fusión RRF de los dos índices con filtros de rango
de años / tribunal / tipo de sección; `agrupar.agrupar_por_fallo` (PR-A1)
colapsa los chunks a fallos con pasajes anidados;
`palabras_vacias.PALABRAS_VACIAS` (PR-A4), la lista de función-palabras del
castellano —gemela de la de `spectre/web/app.js`—), `spectre/api/`
(`app.crear_app`: FastAPI que
sirve `spectre/web/` estático y expone `GET /api/estado` — tomos + total de
chunks —, `GET /api/buscar` — PR-21: envuelve `buscar_hibrido`, cachea el
modelo de embeddings por instancia de app y degrada sola a léxico puro si
`sentence-transformers` no está, diciéndolo en `modo` — nunca fingiendo
`hibrido` —; PR-A1: la respuesta va **agrupada por fallo** (`search/agrupar.py`,
módulo aparte de `hybrid.py`): cada resultado es un fallo con sus `pasajes`
anidados (uno por tipo de sección, el de más puntaje) y `total_pasajes` para
el contador "N pasajes más" —, `GET /api/fallos/{cita}` — PR-22: el fallo completo por
secciones + metadatos + citas salientes, recalculadas al vuelo con
`extraer_citas` (PR-10) sobre el texto ya persistido porque el pipeline
(PR-19) decidió a propósito no guardarlas en la tabla `citas` (es la materia
prima de un grafo de precedentes fuera del MVP, §8.3) — y `GET
/api/tomos/{numero}/pdf` — sirve el PDF del tomo desde disco, para el enlace
"ver en el PDF" con `#page=N` calculado con `pagina_oficial +
tomos.offset_pagina` —, y dos rutas que escriben (PR-23): `POST
/api/tomos/{numero}/indexar` (registra o retoma un tomo por `csjn_tomo_id`,
D-9) y `POST /api/tomos/{numero}/subir` (sube un PDF a mano a `data/tomos/`,
D-9) — las dos arrancan `jobs.correr_pipeline` con `BackgroundTasks` de
Starlette (el hilo del pool que ya trae el framework, no un worker casero) y
devuelven 202 al toque; `GET /api/estado` agrega por tomo `etapas_hechas`/
`etapas_total` (de `jobs.progreso`) y el `error` de la última etapa fallida
si la hay — ninguna de las dos rutas de escritura reintenta sola una etapa
ya fallida, mismo comportamiento que `spectre ingest` desde PR-19).
`spectre/web/` (HTML/CSS/JS planos sin build: layout con dos tabs, Buscar y
Biblioteca, más una vista de fallo sin tab propio —se llega clickeando un
resultado, o escribiendo una cita (`348:34`, `Fallos: 348:34`, `Fallos
348:34`) en el buscador: PR-A5 salta directo al fallo, y si no existe muestra
un mensaje con la opción de buscarla como texto—; Buscar ya busca de verdad
—campo de consulta, resultados agrupados por fallo con sus pasajes anidados
(PR-A1), cita `Fallos: N:N`,
extracto que arranca en borde de palabra y, si hay una cerca, en el
principio de la oración que contiene el término (PR-A4), con el término
resaltado en `<mark>` —PR-A3: sin palabras vacías del castellano y con
límites de palabra Unicode, "sin" ya no marca "sino"—, etiqueta de sección
mayoría/voto/disidencia/dictamen, y una fila de filtros (PR-A2): tribunal,
sección, rango de años y "solo texto", que se aplican sobre la búsqueda a la
vista—, la vista de fallo muestra el
texto completo por sección, metadatos, citas salientes y el enlace al PDF en
la página exacta del fragmento que trajo el resultado, y Biblioteca (PR-23)
lista los tomos con su progreso (sondeado cada 2s mientras la pestaña está a
la vista) y tiene los dos formularios —indexar por `csjn_tomo_id` o subir un
PDF— para lanzar una indexación desde la UI). `spectre serve` levanta ese
servidor y abre el navegador. `scripts/arrancar.ps1` (Windows) /
`scripts/arrancar.sh` (macOS/Linux) — PR-24: crean el venv, instalan
`.[embed]`, y llaman a `scripts/arrancar.py`, que baja el modelo real,
intenta indexar un tomo de muestra desde la CSJN (best-effort — si el sitio
no responde, sigue igual, no aborta) y levanta `spectre serve`.
`scripts/medir_ingesta.py` (PR-25) mide tiempos reales de `spectre ingest`
por etapa, memoria pico y tamaño de índice corriendo un subproceso real por
tomo contra un `data_dir` temporal (el subproceso se mide a sí mismo antes
de salir — sondear la memoria de un proceso ajeno desde el padre no fue
confiable en esta máquina); números y su extrapolación honesta a la
colección completa en `docs/qa/mediciones.md`. `README.md` (PR-26) es la
instalación real (los scripts de PR-24) y `docs/guia-uso.md` (PR-26) es la
guía de uso sin jerga de programador, escrita para quien solo quiere buscar
fallos, no tocar el código. Con esto el plan (`docs/plan-spectre.md`, §6/§9)
quedó completo (27/27). El desarrollo sigue en `docs/plan-v2.md`, definido
tras relevar el MVP real: seis problemas medidos (§2) y las tandas A/B/C/D
con su criterio de aceptación (§4-§7), más la Tanda E (multi-tribunal, D-17).
**Tanda A cerrada** (PR-A0 a PR-A6): observación con la primera usuaria,
resultados agrupados por fallo, filtros en la UI (año por rango), resaltado y
extractos limpios, búsqueda por cita, y un set de evaluación
(`docs/qa/eval-busqueda.md`, línea de base recall@10 0,90 · MRR 0,71) para
medir cambios de ranking.
Deuda conocida que arrastra el MVP: la tabla `citas` tiene 0 filas (el
endpoint las extrae al vuelo, PR-10 nunca las persistió — la termina PR-C1) y
la ingesta pica 5,3 GB de memoria (PR-C4).

## Reglas de trabajo

- **Metodología con Claude Code (a partir de PR-07):** se trabaja el PR
  indicado y solo ese. Al terminarlo —bitácora escrita, casilla marcada, commit
  hecho— se hace `git push` de la rama y se abre el PR con `gh pr create`
  (base `main`). Después **se para y se espera nueva instrucción**: no se
  arranca el PR siguiente por cuenta propia.
- Cada PR cierra escribiendo `docs/qa/bitacora-<ID>.md` (ej.
  `bitacora-PR-A1.md`): qué hizo, qué decidió por su cuenta, en qué se desvió
  del plan, qué verificó y con qué comandos exactos, qué dudas quedaron. Tiene
  que poder leerse sin el diff al lado.
- Marcá la casilla del PR en `docs/plan-v2.md`, en el mismo commit que lo
  cierra. (Los PRs del MVP están en `docs/planes_archivados/plan-spectre.md`,
  ya todos marcados.)
- Los criterios de aceptación son números medidos sobre el fixture, no "parece
  que anda". Verificá contra el número del plan; si no da, se anota la diferencia
  medida en la bitácora y no se fuerza.

## Reglas del código

- **Ningún stub que reporte éxito.** Si algo no está implementado, falla
  ruidosamente. El proyecto anterior murió por simular procesamiento
  (`time.sleep(2)` + `chunks_count=10` inventado) y marcar documentos como
  indexados.
- Las rutas se resuelven contra la raíz del paquete, nunca contra el CWD. La
  config tiene que cargar igual desde cualquier directorio (bug D-02).
- Todo el acceso a datos pasa por `spectre/db/repo.py`. El estado va en SQLite,
  no en JSON escrito a mano (bug D-04).
- Migraciones: `spectre/db/migrations/NNNN_nombre.sql`, aplicadas en orden y
  anotadas en la tabla `_migraciones`. El plan nombra `db/schema.sql`; se
  realizó como `0001_initial.sql` para no tener dos fuentes del esquema. Una
  restricción de dominio nueva es una migración nueva; SQLite no tiene
  `ALTER TABLE ADD CONSTRAINT`, así que se reconstruye la tabla (ver `0002`).
- Job runner: el handler recibe `(conn, job)`, escribe solo por esa conexión y
  **no** llama `commit()` / `rollback()`. El `Runner` es dueño del límite
  transaccional; un handler que commitea rompe la garantía "sin duplicar" (D-3).
  Por eso los handlers de `jobs/pipeline.py` usan `Repo(conn,
  auto_commit=False)` (PR-19): con eso, cada escritura queda pendiente hasta
  que el `Runner` cierra la transacción del job entero. `Repo(conn)` a secas
  (sin el argumento) sigue commiteando por su cuenta, para el CLI y los tests.
- **Regla de dependencias:** `corpus/` no importa `index/` ni `embed/`.
  `search/` no importa `corpus/`. `chunking/` consume `corpus/fallo` (secciones
  + texto por página) pero no importa `embed/` ni `index/`. `index/` recibe
  vectores / texto ya listos y no importa `corpus/`. Todo cruce con la base
  pasa por `db/repo.py`.
- El modelo de embeddings va detrás de `embed/base.py` y **se registra por
  chunk** (`chunks.modelo_embedding`), para saber qué reindexar si cambia.
- El parseo y el embedding están separados: texto limpio y chunks viven en
  SQLite, reindexar no vuelve a abrir un PDF.
- Sin control de recursos casero, sin threads, sin Docker. Un proceso, lotes
  acotados, cola durable en SQLite reanudable.

## Comandos

Todo corre en el venv del repo. En esta máquina (Windows) no hay Python 3.11
instalado: el `.venv` es 3.13 y **CI valida contra 3.11** (`.github/workflows/ci.yml`).
Rutas del venv: `./.venv/Scripts/python.exe`, `./.venv/Scripts/ruff.exe`.

`lancedb` (PR-13, índice vectorial) es dependencia **dura**: `pip install -e
".[dev]"` la trae (arrastra pyarrow + numpy, no torch) y CI la ejercita.
`sentence-transformers` (PR-12, embeddings reales) es el extra **opcional**
`[embed]` — arrastra torch, CI **no** lo instala. Instalado en el `.venv` de
esta máquina desde PR-15 (`pip install -e ".[embed]"`, sentence-transformers
6.0.1 / torch 2.14.0): los `slow` que necesitan el modelo real corren acá sin
paso previo. Si el `.venv` se rehace desde cero, hay que reinstalar el extra.

- `python -m pytest` — corre la suite (rápida; excluye `-m slow` y `-m red`).
  Un solo test: `python -m pytest tests/test_db.py::nombre`. La marca `slow`
  es la medición de aceptación sobre el Tomo 348 completo (~2 min, necesita
  `data/tomos/348.pdf`): `python -m pytest -m slow`. La marca `red` (PR-16)
  pega contra un sitio real por HTTP (el catálogo de la CSJN); CI no depende
  de que ese sitio esté arriba: `python -m pytest -m red`.
- `ruff check .` — lint. `ruff format --check .` — formato (el gate de CI corre
  `ruff check`; el formato se verifica a mano antes de commitear).
- `python -m spectre.cli <sub>` o `spectre <sub>` (entry point instalado):
  - `spectre config` — imprime las rutas resueltas (verificación a ojo de D-02).
  - `spectre db migrate` — crea `data/spectre.db` y aplica las migraciones
    pendientes de `spectre/db/migrations/`. `spectre db status` — qué se aplicó.
  - `spectre csjn catalog [--muestra N]` — lista los tomos del sitio oficial de
    la CSJN (número, volumen, año, id CSJN); mide, no persiste (`spectre
    ingest` es quien persiste, vía `--csjn-tomo-id`). Necesita red real.
  - `spectre csjn download <tomo_id> <destino> [--forzar]` — baja el PDF de
    un tomo (el `tomo_id` lo da `csjn catalog`) con reintentos y caché: si
    `destino` ya existe no pide nada, salvo `--forzar`. Necesita red real.
  - `spectre pdf stats <pdf>` — extrae el texto de un tomo y mide cobertura del
    número de página oficial y el offset (criterio de aceptación de PR-04).
  - `spectre pdf clean <pdf> [--muestra N]` — limpia el texto del cuerpo
    (encabezados, des-hifenado, versalitas) y mide la reducción de palabras.
  - `spectre pdf quality <pdf>` — mide caracteres por página y clasifica el
    tomo en `digital` / `requiere_ocr` (D-10; PR-18).
  - `spectre pdf index <pdf> [--muestra N]` — parsea el índice por nombres de
    las partes y cuenta carátulas → página (PR-06).
  - `spectre pdf segment <pdf> [--tomo N] [--muestra N]` — arma los fallos del
    tomo (rango de página + cita `348:145`) desde el índice (PR-07).
  - `spectre pdf meta <pdf> [--tomo N] [--muestra N]` — fecha, jueces, tipo de
    recurso, tribunal de origen y partes de cada fallo (PR-08).
  - `spectre pdf sections <pdf> [--tomo N] [--cita 348:113]` — parte cada fallo
    en dictamen / mayoría / votos / disidencias (PR-09).
  - `spectre pdf citations <pdf> [--tomo N] [--cita 348:189]` — extrae las citas
    `Fallos: N:N` a precedentes; mide referencias y relación fallo→fallo (PR-10).
  - `spectre pdf chunks <pdf> [--tomo N] [--cita 348:34] [--objetivo N]
    [--solape N]` — fragmenta cada sección en ventanas de ~400 palabras con 80
    de solape; verifica que ningún chunk cruza el borde de sección (PR-11).
  - Todos los `spectre pdf …` **miden, no persisten**: son las mismas
    funciones que corre `spectre ingest`, pero sin tocar la base (útiles para
    ver un número de un tomo suelto sin registrar nada). Persistir en SQLite
    es `spectre ingest` (PR-19), no estos.
  - `spectre embed status` — modelo de la config y cuántos chunks de la base
    están pendientes de (re)embedding con ese modelo (criterio de PR-12).
    `spectre embed probe "<texto>" [--modelo M]` — carga el modelo real y embebe
    (necesita el extra `[embed]`; sin él, revienta claro).
  - `spectre index status` — vectores en el índice LanceDB (`data/vectors/`),
    por modelo, cuántos chunks de SQLite faltan indexar (PR-13) y cuántos hay
    en el índice léxico FTS5 (PR-14). `spectre index buscar "<consulta>"
    [--k N]` — corre la consulta contra `chunks_fts` solo (léxico puro).
  - `spectre search buscar "<consulta>" [--k N] [--candidatos N]
    [--anio-desde AAAA] [--anio-hasta AAAA] [--tribunal T]
    [--seccion mayoria|voto|disidencia|dictamen] [--solo-lexico]` — fusiona
    léxico + vectorial por RRF (PR-15); embebe la consulta con el modelo real
    salvo que se pase `--solo-lexico` (no necesita `[embed]` en ese caso). El
    año es un rango inclusivo (PR-A2); se pueden pasar los dos límites o uno
    solo.
  - `spectre ingest <numero> [--pdf RUTA] [--csjn-tomo-id ID]` — corre el
    pipeline completo sobre un tomo (descargar → extraer → limpiar →
    segmentar → estructurar → fragmentar → embeber → indexar) y persiste todo
    en SQLite + LanceDB (PR-19). `--pdf` para subida manual (D-9, salta la
    descarga); `--csjn-tomo-id` para bajarlo de la CSJN (lo da `csjn
    catalog`). Reanudable: correrlo de nuevo retoma desde `tomos.estado` sin
    reprocesar lo que ya esté hecho, y si una etapa falla se frena ahí y lo
    dice (no reintenta esa etapa solo — hay que arreglar y volver a correr).
    Un tomo que mide `requiere_ocr` (PR-18) se frena después de `extraer`
    (D-10): la "cola visible" son los tomos con `estado='extraido'` y
    `calidad='requiere_ocr'`.
  - `spectre serve [--host H] [--port N] [--no-browser]` — migra la base si hace
    falta, levanta el servidor FastAPI (`spectre/api/`) que sirve
    `spectre/web/` en `http://127.0.0.1:8000/` por defecto y abre el
    navegador (PR-20). La pestaña Buscar ya busca de verdad (PR-21):
    `GET /api/buscar` fusiona léxico + vectorial, con cita, extracto
    resaltado y etiqueta de sección; PR-A1 agrupa los resultados por fallo,
    PR-A2 agrega la fila de filtros (tribunal, sección, rango de años, "solo
    texto"), PR-A3/A4 limpian el resaltado y los bordes del extracto, y PR-A5
    hace que escribir una cita en el buscador salte directo al fallo. Clickear
    un resultado abre la vista de fallo (PR-22): texto completo por sección,
    metadatos, citas salientes y el enlace al PDF original en la página exacta
    del fragmento. La pestaña
    Biblioteca (PR-23) lista los tomos con su progreso y tiene los dos
    formularios para lanzar una indexación desde la UI: por `csjn_tomo_id`
    (D-9) o subiendo un PDF a mano — las dos corren el pipeline completo en
    segundo plano (no bloquean el servidor) y el progreso se ve solo, sin
    recargar la página.
- `scripts/arrancar.ps1` (Windows) / `scripts/arrancar.sh` (macOS/Linux) —
  PR-24, el arranque de un comando (necesita Python 3.11+ ya instalado, eso
  no lo instala el script): crean `.venv`, `pip install -e ".[embed]"`, y
  llaman a `scripts/arrancar.py` (testeado en `tests/test_arrancar.py`), que
  baja el modelo real, intenta indexar un tomo de muestra desde la CSJN
  (best-effort: si el sitio no responde, no aborta — Spectre igual levanta
  vacío) y corre `spectre serve`. La lógica que necesita `spectre` ya
  importable vive en Python (testeable); los `.ps1`/`.sh` solo hacen lo de
  antes de eso.
- `python scripts/medir_ingesta.py [pdf:numero ...]` — PR-25, medición
  end-to-end: corre `spectre ingest` de verdad, un subproceso por tomo
  (`--pdf`, sin depender de la CSJN), contra un `data_dir` temporal, uno de
  los tomos atrás del otro. Mide tiempo por etapa (de
  `jobs.iniciado_at`/`terminado_at`), memoria pico (el subproceso se mide a
  sí mismo justo antes de salir) y tamaño de índice final (`spectre.db` +
  `data/vectors/`). Sin argumentos usa `data/tomos/348.pdf` y `349.pdf`.
  Números y la extrapolación honesta a los 349 tomos del catálogo (con sus
  límites explícitos, D-10/R-1) están en `docs/qa/mediciones.md`, no en el
  código.

## Tests

- Planos en `tests/`: un archivo por módulo (`test_extract.py`, `test_clean.py`,
  ...), no espejan el árbol del paquete. No hay `conftest.py`; cada archivo
  arma sus fixtures.
- Los fixtures de texto real son recortes de pocas páginas del Tomo 348 en
  `tests/fixtures/`, regenerables con `pypdf` (receta en
  `tests/fixtures/README.md`). El tomo completo (`data/tomos/348.pdf`) no se
  versiona.
- Las mediciones de aceptación sobre el tomo entero son tests `slow` + `skipif`
  que necesitan `data/tomos/348.pdf`. El `pytest` de todos los días las saltea
  (`addopts = -m 'not slow and not red'`); corrélas con `pytest -m slow`
  (tardan minutos y CI no las ve). El set de evaluación de la búsqueda (PR-A6,
  `tests/test_eval_busqueda.py` + `tests/fixtures/eval-busqueda.jsonl`) es
  `slow` y corre contra el índice real local (`data/spectre.db`); mide
  recall@10 / MRR con un piso de regresión. Línea de base y método en
  `docs/qa/eval-busqueda.md`.
- `red` (PR-16): tests que pegan contra un sitio real por HTTP (el catálogo de
  la CSJN, `spectre/corpus/csjn/catalog.py`). Rápidos (segundos), pero CI no
  depende de que el sitio externo esté arriba, así que quedan afuera del
  default igual que `slow`: `pytest -m red`.
- `tests/verificar_*.mjs`: las verificaciones que no son Python. Cargan
  `spectre/web/app.js` con un DOM de mentira (`vm`) y chequean funciones
  puras: `verificar_resaltado.mjs` (PR-A3, `terminosDe` / `resaltarEn`),
  `verificar_cita.mjs` (PR-A5, `citaDe` + el mensaje de cita inexistente).
  No las mira `pytest` ni CI; se corren a mano: `node tests/verificar_cita.mjs`.

## Git

- Rama por PR: `pr-<id>-slug` (ej. `pr-a1-agrupar-fallo`), sacada de `main`
  actualizado. PR contra `main`. El remoto es `origin` → `Kevinmass/Spectre-2`.
- El commit que cierra el PR marca la casilla en `docs/plan-v2.md` y agrega
  `docs/qa/bitacora-<ID>.md`.

## Fixture de referencia

`data/tomos/348.pdf` (Fallos, Tomo 348, 968 páginas, ~126 fallos). Los criterios
de aceptación de las Fases 1 a 3 son números medidos sobre ese tomo: offset de
página 6, 126 entradas en el índice, fallo más largo 57 páginas, mediana 4
páginas, ~1.041 chunks, 887 citas. Un resultado lejos de esos números indica que
algo aguas arriba se rompió.

Desde PR-08 hay también `data/tomos/349.pdf` (Tomo 349, el más reciente). Cuando
un PR mida algo sobre tomo real, correrlo sobre **los dos** para no sesgar con un
solo archivo; los números del plan siguen anclados al 348. Ninguno de los dos se
versiona (gitignored).

## Lo que hay en `legacy/`

El intento anterior (`document-semantic-search/`, 3.022 LOC). PR-00 lo mueve a
`legacy/`. Es referencia histórica: no se importa ni se reutiliza código.
