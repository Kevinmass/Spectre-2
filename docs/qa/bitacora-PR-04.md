# Bitácora PR-04 — Extracción de texto y paginación oficial

Fecha: 03/09/2026
Criterio de aceptación (plan §6): sobre el Tomo 348, ≥95% de páginas con número
detectado y un único offset (el valor medido es 6).

**Medido: 956/968 = 98,76% de cobertura, offset 6 en las 956, 0 discrepancias.**
Coincide con D-3 del plan ("recuperable en 956 de 968 páginas (98,8%) con offset
constante de 6").

Primer PR de la Fase 1. Trae la primera dependencia de procesamiento pesada
(`pdfplumber`) y el primer fixture binario del repo.

## Qué hice

### `spectre/corpus/pdf/extract.py`

Lee un PDF de tomo y devuelve el texto por página con el número de página
oficial detectado.

- **`PaginaTexto(pdf_page, texto, pagina_oficial)`** — `pdf_page` 1-based como lo
  numera el PDF; `texto` crudo sin limpiar (eso es PR-05); `pagina_oficial` el
  número impreso en el encabezado, o `None` si no se pudo leer. **No se inventa
  un número** (D-05).
- **`detectar_pagina_oficial(texto)`** — mira las primeras 3 líneas del texto de
  la página y busca el encabezado. En el Tomo 348, con pdfplumber, el encabezado
  sale así:
  - página impar (derecha): `DE JUSTICIA DE LA NACIÓN  <n>` — el número al final
  - página par (izquierda): `<n>  FALLOS DE LA CORTE SUPREMA` — el número al
    principio
  Dos regex, una por caso. Descarta números fuera de `1..5000` (un tomo no se
  acerca; corta un falso positivo). Estas expresiones están **calibradas contra
  el Tomo 348**: el formato del encabezado cambia entre décadas (riesgo R-2), y
  cada tomo que las rompa entra como caso de regresión con su fixture.
- **`extraer_texto(pdf_path)`** — abre con `pdfplumber`, `page.extract_text()`
  por página. Lanza `FileNotFoundError` si no existe y `ValueError` si el PDF no
  tiene páginas (nada de devolver `[]` como si hubiera andado). No toca la base.
- **`calcular_offset(paginas)`** → `ResultadoOffset(offset, total, detectadas,
  consistentes, discrepancias)` con `cobertura` y `consistencia` como
  propiedades. `offset` es la moda de `pdf_page - pagina_oficial` entre las
  páginas con número; `discrepancias` son los `pdf_page` que no la respetan.
- **`persistir(repo, tomo_id, paginas, offset)`** — el único cruce a la base
  (por `db/repo.py`, como manda la regla de dependencias). Borra las páginas del
  tomo, inserta las nuevas en lote y actualiza `tomos.paginas` /
  `tomos.offset_pagina`. Reextraer un tomo **reemplaza**, no acumula.

`corpus/` no importa `index/` ni `embed/`. El import de `Repo` es solo para tipos
(`TYPE_CHECKING`).

### `spectre/db/repo.py`

Dos operaciones nuevas de página, para que `persistir` no inserte de a una:

- `insert_paginas(tomo_id, filas)` — lote vía `executemany`; cada fila es
  `(pdf_page, pagina_oficial, texto_crudo)`. `texto_limpio` lo completa PR-05.
- `borrar_paginas(tomo_id)` — devuelve cuántas borró.

### `spectre/cli.py`

- **`spectre pdf stats <pdf>`** — extrae el texto del tomo e imprime total de
  páginas, cuántas tienen número oficial (con %), el offset, la consistencia y
  hasta 15 `pdf_page` con discrepancia. Es la herramienta que mide el criterio
  de aceptación a mano. No persiste nada, no finge nada. Import de `pdfplumber`
  perezoso (solo `pdf` lo necesita).
- `pdf` sin acción es error, igual que `db`.

### `pyproject.toml`

- `dependencies += ["pdfplumber>=0.11"]` — primera dependencia de procesamiento.
  MIT/Apache (sobre `pdfminer.six`), coherente con la licencia del proyecto.
  Elegida sobre pymupdf (más rápida pero AGPL) a pedido de Kevin en el chat.
- Marca de pytest **`slow`**, excluida por defecto
  (`addopts = "-ra -m 'not slow'"`). Hoy `slow` es solo la medición de
  aceptación sobre el tomo completo (~5 min, y necesita `data/tomos/348.pdf`).
  Correrla: `pytest -m slow`.

### Fixture: `tests/fixtures/tomo348_p1-16.pdf`

Las primeras 16 páginas reales del Tomo 348 (portada 1–6 sin número + cuerpo
7–16 = oficiales 1–10, encabezado impar y par). 150 KB. Recortado con `pypdf`
(comando en `tests/fixtures/README.md`). Publicación oficial de dominio público.
`.gitattributes` marca `*.pdf binary`.

El PDF completo (`data/tomos/348.pdf`, 3 MB, 968 páginas) **no va al repo**
(gitignored). Lo copié de `~/Downloads/LibroVol348-1.pdf` para medir localmente.

### Tests

- **`tests/test_extract.py`** (17; 1 es `slow`):
  - `detectar_pagina_oficial`: encabezado impar → 15; par → 42; sin encabezado →
    None; solo mira las 3 primeras líneas; número disparatado (99999) → None;
    página 0 → None; texto vacío → None.
  - Sobre el recorte de 16 páginas: extrae las 16; portada 1–6 → `None`, cuerpo
    7–16 → 1–10; el acento real se conserva (`NACIÓN`, no mojibake); archivo
    inexistente → `FileNotFoundError`.
  - `calcular_offset`: sobre el recorte da offset 6, 10/16 detectadas, 10
    consistentes, 0 discrepancias; sin ninguna detección → `offset None`,
    cobertura 0; con una página que rompe el offset → esa `pdf_page` en
    `discrepancias`, `consistentes < detectadas`.
  - `persistir`: vuelca 16 filas, `get_pagina(tomo,7).pagina_oficial == 1`,
    `texto_limpio is None`, `tomo.paginas == 16`, `tomo.offset_pagina == 6`;
    llamarlo dos veces no acumula (sigue en 16).
  - **`test_aceptacion_tomo_348`** (`slow` + `skipif` sin el PDF): 968 páginas,
    offset 6, cobertura ≥ 0.95, consistencia 1.0, 0 discrepancias.
- **`tests/test_db.py`** (+2): `insert_paginas` en lote (incluye una fila con
  `pagina_oficial None`); `borrar_paginas`.
- **`tests/test_cli.py`** (+2): `pdf stats` sobre el recorte imprime páginas /
  offset / 6; `pdf` sin acción es error.

## Qué decidí por mi cuenta

- **Librería PDF: pdfplumber.** Lo pregunté en el chat; Kevin eligió pdfplumber
  (MIT, coherente con la licencia) sobre pymupdf (más rápida, AGPL). La
  velocidad recién importa en PR-25 y el pipeline es reanudable por lotes.
- **Fixture = recorte real de 16 páginas, no PDF sintético.** Prueba las regex
  contra texto real de pdfplumber (el layout impar/par, el acento, la portada
  sin número), no contra mi reproducción de ese layout. 150 KB es aceptable como
  binario de test. Alternativa (generar un PDF con un writer nuevo de
  dependencia) probaba menos y sumaba dep.
- **Marca `slow`, excluida por defecto.** La medición de aceptación necesita el
  tomo completo y tarda ~5 min con pdfplumber. Meterla en el `pytest` de todos
  los días arruina el ciclo. Queda explícita (`pytest -m slow`) y con `skipif`
  para CI, que no tiene el archivo. El número igual está medido y anotado acá y
  en el plan §6.
- **`persistir` vive en `extract.py`**, no en `repo.py`. `repo.py` es la capa de
  datos genérica; orquestar extracción→persistencia es lógica de `corpus`. El
  cruce a la base pasa por métodos de `Repo`, que es lo que pide la regla.
- **`persistir` reemplaza (borra + inserta).** Reextraer un tomo tras cambiar el
  parser no debe dejar filas viejas ni chocar con el `UNIQUE(tomo_id, pdf_page)`.
- **Sin subcomando para persistir a la base todavía.** `spectre pdf stats` mide;
  persistir un tomo necesita un tomo registrado, y registrar tomos es territorio
  de PR-16/17. PR-19 arma el pipeline (extraer→limpiar→…) como job y ahí se
  llama a `persistir`. Por ahora es función con test, como el runner de PR-03.
- **Regex atadas al Tomo 348.** El plan lo asume (R-2: "los números verificados
  valen para el Tomo 348"; cada tomo que rompa entra como regresión). No intenté
  un parser genérico de encabezados de 1863–2026 ahora.

## En qué me desvié del plan

- **Encadené PR-04 con PR-03 en la misma sesión**, contra "un PR por sesión"
  (`CLAUDE.md` / plan §1). A pedido explícito de Kevin en el chat, con PR-03 ya
  mergeado.
- **Fixture binario en el repo.** El plan no habla de fixtures de test. El
  criterio de aceptación se mide sobre `data/tomos/348.pdf`, que no está
  versionado; para tener tests que corran en CI hace falta un recorte chico
  versionado. Documentado en `tests/fixtures/README.md`.
- **Marca `slow` y cambio de `addopts`.** El plan no lo pide; es la forma de
  tener la medición de aceptación como test sin volver lento el run de todos los
  días.
- Nada más material. Texto por página, detección de número oficial y cálculo de
  offset están, con el número medido contra el plan.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . -q                        # -> (sin salida: ok)
./.venv/Scripts/ruff.exe format --check .                  # -> 25 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 84 passed, 1 deselected (6-7 s)
./.venv/Scripts/python.exe -m pytest -q -m slow            # -> 1 passed (~5 min, usa data/tomos/348.pdf)
```

Medición de aceptación a mano:

```
./.venv/Scripts/python.exe -m spectre.cli pdf stats data/tomos/348.pdf
# páginas        968
# con nº oficial  956  (98.8%)
# offset          6
# consistencia    956/956  (100.0%)
#   (sin discrepancias)
```

Las 12 páginas sin número son las 1–6 (portada) y 963–968 (índice general): no
tienen encabezado, es correcto que queden en `None`.

`spectre pdf stats tests/fixtures/tomo348_p1-16.pdf` sobre el recorte: 16
páginas, 10 con número (62,5% — el resto es portada), offset 6, consistencia
100%.

## Dudas que quedaron

- **pdfplumber es lento**: ~5 min para las 968 páginas del Tomo 348 en esta
  máquina. Para los 349 tomos son horas. Es la contra conocida de la elección
  (a cambio de licencia limpia) y el pipeline es reanudable por diseño; PR-25 lo
  mide y decide si duele.
- **La consistencia del offset es 100% en el Tomo 348**, así que `calcular_offset`
  nunca ejerció el camino de "hay dos offsets, elijo la moda" sobre datos
  reales. Cubierto con un test sintético; el primer tomo con encabezados
  irregulares dirá si el criterio (moda) es el correcto o hay que ponderar por
  tramos.
- **`extraer_texto` carga todo el tomo en memoria** (lista de 968 `PaginaTexto`
  con el texto completo). Para un tomo son ~2 MB de texto, va bien. Si algún
  tomo escaneado + OCR pesa mucho más, habrá que streamear a la base por lotes
  en vez de acumular; hoy no hace falta.
- **`persistir` no valida que `len(paginas)` coincida con lo que ya había.**
  Reextraer con un parser que de golpe ve menos páginas pisaría silenciosamente.
  Cuando PR-19 lo llame desde un job convendría loguear el delta.
- **Números pegados (`348145`)**: D-3 los menciona; con pdfplumber salen
  separados (`348` y el número en líneas distintas). Si otra versión de
  pdfplumber o algún tomo los pega, la regex `\d{1,4}` tomaría `3481` mal. No lo
  vi pasar en el Tomo 348; queda anotado.
