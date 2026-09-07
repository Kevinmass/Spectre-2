# Bitácora PR-C5 — Filtro por tipo de parte

Fecha: 07/09/2026
Rama: `pr-c5-filtro-tipo-parte`, de `main` (con PR-C2a/b ya mergeadas, #39/#40).

## Qué pedía el plan

> **PR-C5 `[N]` Filtro por tipo de parte.** La observación 01 pidió filtrar por
> "las partes, p. ej. que una sea una empresa". Las partes ya se extraen por
> fallo (PR-08), pero como texto libre; falta clasificar su naturaleza: persona
> física / empresa / Estado / organismo público. Clasificación sobre los
> strings de partes (reglas + listas, o modelo si no alcanza), columna nueva,
> backfill del corpus indexado, y el filtro en `buscar_hibrido` + la UI.
> *Acepta:* filtrar "una parte es el Estado" y "una parte es una empresa" desde
> la UI y ver que el conteo cambia; medir la cobertura de la clasificación
> sobre el fixture (Tomo 348) y anotarla, no forzarla.

## Qué se hizo

### `spectre/corpus/fallo/partes.py` (nuevo — clasificador puro)

`clasificar_parte(texto) -> "persona_fisica" | "empresa" | "estado" |
"organismo" | None`. Reglas + listas, **sin modelo**. Normaliza el string
(mayúsculas, sin acentos, guiones unificados) y prueba las categorías en orden:
**organismo → estado → empresa → persona_fisica**. El orden importa: "Banco de
la Nación Argentina" / "Banco de la Provincia de Buenos Aires" tienen que caer
en `organismo` antes de que "Nación Argentina" / "Provincia de …" los lleve a
`estado`, y ambos antes de que "Banco …" los lleve a `empresa`.

- `estado`: Estado Nacional, "E.N. - …" y "E.N. Ministerio/Secretaría/…",
  Provincia de X (y el invertido "X, Provincia de"), GCBA, Municipalidad/Comuna,
  ministerios y secretarías, poderes del Estado, AFIP/DGI/ANSeS, fisco,
  fuerzas de seguridad, **órganos judiciales y legislativos** (Juzgado, Cámara
  Federal/Nacional/Contencioso, Corte Suprema, Legislatura, Concejo
  Deliberante, Cámara de Diputados/Senadores).
- `organismo`: BCRA y bancos públicos, universidades nacionales, INSSJP/PAMI,
  cajas, obras sociales, entes reguladores (ENARGAS, ENRE, CNRT…), ANMAT,
  comisiones y agencias nacionales, colegios y consejos profesionales,
  sociedades y empresas del Estado ("… S.E."), Correo Oficial, Vialidad.
- `empresa`: sufijos societarios tolerantes a puntos/espacios (`_sigla()`:
  "SA", "S.A.", "S A"), SRL/SACIF/SAIC/…, "Sociedad Anónima", "y Cía.",
  cooperativas, mutuales, ART/aseguradoras, y sustantivos de actividad
  comercial (Editorial, Transportes, Industrias, Frigorífico…) para las razones
  sociales sin sufijo.
- `persona_fisica`: "Apellido, Nombre" (coma, ≤3 palabras a la izquierda),
  "N.N.", sucesiones, o 1-4 palabras sin dígitos ni palabra-clave de entidad.
  Antes de evaluar se limpian sufijos ruidosos: "y otros", paréntesis finales
  ("Heredia, Gonzalo (24609)"), prefijos numéricos ("y 468 ASSUPA"), "p/ sí …".
- Todo lo demás → `None`. **Asociaciones civiles, fundaciones, sindicatos y
  cámaras gremiales caen en `None` a propósito**: la taxonomía de 4 tipos
  (elegida con Kevin) no tiene "entidad civil".

### `corpus/fallo/structure.py`

`MetadatosFallo` gana `actor_tipo` / `demandado_tipo`; `extraer_metadatos` los
clasifica. Export `clasificar_parte` en `corpus/fallo/__init__.py`.

### Migración `0006_partes.sql` (aditiva)

`ALTER TABLE fallos ADD COLUMN` × 4: `actor` / `actor_tipo` / `demandado` /
`demandado_tipo`. Los `_tipo` con `CHECK (… IN (…4 valores…) OR … IS NULL)`
en la propia cláusula (SQLite lo permite en ADD COLUMN). Índice sobre cada
`_tipo`. Sin reconstruir la tabla (no como 0002/0004).

### `db/repo.py`

- `Fallo` += `actor` / `actor_tipo` / `demandado` / `demandado_tipo` (en el
  orden de las columnas de 0006, para `Fallo(**row)`). `_FALLO_CAMPOS_MUTABLES`
  += esos 4.
- `filtrar_chunks(parte_tipo=…)` → `AND (f.actor_tipo = ? OR f.demandado_tipo =
  ?)` (el fallo pasa si **alguna** parte es de ese tipo).
- `iter_fallos(tomo_id=None)` — recorrido de todos los fallos (o de un tomo),
  para el backfill.
- `cobertura_partes(tomo_id=None)` — total, con actor/demandado clasificado,
  reparto por tipo (cada parte por separado).

### `jobs/pipeline.py::_h_estructurar`

Persiste `actor` / `actor_tipo` / `demandado` / `demandado_tipo`. Los tomos
nuevos quedan clasificados sin backfill.

### `spectre/partes/__init__.py` (nuevo — backfill)

`reclasificar_partes(conn, *, tomo=None) -> ResumenReclasificacion`. Recorre
los fallos, recomputa `_partes(caratula)` + `clasificar_parte` **desde la
carátula ya en la base** (sin abrir PDFs) y `actualizar_fallo`. Reejecutable —
correrlo de nuevo tras afinar las reglas reescribe.

### API (`api/app.py`)

- `/api/buscar`: query param `parte:
  Literal["persona_fisica","empresa","estado","organismo"]` → `buscar_hibrido(
  parte_tipo=…)`.
- `/api/fallos/{cita}`: `+ actor / actor_tipo / demandado / demandado_tipo`.
- `POST /api/fallos/reclasificar-partes` (200, **síncrono** — es instantáneo,
  no abre PDFs ni pega a internet) → `reclasificar_partes`, devuelve el resumen.
- `search/hybrid.py`: `buscar_hibrido` gana `parte_tipo`.

### CLI

- `spectre partes reclasificar [--tomo N]` — corre el backfill e imprime la
  cobertura. `spectre partes status` — la cobertura sin recalcular.
- `spectre search buscar` gana `--parte`.

### UI

- Fila de filtros: `<select id="filtro-parte">` (cualquiera / persona física /
  empresa / Estado / organismo público). Redispara la búsqueda y se limpia con
  "Limpiar filtros".
- Vista de fallo: fila "Partes" en los metadatos — `actor (tipo) c/ demandado
  (tipo)`.
- Biblioteca: formulario "Clasificar las partes" → `POST
  /api/fallos/reclasificar-partes`, muestra el resumen en el aviso.

### Tests

- `tests/test_partes.py` (nuevo): ~55 strings reales parametrizados, más los
  casos de orden y de acentos.
- `tests/test_partes_reclasificar.py` (nuevo): `reclasificar_partes` —
  persiste, reejecutable, `--tomo` acota, tomo inexistente revienta, carátula
  sin clasificar deja `None` (pero guarda el string crudo).
- `tests/test_structure.py`: `extraer_metadatos` da los tipos.
- `tests/test_db.py`: `filtrar_chunks(parte_tipo=…)`, CHECK de dominio,
  `cobertura_partes`, `iter_fallos`.
- `tests/test_pipeline.py`: `_h_estructurar` persiste las partes (fixture 348).
- `tests/test_api.py`: `/api/buscar?parte=`, `/api/fallos` con partes, `POST
  /api/fallos/reclasificar-partes`, `parte` inválida → 422.
- `tests/test_cli.py`: `partes reclasificar` / `status`.
- `MIGRACIONES` en `test_db.py` += `0006_partes`.

## Qué decidí por mi cuenta

- **4 tipos** (`persona_fisica` / `empresa` / `estado` / `organismo`) y
  **backfill por CLI + botón en la Biblioteca**: las dos las confirmó Kevin en
  la sesión.
- **`organismo` separado de `estado`** para bancos públicos, universidades
  nacionales, PAMI/cajas, entes reguladores, sociedades del Estado. El caso
  ambiguo (frontera Estado / ente autárquico) se resuelve por el orden de las
  reglas y va documentado en el test.
- **Se persiste el string crudo `actor` / `demandado`**, no solo el tipo:
  habilita reclasificar sin reparsear y mostrar las partes en la vista de
  fallo. Hoy PR-08 no persistía ninguno de los dos.
- **El backfill lee `fallos.caratula`, no reabre PDFs.** Actor/demandado salen
  de la carátula, que ya está en la base — reclasificar todo el corpus es
  instantáneo. Por eso el endpoint de la UI es síncrono (a diferencia del sync
  de sumarios de C2b, que sí pega a internet).
- **Asociaciones civiles / fundaciones / sindicatos / cámaras gremiales quedan
  sin clasificar (`None`).** Es consecuencia de la taxonomía de 4 tipos: no hay
  "entidad civil". Son la mayor parte del 16 % no clasificado (ver medición).
- **Sin modelo de ML.** Las reglas dan 84 % de cobertura sobre el corpus real;
  el plan lo permite ("reglas + listas, o modelo si no alcanza") y 84 % con el
  resto siendo entidades civiles alcanza. Un modelo queda para otro PR si hace
  falta.
- **Regla de provincia amplia** (`\bPROVINCIA DE ?L?\b` en cualquier posición):
  gana cobertura del invertido "Córdoba, Provincia de" a costa de algún falso
  positivo tipo "Colegio … de la Provincia de La Pampa" — mitigado poniendo los
  colegios profesionales en `organismo`, que se evalúa primero.

## En qué me desvié del plan

- El plan sugería medir la cobertura "sobre el fixture (Tomo 348)". Se midió
  sobre la base real indexada (tomos **348 + 349**, 286 fallos) — es el número
  honesto y ya estaba a mano, como en PR-C2b.
- No se agregó `partes_clasificadas` por tomo a `/api/estado` (lo daba como
  "opcional" el plan): el `POST` de reclasificación devuelve el resumen
  completo y la UI lo muestra en el aviso, alcanza.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13; CI valida 3.11).

```
./.venv/Scripts/ruff.exe check .                    # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .           # -> 123 files already formatted
./.venv/Scripts/python.exe -m pytest -q             # -> 526 passed, 3 skipped, 28 deselected
node tests/verificar_cita.mjs && node tests/verificar_resaltado.mjs  # -> TODO OK
```

### Cobertura de la clasificación (criterio de aceptación), base real 348 + 349

`./.venv/Scripts/python.exe -m spectre.cli partes reclasificar`:

```
fallos recorridos          286
con actor clasificado      274      (de 286)
con demandado clasificado  206      (de 217 con demandado; 69 fallos no tienen)
partes sin clasificar      92
  empresa                  115
  estado                   116
  organismo                30
  persona_fisica           219
```

**Cobertura: 480 / 572 partes = 84 %.** El 16 % sin clasificar es casi todo
entidades civiles (asociaciones, fundaciones, sindicatos, cámaras gremiales),
que la taxonomía de 4 tipos no cubre, más un puñado de nombres anonimizados
por iniciales.

### El filtro cambia el conteo

`spectre search buscar "impuesto ganancias" --solo-lexico --k 50`:

| filtro | resultados (chunks) |
|---|---|
| (sin filtro) | 32 |
| `--parte estado` | 22 |
| `--parte empresa` | 11 |
| `--parte persona_fisica` | 19 |

Agrupado por fallo (`/api/buscar`, `k=10`): `q="daños y perjuicios"` sin filtro
10 → `parte=estado` 3; `q="impuesto"` sin filtro 10 → `parte=persona_fisica` 3,
`parte=empresa` 8.

## Dudas / pendientes

- **Cobertura de `persona_fisica`** — el fallback "parece un nombre" puede
  tragarse una razón social corta sin sufijo (mitigado con la lista de
  sustantivos de actividad). Se mide, no se fuerza.
- **Entidades civiles sin categoría.** Si la primera usuaria las quiere
  filtrar, hace falta un 5º tipo (`entidad_civil`) — cambio de taxonomía, otro
  PR.
- **Carátulas mal parseadas** (deuda PR-06/07): si `caratula` viene sucia,
  `_partes` y la clasificación heredan el error.
- **Reclasificar tras cambiar las reglas**: hay que acordarse de correr
  `spectre partes reclasificar` (o el botón) — no hay trigger automático.
