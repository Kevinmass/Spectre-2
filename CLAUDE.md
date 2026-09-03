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

El esqueleto (`pyproject.toml`, ruff, pytest, CI) lo crea PR-00. Una vez cerrado:

- `pytest` — corre toda la suite. Un solo test: `pytest ruta/al/test.py::nombre`.
- `ruff check` — lint. `ruff format` — formato.
- `spectre --help` — CLI (subcomandos se van llenando por fase; `serve` levanta
  la UI en localhost a partir de PR-20).

Python de desarrollo: 3.11 (D-11). La máquina tiene 3.13 instalado; usar un venv
3.11 para que coincida con CI.

## Fixture de referencia

`data/tomos/348.pdf` (Fallos, Tomo 348, 968 páginas, ~126 fallos). Los criterios
de aceptación de las Fases 1 a 3 son números medidos sobre ese tomo: offset de
página 6, 126 entradas en el índice, fallo más largo 57 páginas, mediana 4
páginas, ~1.041 chunks, 887 citas. Un resultado lejos de esos números indica que
algo aguas arriba se rompió.

## Lo que hay en `legacy/`

El intento anterior (`document-semantic-search/`, 3.022 LOC). PR-00 lo mueve a
`legacy/`. Es referencia histórica: no se importa ni se reutiliza código.
