# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Spectre

Motor de búsqueda semántica sobre jurisprudencia argentina (colección Fallos de
la CSJN). Monousuario, local, Python 3.11 + FastAPI, interfaz servida en
localhost.

## Antes de tocar nada

**Leé `docs/plan-spectre.md`. Es la fuente de verdad y el estado del
desarrollo.** Contiene las decisiones congeladas (D-1 a D-12), la lista de
defectos del proyecto anterior que no hay que repetir (D-01 a D-08), la
arquitectura de paquetes (§4), el modelo de datos SQLite (§5), los 27 PRs con su
criterio de aceptación (§6) y los riesgos abiertos (§7). La sección §9 dice cuál
es el próximo PR.

## Estado del código (al cerrar PR-11)

Existe y anda: `spectre/config.py`, `spectre/cli.py`, `spectre/db/` (repo +
migraciones), `spectre/jobs/runner.py`, `spectre/corpus/pdf/` (`extract` +
`clean`), `spectre/corpus/fallo/` (`index_parser` + `segmenter` + `structure` +
`sections` + `citations`), `spectre/chunking/` (`chunker`: ventanas de ~400
palabras por sección). El resto del árbol de la §4 del plan (`embed/`, `index/`,
`search/`, `api/`, `web/`) es objetivo: todavía no hay código. La §9 del plan
dice cuál es el próximo PR.

## Reglas de trabajo

- **Metodología con Claude Code (a partir de PR-07):** se trabaja el PR
  indicado y solo ese. Al terminarlo —bitácora escrita, casilla marcada, commit
  hecho— se hace `git push` de la rama y se abre el PR con `gh pr create`
  (base `main`). Después **se para y se espera nueva instrucción**: no se
  arranca el PR siguiente por cuenta propia.
- Cada PR cierra escribiendo `docs/qa/bitacora-PR-NN.md`: qué hizo, qué decidió
  por su cuenta, en qué se desvió del plan, qué verificó y con qué comandos
  exactos, qué dudas quedaron. Tiene que poder leerse sin el diff al lado.
- Marcá la casilla del PR en `docs/plan-spectre.md` (§6 y §9), en el mismo commit
  que lo cierra.
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
- **Regla de dependencias:** `corpus/` no importa `index/` ni `embed/`.
  `search/` no importa `corpus/`. `chunking/` consume `corpus/fallo` (secciones
  + texto por página) pero no importa `embed/` ni `index/`. Todo cruce con la
  base pasa por `db/repo.py`.
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

- `python -m pytest` — corre la suite (rápida; excluye `-m slow`). Un solo test:
  `python -m pytest tests/test_db.py::nombre`. La marca `slow` es la medición de
  aceptación sobre el Tomo 348 completo (~2 min, necesita `data/tomos/348.pdf`):
  `python -m pytest -m slow`.
- `ruff check .` — lint. `ruff format --check .` — formato (el gate de CI corre
  `ruff check`; el formato se verifica a mano antes de commitear).
- `python -m spectre.cli <sub>` o `spectre <sub>` (entry point instalado):
  - `spectre config` — imprime las rutas resueltas (verificación a ojo de D-02).
  - `spectre db migrate` — crea `data/spectre.db` y aplica las migraciones
    pendientes de `spectre/db/migrations/`. `spectre db status` — qué se aplicó.
  - `spectre pdf stats <pdf>` — extrae el texto de un tomo y mide cobertura del
    número de página oficial y el offset (criterio de aceptación de PR-04).
  - `spectre pdf clean <pdf> [--muestra N]` — limpia el texto del cuerpo
    (encabezados, des-hifenado, versalitas) y mide la reducción de palabras.
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
  - Todos los `spectre pdf …` **miden, no persisten** (llenar SQLite es PR-19).
  - `spectre ingest` / `serve` — declarados pero revientan (los implementan
    PR-19 / PR-20). Ningún stub que reporte éxito.

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
  (`addopts = -m 'not slow'`); corrélas con `pytest -m slow` (tardan minutos y
  CI no las ve).

## Git

- Rama por PR: `pr-NN-slug` (ej. `pr-02-esquema-sqlite`), sacada de `main`
  actualizado. PR contra `main`. El remoto es `origin` → `Kevinmass/Spectre-2`.
- El commit que cierra el PR marca la casilla en `docs/plan-spectre.md` (§6 y §9)
  y agrega `docs/qa/bitacora-PR-NN.md`.

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
