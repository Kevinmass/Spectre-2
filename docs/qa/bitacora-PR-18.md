# Bitácora PR-18 — Sonda de calidad

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **mide caracteres por página y clasifica el
tomo en `digital` / `requiere_ocr`. Acepta: el Tomo 348 clasifica `digital`;
un tomo anterior a 1950 clasifica `requiere_ocr` y no se indexa como si
estuviera vacío.**

## Resultado en una línea

`spectre/corpus/pdf/quality.py` — `medir_calidad(paginas)` clasifica un tomo
en `digital` / `requiere_ocr` según qué fracción de páginas supera un umbral
de caracteres extraídos por `pdfplumber`. **Mitad del criterio verificada
contra el tomo real**: el Tomo 348 completo (968 páginas) clasifica `digital`
con 99,4% de páginas por encima del umbral (mediana 2.335 caracteres/página);
349 igual (99,3%). **La otra mitad —un tomo real anterior a 1950— no se pudo
verificar esta sesión**: no hubo acceso de red a
`sjservicios.csjn.gov.ar` (timeout de conexión desde esta máquina, confirmado
también a nivel TCP con `Test-NetConnection`), así que no hay forma de bajar
un tomo viejo para calibrar/probar contra un escaneo genuino. Se prueba en su
lugar con `PaginaTexto` fabricados a mano que reproducen la forma exacta de un
escaneo sin OCR (texto vacío en casi todas las páginas) — mismo tipo de dato
que consume `medir_calidad`, así que el camino de código que corre es
idéntico al que correría sobre un PDF real; lo que no está probado es que un
escaneo real de la CSJN efectivamente tenga esa forma. Ver "Dudas" abajo.

## Qué hice

### `spectre/corpus/pdf/quality.py`

- **`ResultadoCalidad(calidad, total, con_texto, caracteres_totales)`** +
  propiedades `cobertura` y `caracteres_por_pagina`.
- **`medir_calidad(paginas: list[PaginaTexto]) -> ResultadoCalidad`**: cuenta,
  por página, los caracteres del texto crudo (`p.texto.strip()`, el que da
  `extraer_texto`, **antes** de `limpiar` — la limpieza asume que ya hay algo
  que limpiar). Una página "con texto" es la que supera `_UMBRAL_CARACTERES =
  200`. Si al menos la mitad (`_COBERTURA_MINIMA = 0.5`) de las páginas superan
  el umbral, `calidad = "digital"`; si no, `"requiere_ocr"`. Sin páginas,
  revienta con `ValueError` (D-05: no hay un tercer resultado "no sé" tratado
  como éxito; además `extraer_texto` ya revienta antes si el PDF no tiene
  páginas, así que este caso es defensivo, no el camino esperado).
- Calibración del umbral, medida sobre el Tomo 348 real (968 páginas): mínimo
  0, máximo 3.286, mediana 2.335, promedio 2.211 caracteres/página; solo 6
  páginas (0,6%) por debajo de 200 caracteres (portada + índice de consulta),
  y solo 7 por debajo de 500. La brecha esperada contra un escaneo sin OCR
  (que da 0 en prácticamente el 100% de las páginas, porque no hay capa de
  texto de la que extraer nada) es enorme, así que 200/50% no necesita ser
  fino — ver "Dudas" sobre por qué esto sigue siendo una calibración contra un
  solo lado del problema.
- No persiste nada (igual que `catalog.py` y `download.py`): `corpus/pdf`
  sigue sin importar `db/`; llenar `tomos.calidad` es tarea de PR-19.

### `spectre/cli.py`

- **`spectre pdf quality <pdf>`** — corre `extraer_texto` + `medir_calidad` y
  muestra calidad, páginas, páginas con texto (con %) y caracteres/página
  promedio.

### Tests

- **`tests/test_quality.py`** (nuevo, 9 casos):
  - `medir_calidad` sobre listas de `PaginaTexto` fabricadas: texto real →
    `digital`; escaneo sin capa de texto (texto vacío) → `requiere_ocr`;
    escaneo con una sola página de portada legible entre 300 vacías → sigue
    siendo `requiere_ocr` (un puñado de páginas con texto no arrastra al
    tomo); cobertura exactamente por debajo de la mitad → `requiere_ocr`, sin
    redondear para arriba; sin páginas → `ValueError`; `caracteres_por_pagina`
    es el promedio simple.
  - Sobre el recorte real `tomo348_p1-16.pdf` (16 páginas, 6 de portada/índice
    + 10 de cuerpo): clasifica `digital`, cobertura 68,75%.
  - **`test_aceptacion_tomo_348`** (`slow`, necesita `data/tomos/348.pdf`):
    `calidad == "digital"`, `cobertura >= 0.99` (medido: 99,4%).
- **`tests/test_cli.py`** (+1): `pdf quality` sobre el recorte imprime
  `calidad`, `digital` y `caracteres/página`.

### Docs

- `docs/plan-spectre.md`: casilla PR-18 (§6) con el resultado medido y la
  brecha del criterio; §9 → "Próximo: PR-19".
- `CLAUDE.md`: "Estado del código" → PR-18; `## Comandos` + `spectre pdf
  quality`.

## Qué decidí por mi cuenta

- **Medir sobre el texto crudo, no sobre `texto_limpio`.** `limpiar()`
  (PR-05) asume que hay encabezado que sacar y guiones que unir; corrida sobre
  una página vacía de un escaneo no cambia nada (sigue vacía), así que no
  aporta señal para esta clasificación y solo agregaría una dependencia
  (`corpus/pdf/clean`) que no hace falta.
- **Umbral fijo (200 caracteres, 50% de cobertura) en vez de algo relativo al
  tomo** (p. ej. un percentil interno). Un umbral relativo necesitaría al
  menos un tomo de referencia de cada clase para calibrarse solo, y hoy solo
  tengo la clase "digital" verificada con datos reales (ver "Dudas"). Un
  número fijo, documentado con la distribución real del Tomo 348, es más
  auditable y es exactamente lo que D-10 pide: "el sistema mide y clasifica".
- **Sin persistencia ni tocar `db/repo.py`.** Mismo patrón que todo
  `corpus/pdf` y `corpus/csjn` hasta ahora (`catalog.py`, `download.py`,
  `extract.py` es la única excepción histórica, con `persistir()` porque
  PR-02 ya necesitaba escribir algo real para probar el repo). `tomos.calidad`
  ya existe en el esquema desde `0001_initial.sql`; escribirlo es tarea del
  pipeline completo (PR-19), que va a tener tomo + tomo_id de verdad, no solo
  un PDF suelto.

## En qué me desvié del plan

- **No hay medición contra un tomo real anterior a 1950.** El criterio de
  aceptación del plan pide explícitamente ese caso y esta sesión no tuvo
  acceso de red para bajarlo (confirmado: `urllib.request` a
  `sjservicios.csjn.gov.ar` da `TimeoutError`, y `Test-NetConnection` al puerto
  443 del mismo host da `False`). No lo fuerzo con un número inventado (D-05);
  lo que hay es la mitad del criterio medida de verdad (348 → digital) y la
  lógica de clasificación probada con datos fabricados que tienen la forma
  correcta. Pendiente, en cuanto haya red: `spectre csjn catalog` para
  encontrar un `csjn_tomo_id` de antes de 1950, `spectre csjn download
  <tomo_id> data/tomos/<N>.pdf`, y `spectre pdf quality data/tomos/<N>.pdf`
  tiene que dar `requiere_ocr`. Si no da, revisar el umbral con los números
  reales de ese tomo, no forzar la clasificación.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> todos formateados
./.venv/Scripts/python.exe -m pytest -q                # -> 288 passed, 3 skipped, 23 deselected
./.venv/Scripts/python.exe -m pytest -q -m slow tests/test_quality.py
                                                        # -> 1 passed (~57 s)
```

Medido a mano sobre los dos tomos reales:

```
./.venv/Scripts/python.exe -m spectre.cli pdf quality data/tomos/348.pdf
# calidad: digital, 968 páginas, 962 con texto (99.4%), 2211 caracteres/página
```

```python
from spectre.corpus.pdf import extraer_texto, medir_calidad

r = medir_calidad(extraer_texto("data/tomos/349.pdf"))
# digital, 913 páginas, 907 con texto (99.3%), 2192 caracteres/página
```

Spike de red bloqueado, repro exacto:

```
./.venv/Scripts/python.exe -c "import urllib.request; urllib.request.urlopen('https://sjservicios.csjn.gov.ar/sj/tomosFallos.do?method=iniciar', timeout=10)"
# -> urllib.error.URLError: <urlopen error timed out>
```

```powershell
Test-NetConnection -ComputerName sjservicios.csjn.gov.ar -Port 443 -InformationLevel Quiet
# -> False
```

## Dudas que quedaron

- **El umbral (200 caracteres, 50% cobertura) está calibrado contra un solo
  lado real** (dos tomos digitales, 348 y 349). El lado `requiere_ocr` está
  probado solo contra datos fabricados a mano, no contra un escaneo real de
  la CSJN — un escaneo real *podría* tener alguna capa de texto ruidosa (OCR
  parcial de mala calidad hecho por el propio sitio, metadata, marcas de
  agua) que dé más de 200 caracteres en más páginas de las esperadas, lo que
  correría el umbral. No hay forma de saberlo sin bajar uno. Es el primer
  punto a revisar cuando haya red.
- **Un tomo "a medias" (escaneado parcialmente, o con algunas páginas
  ilegibles) da `requiere_ocr` entero**, sin distinguir qué páginas
  puntuales fallaron. Para el MVP (D-10: clasificar el tomo completo y dejarlo
  en una cola) alcanza; si en el futuro hace falta indexar tomos mixtos
  página por página, `ResultadoCalidad` tendría que exponer qué páginas
  específicas no llegan al umbral (ya están en `caracteres`, no se guardan).
- **`_COBERTURA_MINIMA = 0.5` es arbitrario dentro del margen amplio que deja
  la brecha real** (99%+ vs. 0% esperado): cualquier valor entre, digamos,
  10% y 90% separaría igual los dos casos medidos. Elegí el punto medio por
  no tener motivo para otra cosa, no porque 50% sea especial.
