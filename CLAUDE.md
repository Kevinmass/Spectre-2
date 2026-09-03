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

## Reglas de trabajo

- **Un PR por sesión. No encadenar dos.**
- Cada PR cierra escribiendo `docs/qa/bitacora-PR-NN.md`: qué hizo, qué decidió
  por su cuenta, en qué se desvió del plan, qué verificó y con qué comandos
  exactos, qué dudas quedaron. Tiene que poder leerse sin el diff al lado.
- Marcá la casilla del PR en `docs/plan-spectre.md` (§6 y §9), en el mismo commit
  que lo cierra.
- Los criterios de aceptación son números medidos sobre el fixture, no "parece
  que anda". Verificá contra el número del plan.

## Reglas del código

- **Ningún stub que reporte éxito.** Si algo no está implementado, falla
  ruidosamente. El proyecto anterior murió por simular procesamiento
  (`time.sleep(2)` + `chunks_count=10` inventado) y marcar documentos como
  indexados.
- Las rutas se resuelven contra la raíz del paquete, nunca contra el CWD. La
  config tiene que cargar igual desde cualquier directorio (bug D-02).
- Todo el acceso a datos pasa por `spectre/db/repo.py`. El estado va en SQLite,
  no en JSON escrito a mano (bug D-04).
- **Regla de dependencias:** `corpus/` no importa `index/` ni `embed/`.
  `search/` no importa `corpus/`. Todo cruce pasa por `db/repo.py`.
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

- `python -m pytest` — corre toda la suite. Un solo test:
  `python -m pytest tests/test_db.py::nombre`.
- `ruff check .` — lint. `ruff format --check .` — formato (el gate de CI corre
  `ruff check`; el formato se verifica a mano antes de commitear).
- `python -m spectre.cli <sub>` o `spectre <sub>` (entry point instalado):
  - `spectre config` — imprime las rutas resueltas (verificación a ojo de D-02).
  - `spectre db migrate` — crea `data/spectre.db` y aplica las migraciones
    pendientes de `spectre/db/migrations/`. `spectre db status` — qué se aplicó.
  - `spectre ingest` / `serve` — declarados pero revientan (los implementan
    PR-19 / PR-20). Ningún stub que reporte éxito.

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

## Lo que hay en `legacy/`

El intento anterior (`document-semantic-search/`, 3.022 LOC). PR-00 lo mueve a
`legacy/`. Es referencia histórica: no se importa ni se reutiliza código.
