# Bitácora PR-C2b — Persistir + mostrar el sumario oficial + filtro por voz / materia

Fecha: 07/09/2026
Rama: `pr-c2b-persistir-sumarios`, sacada de `pr-c2-sumarios-voces` (PR-C2a,
todavía sin mergear a `main`). El PR se abre contra `main`; hasta que C2a
entre, el diff del PR muestra también los commits de C2a.

## Qué pedía el plan

> **PR-C2b — persistir + mostrar el sumario + filtro por voz.**
> Tabla(s) `sumarios`/`voces` (+ `fallo_voces`) con su migración; traer los
> sumarios por fallo en la ingesta (o un `spectre sumarios sync`) y
> persistirlos; `/api/fallos/{cita}` y los resultados de `/api/buscar`
> muestran el/los sumario(s); filtro por voz en `/api/buscar` + la UI (input
> con autocompletado sobre el tesauro). Evaluar
> `analisisDocumental.materiaSecretaria` para el filtro por materia/rama.
> **Acá se cumple el criterio de aceptación de PR-C2:** cada resultado
> muestra su sumario oficial cuando existe; se puede filtrar la búsqueda por
> al menos una voz y el conteo cambia.

## Qué se hizo

### Migración `0005_sumarios.sql` (aditiva)

Tres tablas nuevas, ninguna reconstrucción (no como 0002/0004):

- `sumarios(id, fallo_id→fallos ON DELETE CASCADE, orden, texto, voces,
  materia, id_documento, sincronizado_at)`, `UNIQUE(fallo_id, orden)`.
  `voces` es JSON con las voces de **ese** sumario (para mostrarlo sin join,
  igual criterio que `fallos.jueces`). `materia` es
  `analisisDocumental.materiaSecretaria`.
- `voces(id, valor UNIQUE, codigo)` — el catálogo local de voces (en
  mayúsculas, como las da la CSJN). `codigo` es el `codigoValor` del tesauro
  si se conoce (hoy siempre `NULL`: las voces de un sumario vienen sin código;
  el código solo lo da `getVoces`, que no se usa en el sync).
- `fallo_voces(fallo_id, voz_id, PK(fallo_id, voz_id))` — forma normalizada
  para el filtro por voz con índice (`idx_fallo_voces_voz`).

Sin CHECK: el vocabulario de voces/materias lo trae la CSJN, no lo fija
Spectre.

### `db/repo.py`

- `SumarioGuardado` (dataclass, distinta de `corpus.csjn.sumarios.Sumario`:
  `db/` no importa `corpus/`).
- `upsert_voz(valor, codigo=None)` — `INSERT ... ON CONFLICT(valor) DO UPDATE`
  que completa el código si llega y no pisa uno previo.
- `reemplazar_sumarios_de_fallo(fallo_id, filas)` — borra `sumarios` +
  `fallo_voces` del fallo y reinserta (idempotente, igual que
  `borrar_citas_de_fallo`). Cada fila `(orden, texto, voces, materia,
  id_documento)`; registra las voces y arma `fallo_voces`.
- `list_sumarios_de_fallo`, `sumarios_por_fallos` (batch, para `/api/buscar`),
  `buscar_voces_locales(termino)` (LIKE en mayúsculas, para el
  autocompletado), `materias_del_corpus()` (DISTINCT, para el `<select>`),
  `contar_sumarios_de_tomo`.
- `filtrar_chunks(...)` — dos kwargs nuevos: `voz` (subconsulta
  `fallo_voces⋈voces`, comparación en mayúsculas) y `materia` (subconsulta
  `sumarios.materia = ?`). Mismo patrón que `tribunal_origen` / `tipo_seccion`.

### `corpus/csjn/sumarios.py`

- `Sumario` gana `materia: str | None = None`; `_map_sumario` lo saca de
  `analisisDocumental.materiaSecretaria` (`_materia` acepta string o
  `{descripcion}`). Único cambio de contenido.
- `TransporteHTTP.abrir_sesion()` ahora es **idempotente** (si la sesión ya
  está abierta no hace el GET de nuevo): reusar un transporte para los ~126
  fallos de un tomo evita 126 GET redundantes.

### `spectre/sumarios/__init__.py` (módulo nuevo)

Orquesta el sync componiendo `corpus.csjn` (cliente) + `db.repo`, como
`search/` compone `index/` + `db/`. **No** es una etapa del pipeline (ver
"decisiones").

- `sincronizar_tomo(conn, numero, *, transporte=None, pausa=0.5, log=None) ->
  ResumenSync` — itera los fallos del tomo con `pagina_inicio` + `cita`,
  reusa una sesión HTTP, `buscar_sumarios` por fallo, `reemplazar_sumarios_de_
  fallo`. `ResumenSync(tomo, fallos_consultados, fallos_con_sumario,
  sumarios_totales, voces_distintas)`.
- `sincronizar_fallo(conn, fallo_id, *, transporte=None) -> int` — un fallo
  suelto (tests `red` / uso puntual).

### API (`api/app.py`)

- `/api/fallos/{cita}`: `+ "sumarios": [{texto, voces, materia, id_documento}]`.
- `/api/buscar`: `+ voz` / `+ materia` (query params) → `buscar_hibrido`; cada
  resultado agrupado `+ "sumarios": [{texto, voces, materia}]`
  (`sumarios_por_fallos`, batch).
- `GET /api/voces?q=` → `{"voces":[{valor, codigo}]}` (autocompletado, contra
  la tabla local — **no** contra el tesauro vivo de la CSJN).
- `GET /api/materias` → `{"materias":[str]}`.
- `POST /api/tomos/{numero}/sumarios/sync` (202) → `sincronizar_tomo` en
  `BackgroundTasks`, conexión propia (patrón de `_correr_pipeline_en_fondo`);
  404 si el tomo no existe.
- `/api/estado`: `+ "sumarios": <n>` por tomo (`contar_sumarios_de_tomo`).
- `search/hybrid.py`: `buscar_hibrido` gana `voz` / `materia`, los pasa a
  `filtrar_chunks`.

### CLI

- `spectre sumarios sync <numero> [--pausa SEG] [--verbose]` — corre
  `sincronizar_tomo` sobre un tomo ya indexado e imprime el `ResumenSync`.
- `spectre sumarios status` — cuántos sumarios / voces hay, por tomo.
- `spectre search buscar` gana `--voz` / `--materia` (consistencia con PR-A2).

### UI (`web/index.html`, `app.js`, `style.css`)

- Fila de filtros: input **Voz** con `<datalist id="voces-datalist">`
  (autocompletado nativo, sin lib — D-15) que se repuebla vía `/api/voces`
  (debounce 200 ms, mín. 2 caracteres); `<select>` **Materia** poblado una vez
  desde `/api/materias`. Los dos redisparan la búsqueda al cambiar y se
  limpian con "Limpiar filtros".
- Resultados: bloque "Sumario oficial de la CSJN" (el primero + "N sumarios
  más"), con la materia y las voces como chips.
- Vista de fallo: los sumarios completos, después de los metadatos.
- Biblioteca: columna "Sumarios" con el conteo por tomo (sube solo con el
  polling de 2 s), y un tercer formulario "Sincronizar sumarios de la CSJN"
  (gemelo de indexar / subir) → `POST .../sumarios/sync`.

### Tests

- `test_db.py`: upsert de voz (dedupe + backfill), reemplazo idempotente,
  `fallo_voces` sin duplicar, cascada al borrar el fallo,
  `filtrar_chunks(voz=/materia=)`, `buscar_voces_locales`, `materias_del_corpus`,
  `contar_sumarios_de_tomo`. Actualizado el listado `MIGRACIONES` y las tablas
  esperadas.
- `test_sumarios.py`: `_materia` (string / objeto / vacío) y `_map_sumario`
  con `analisisDocumental`.
- `test_sumarios_sync.py` (nuevo): `sincronizar_tomo` con transporte falso —
  persiste texto/voces/materia, dedup de voces entre fallos, una sola sesión,
  reejecutable sin acumular, fallo sin sumario no rompe, tomo inexistente
  revienta; `sincronizar_fallo` suelto; un `red` que sincroniza 348:36 real.
- `test_api.py`: `/api/fallos` con `sumarios`, `/api/buscar` con `sumarios` +
  `voz=` / `materia=` cambiando el conteo, `/api/voces`, `/api/materias`,
  `/api/estado` con el conteo por tomo, `POST .../sumarios/sync` (202 y 404,
  tarea en segundo plano con `sincronizar_tomo` monkeypatcheado). Actualizado
  el `assert` exacto de `/api/estado`.
- `test_cli.py`: `sumarios sync` (resumen + tomo no indexado revienta),
  `sumarios status`.

## Qué decidí por mi cuenta

- **El sync es un comando/endpoint aparte, no una etapa del pipeline.**
  Kevin lo confirmó en la sesión: CLI + botón en la Biblioteca. Motivos: el
  corpus ya está indexado (una etapa nueva obligaría a reindexar), y no quiero
  atar la ingesta a un sitio con WAF que puede colgar un request a mitad. El
  spike ya listaba "o un `spectre sumarios sync`". No se tocó `ETAPAS` ni el
  CHECK de `tomos.estado`.
- **Autocompletado contra la tabla local `voces`, no contra `getVoces`.** Solo
  tiene sentido ofrecer voces que algún fallo indexado trae (una voz del
  tesauro sin fallos filtraría a 0). `buscar_voces` (el cliente de C2a) queda
  para un futuro "explorar el tesauro entero". Instantáneo y sin dependencia
  externa en cada tecla.
- **`materia` se persiste y se filtra** (Kevin lo pidió en la sesión): columna
  `sumarios.materia` + `<select>` en la UI + `/api/buscar?materia=`. Cubre el
  "materia / rama del derecho" de la observación 01.
- **`voces` normalizada (`voces` + `fallo_voces`) *y* denormalizada
  (`sumarios.voces` JSON).** La normalizada es para el filtro con índice; la
  JSON para mostrar cada sumario con sus voces sin un join por resultado. La
  duda del cierre de C2a ("¿tabla o texto?") se resuelve: las dos, cada una
  para lo suyo.
- **`abrir_sesion` idempotente** en `TransporteHTTP` (cambio menor en código
  de C2a): sin esto, reusar el transporte igual hacía un GET de sesión por
  fallo. Los `red` de C2a siguen verdes.
- **`upsert_voz` público commitea; `_upsert_voz` interno no** — para que
  `reemplazar_sumarios_de_fallo` no commitee a mitad de su propia unidad.
- **Sin barra de progreso del sync en la UI**, solo el conteo de la columna
  "Sumarios" subiendo con el polling que ya existe. Una barra fina (fallos
  hechos / total) sería lindo pero pide estado nuevo; el conteo alcanza para
  "está avanzando".

## En qué me desvié del plan

- El plan dice "input con autocompletado sobre el tesauro"; el autocompletado
  es sobre las voces **del corpus**, no el tesauro completo de la CSJN (ver
  decisiones). El filtro por voz funciona igual; lo que no se puede es
  autocompletar una voz que ningún fallo cargado tiene — que es justo la que
  no querés elegir.
- El plan menciona "traer los sumarios por fallo en la ingesta (o un `spectre
  sumarios sync`)": se hizo solo lo segundo, y además por la UI.
- `codigo` en `voces` queda siempre `NULL` por ahora (las voces de un sumario
  no traen código; solo `getVoces` lo da). La columna está para cuando se
  quiera cruzar con el tesauro.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13; CI valida 3.11).

```
./.venv/Scripts/ruff.exe check .                    # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .           # -> 119 files already formatted
./.venv/Scripts/python.exe -m pytest -q             # -> 446 passed, 3 skipped, 28 deselected
node tests/verificar_cita.mjs                       # -> TODO OK
node tests/verificar_resaltado.mjs                  # -> TODO OK
./.venv/Scripts/python.exe -m pytest -q -m red tests/test_sumarios.py tests/test_sumarios_sync.py
#   -> 4 passed  (contra el sitio real de la CSJN)
```

- 446 passed vs 419 al cerrar C2a: +27 tests (test_db +9, test_sumarios +3,
  test_sumarios_sync +7 puros, test_api +8; deselected 28 vs 27 por el `red`
  nuevo de sync).

### Criterio de aceptación, medido sobre la base real (`data/spectre.db`, tomos 348 + 349 ya indexados)

`./.venv/Scripts/python.exe -m spectre.cli sumarios sync 348 --pausa 0.3`
(pega contra la CSJN, ~7 min):

```
tomo                348
fallos consultados  133
fallos con sumario  132
sumarios totales    591
voces distintas     420
```

(133 fallos, no 126: la segmentación real del Tomo 348 da 133 — mismo número
que PR-10. Solo 1 fallo quedó sin sumario en la base de la Secretaría.)

- **Cada resultado muestra su sumario oficial cuando existe.** Verificado con
  `TestClient` sobre la base real: `/api/buscar?q=recurso extraordinario
  sentencia arbitraria&solo_lexico=true` → el resultado `348:56` trae
  `"sumarios": [{texto:"Es arbitraria la sentencia que rechazó el beneficio de
  litigar sin gastos…", voces:["BENEFICIO DE LITIGAR SIN GASTOS","SENTENCIA
  ARBITRARIA",…]}]`; `GET /api/fallos/348:56` → 4 sumarios. `GET
  /api/voces?q=recurso` y `GET /api/materias` responden con lo del corpus.
- **El filtro por voz / materia cambia el conteo.** Misma consulta, `k=10`,
  agrupada por fallo:

  | filtro | fallos |
  |---|---|
  | (sin filtro) | 10 |
  | `voz=RECURSO DE QUEJA` | 1 |
  | `voz=HONORARIOS DE ABOGADOS Y PROCURADORES` | 1 |
  | `materia=Penal` | 3 |
  | `voz=SENTENCIA ARBITRARIA` + `materia=Consumo` | 1 |

  Y a nivel chunk (`spectre search buscar "..." --solo-lexico --k 50`): 50 →
  13 (`--voz "SENTENCIA ARBITRARIA"`) → 3 (`--materia Penal`).

## Dudas / pendientes

- **Cruce fallo ↔ sumario por `tomo` + `pagina_inicio`.** Si la segmentación
  (deuda PR-06/07) calculó mal la página de inicio de un fallo, se le pegarían
  los sumarios de otro. Bajo riesgo; sin defensa nueva acá.
- **Volumen de requests del sync.** ~126 fallos/tomo × (1 POST + ≥1 GET). Con
  349 tomos es un trabajo largo; hoy es manual, un tomo por vez. Si se
  automatiza (todo el corpus), hace falta pensar rate-limit y reintentos.
- **`codigo` de las voces sin poblar** — ver arriba.
- **El `<datalist>` nativo** tiene UX distinta por navegador. Si molesta, un
  dropdown propio es trabajo de la Tanda B (PR-B3).
- **Estabilidad del scraping**: los `red` avisan si el front de la Secretaría
  cambia; el cliente revienta claro ante la página del WAF.
