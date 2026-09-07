# Bitácora PR-C2a — Spike de sumarios de la CSJN + cliente

Fecha: 07/09/2026
Rama: `pr-c2-sumarios-voces` (de `main` con PR-C1 y el hotfix de indexar
mergeados, #37 y #38).

## Qué pedía el plan

> **PR-C2 `[N]` Sumarios oficiales de la CSJN — y las voces como filtro.**
> *Empieza con un spike:* (1) confirmar que los sumarios se pueden consultar
> programáticamente; (2) ver en qué formato vienen — si es PDF no seleccionable
> (imagen), decidir si entra OCR; (3) ver si las voces vienen estructuradas.
> *Acepta:* cada resultado muestra su sumario oficial cuando existe; se puede
> filtrar por al menos una voz y el conteo cambia.

## Qué se hizo — y por qué se partió en dos

El spike (paso obligado del PR) mostró que la integración es viable pero la
implementación completa —persistir, mostrar el sumario en cada resultado,
filtro por voz con autocompletado en la UI, migración de tablas nuevas— no
entra en una sesión. Se partió PR-C2 en:

- **PR-C2a (esto): spike + cliente.** El recon en vivo y el módulo cliente,
  con tests. No persiste nada.
- **PR-C2b: persistir + mostrar + filtrar.** Cierra el criterio de aceptación.

Mismo patrón que PR-16 (spike del catálogo → `catalog.py` + `red` tests).

## El spike (respuestas)

Detalle completo en **`docs/qa/spike-C2-sumarios.md`**. Resumen:

1. **¿Programático? Sí.** Flujo HTTP stateful de 3 pasos contra
   `sjconsulta.csjn.gov.ar`: `GET consultaSumarios/consulta.html` (abre sesión,
   2 cookies) → `POST consultaSumarios/buscar.html` (form `filter.tomo` +
   `filter.pagina`, `g-recaptcha-response` vacío — **el backend no lo valida**)
   → `GET consultaSumarios/paginarSumarios.html?startIndex=K` (array JSON, 10
   por página). Público, sin credenciales.
2. **¿Formato? JSON con texto seleccionable. NO hace falta OCR.** El sumario
   (`texto`) y las voces vienen como campos de un objeto JSON. (El
   `verTomo?tomoId=N` de `sjconsulta` sí devuelve un PDF —el volumen publicado
   entero, 1000+ páginas— pero es un callejón: la API real es JSON.)
3. **¿Voces estructuradas? Sí, doble vía.** Cada sumario trae `voces` como
   string separada por `" - "` (tesauro controlado, en mayúsculas). Y hay un
   endpoint de autocompletado `POST autocomplete/getVoces.html` (`term=`) que
   devuelve `[{codigoValor, valor}]` — el `codigoValor` es lo que el buscador
   manda en `filter.idsVocesElegidas` para filtrar por voz.

Hallazgos extra:

- **Un fallo tiene varios sumarios** (uno por regla de doctrina). Medido:
  `348:36` → 7, `348:31` → 1, `349:1` → 2.
- **No todos los fallos están sumariados.** `348:145` → 0 resultados.
- **WAF con firma de cliente.** `curl.exe` puede recibir la página del WAF;
  **`urllib` de Python pasa** (verificado: los 3 tests `red` corren verdes con
  el módulo real). El cliente detecta la página del WAF y revienta en vez de
  devolver vacío.
- El objeto trae también `analisisDocumental` con `materiaSecretaria`,
  `sentidoPronunciamiento`, `tipoRecurso`, `referenciasNormativas`, ministros…
  — materia prima para el filtro por materia/rama de la observación 01, a
  evaluar en C2b.

## Qué se entregó

### `spectre/corpus/csjn/sumarios.py` (nuevo)

- **`buscar_sumarios(tomo, pagina, *, transporte=None) -> list[Sumario]`** — el
  flujo de 3 pasos + bucle de paginación de a 10 hasta cubrir
  `totalResultados`. `Sumario(tomo, pagina, caratula, fecha, voces, texto,
  id_documento)`: `voces` es `tuple[str, ...]` (split por `" - "`), `texto`
  con los tags HTML sacados, `fecha` normalizada a ISO (`dd/mm/yyyy` →
  `AAAA-MM-DD`).
- **`buscar_voces(termino) -> list[Voz]`** — autocompletado del tesauro.
  `Voz(codigo, valor)`.
- **`TransporteHTTP`** — encapsula la sesión (cookies) y los 3 requests;
  inyectable (`transporte=`) para testear el bucle sin red. Detecta la página
  del WAF y lanza `RuntimeError`.
- Helpers puros y testeables: `_texto_plano`, `_voces`, `_fecha_iso`,
  `_id_documento`, `_total_resultados`, `_map_sumario`, `_map_voces`.
- **No toca la base ni importa `index`/`embed`** (regla de dependencias). No
  persiste — eso es C2b.

### `spectre csjn sumario <tomo> <pagina>` (CLI)

Imprime los sumarios de ese fallo (carátula, fecha, voces, texto). Mide, no
persiste — como `csjn catalog` y `pdf …`.

### Tests — `tests/test_sumarios.py`

- Parseo puro (siempre): tags/espacios, split de voces (un guion pegado no
  parte), fecha ISO, id de documento, `totalResultados`, `_map_sumario`,
  `_map_voces`.
- Bucle de `buscar_sumarios` con un `_FakeTransporte`: total 0 → no pagina;
  una página; varias páginas; trunca si el server devuelve de más; corta si
  una página viene vacía antes del total.
- **`red`** (contra el sitio real): `buscar_sumarios(348, 36)` → ≥2 sumarios,
  todos con voces y texto, fecha `2025-02-13`; `buscar_sumarios(348, 145)` →
  `[]`; `buscar_voces("contrato administrativo")` → contiene
  `"CONTRATO ADMINISTRATIVO"`.

### Docs

- `docs/qa/spike-C2-sumarios.md` (nuevo) — el recon completo.
- `docs/plan-v2.md` — PR-C2 partido en C2a `[x]` / C2b `[ ]`; §9 anota que el
  spike de C2 no dispara OCR; §10 actualizado.
- `CLAUDE.md` — módulo `csjn/sumarios`, comando `csjn sumario`, nota `red`.

## Qué decidí por mi cuenta

- **Partir PR-C2 en C2a/C2b.** El plan dice "empieza con un spike"; el spike +
  el cliente son un entregable reviewable y cerrado, la persistencia+UI es
  otro. La casilla de PR-C2 **no** se marca (su criterio se cumple en C2b);
  se marca la sub-casilla C2a.
- **`urllib`, no `requests` ni un browser headless.** El repo ya usa `urllib`
  (`catalog.py`, `download.py`) y pasa el WAF. Sin dependencias nuevas.
- **`TransporteHTTP` como clase inyectable** en vez de un callable suelto como
  `catalog.listar_catalogo(pedir_pagina=...)`: acá son 3 requests con estado
  de sesión compartido, una clase lo expresa mejor. Los tests pasan un doble.
- **`fecha` a ISO en el cliente**, no dejarla `dd/mm/yyyy`. Es para casar con
  `fallos.fecha` (ISO) en C2b; normalizar temprano evita repetirlo.
- **El cliente revienta ante la página del WAF**, no devuelve `[]`. Regla del
  proyecto: ningún stub que reporte éxito.
- **No toqué el pipeline ni la API.** Todo lo que persiste o muestra es C2b.

## En qué me desvié del plan

- PR-C2 pasó de una casilla a dos (C2a hecha, C2b pendiente). El criterio de
  aceptación de PR-C2 no se cumple todavía y está dicho.
- El spike descartó el sub-camino "PDF de sumarios" (`verTomo` en
  `sjconsulta`): existe pero es el volumen entero, no la base estructurada.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13; CI valida 3.11).

```
./.venv/Scripts/ruff.exe check .                         # -> All checks passed!
./.venv/Scripts/ruff.exe format --check spectre tests    # -> 66 files already formatted
./.venv/Scripts/python.exe -m pytest -q                  # -> 419 passed, 3 skipped, 27 deselected
./.venv/Scripts/python.exe -m pytest -q -m red tests/test_sumarios.py
#   -> 3 passed, 13 deselected  (contra el sitio real de la CSJN)
./.venv/Scripts/python.exe -m spectre.cli csjn sumario 348 36   # -> 7 sumarios, con voces y texto
./.venv/Scripts/python.exe -m spectre.cli csjn sumario 348 145  # -> 0 sumarios
```

- 419 passed vs 406 al cerrar el hotfix: +13 tests de `test_sumarios.py` (10
  puros + 3 `red` que quedan deselected en el run por defecto → 27 deselected
  vs 24).

## Dudas / pendientes para C2b

- **Cruce fallo ↔ sumario.** El cruce es por `tomo` + `pagina` (= la cita
  `N:P` = `fallos.pagina_inicio`). Un fallo cuya página de inicio la
  segmentación calculó mal (deuda PR-06/07) traería los sumarios de otro. Bajo
  riesgo pero anotarlo.
- **Fallos sin sumario.** Mayoría de los viejos, y varios nuevos. La UI tiene
  que manejar "este fallo no tiene sumario oficial" sin ruido.
- **Modelo de datos de las voces.** ¿Tabla `voces` normalizada + `fallo_voces`
  (permite el filtro con índice) o un `sumarios.voces` como texto? El filtro
  por voz con conteo pide lo primero. A decidir en C2b con la migración.
- **Volumen de requests.** Sincronizar los sumarios de un tomo entero son
  ~130 fallos × (1 POST + N GETs). Hace falta un `sleep` cortés entre fallos
  y, seguramente, que sea un paso aparte del pipeline (no bloquear la ingesta).
- **`materiaSecretaria`** como fuente del filtro por materia/rama (observación
  01): está en `analisisDocumental`, no lo trae `Sumario` todavía. Sumarlo en
  C2b si se decide usarlo.
- **Estabilidad del endpoint.** Es scraping de un front, no una API con
  contrato. Los `red` tests avisan si cambia; el cliente revienta claro.
