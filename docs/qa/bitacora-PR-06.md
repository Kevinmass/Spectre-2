# Bitácora PR-06 — Parser del índice de partes

Fecha: 03/09/2026
Criterio de aceptación (plan §6): 126 entradas en el Tomo 348, con las páginas
dentro del rango.

**Medido: 129 carátulas / 133 referencias de página** en el ÍNDICE POR LOS
NOMBRES DE LAS PARTES del Tomo 348 (`pdf_page` 963–967). Las páginas citadas van
de 1 a 955. La diferencia con el 126 del plan no se forzó — hipótesis y plan de
verificación abajo, en "En qué me desvié" y "Dudas". El ejemplo textual de la
decisión D-2 (`Zárate ... : p. 380`) sale exacto, así que el parser está leyendo
lo que tiene que leer.

## Qué hice

### `spectre/corpus/fallo/` (paquete nuevo)

Primer módulo de la carpeta `corpus/fallo/` que nombra la §4 del plan.
`__init__.py` reexporta la API; `segmenter` / `structure` / `citations` llegan en
PR-07 a PR-10.

### `spectre/corpus/fallo/index_parser.py`

- **`EntradaIndice(caratula: str, paginas: tuple[int, ...])`** — una línea del
  índice. `paginas` es tupla porque una parte que litigó en varios fallos
  aparece una vez con todas sus páginas (`Tabacalera Sarandí ...: ps. 569, 841 y
  955`). Explotar eso en un fallo por página es PR-07.
- **`localizar_indice_partes(pdf) -> range`** — índices de página (0-based) de la
  sección, **buscando desde el final** del PDF. Una página es del índice de
  partes si su cabecera (primeras 2 líneas) contiene `NOMBRES DE LAS PARTES` —el
  running header que llevan las 5 páginas—. Frena en la primera página hacia
  atrás que ya no lo tiene. Si no aparece en ninguna, `ValueError` ruidoso
  (D-05): no se inventa un índice vacío.
- **`_parsear_columna(lineas) -> list[EntradaIndice]`** — el armado de entradas.
  Junta líneas en un buffer hasta encontrar `: p. NNN` (regex `_REF`, que cubre
  `p. 380`, `ps. 443 y 494`, `ps. 569, 841 y 955`, `ps.43 y 45`); lo de antes es
  la carátula, lo de después arranca la siguiente. Descarta:
  - letras divisoras del abecedario (`A`, y `N R` cuando dos caen en un renglón);
  - fragmentos del encabezado partidos por el corte de columna
    (`E LAS PARTES (i)`, `INDICE POR LOS NOM`, `(ii) NOMBRES DE`), pero **solo en
    las 2 primeras líneas útiles** de la columna, para no comerse una carátula
    que mencione "partes".
  Maneja dos cortes de renglón: el número de página en la línea siguiente
  (`... perjuicios: p.` / `274`) —cae solo con el buffer— y la cola de una lista
  larga de páginas (`... ps. 569, 841` / `y 955`) —línea que es solo números, se
  pega a la última entrada de la misma columna—.
- **`analizar_indice(pdf_path) -> ResumenIndice`** — pipeline completo:
  localizar, recortar cada página en dos columnas por `width / 2`, extraer y
  parsear cada mitad. `ResumenIndice` tiene `paginas_indice`, `entradas` y las
  propiedades `caratulas` / `referencias` / `paginas_citadas` que miden la
  aceptación. Lanza si el archivo no existe o si no salió ninguna entrada.
- **`parsear_indice(pdf_path) -> list[EntradaIndice]`** — la lista plana, la API
  para PR-07 y el pipeline.

No toca la base. `corpus/fallo/` no importa `index/` ni `embed/`; tampoco
importa `corpus/pdf/` (hace su propia extracción por recorte de columna).

### `spectre/cli.py`

- **`spectre pdf index <pdf> [--muestra N]`** — parsea el índice e imprime el
  rango de `pdf_page` de la sección, el nº de carátulas, el de referencias de
  página, el rango de páginas citadas y las carátulas que aparecen en varios
  fallos. Con `--muestra N`, las primeras N entradas. No persiste nada, no finge
  nada: es la herramienta que mide el criterio de aceptación a mano, como
  `pdf stats` y `pdf clean`.

### Fixture: `tests/fixtures/tomo348_indice.pdf`

`pdf_page` 962–968 del Tomo 348 (7 páginas: última de cuerpo + las 5 del índice
de partes + el índice general). 200 KB. Recortado con `pypdf` (comando en
`tests/fixtures/README.md`). Contiene la sección entera, así que casi todos los
asserts corren sin `slow`.

### Tests

- **`tests/test_index_parser.py`** (24; 1 `slow`):
  - `_parsear_columna`: entrada de una línea; carátula en varias líneas; número
    en el renglón siguiente; `ps. N y M`; `ps.43 y 45` sin espacio; cola `y 955`
    en renglón aparte; letra divisora descartada; `N R` descartado; fragmento de
    encabezado al tope descartado; "partes" dentro de una carátula (línea 3+) no
    se descarta; columna sin `: p.` no produce entradas.
  - `localizar_indice_partes`: encuentra `[1..5]` en el fixture; no confunde el
    índice general (que termina con la entrada de TOC "Indice por los nombres de
    las partes (i)"); `ValueError` sobre `tomo348_p1-16.pdf` (sin índice);
    `FileNotFoundError` si el archivo no existe.
  - `analizar_indice` sobre el fixture: 129 carátulas, 133 referencias;
    `paginas_indice == (2, 6)`; páginas citadas de 1 a 955; anclas conocidas
    (`Zárate → 380`, `Raskovsky → 1`, `AFIP c/ Organización → 953`); las 3
    carátulas multi-fallo con sus tuplas; `parsear_indice` devuelve la lista
    plana.
  - **`test_aceptacion_tomo_348`** (`slow` + `skipif`): sobre el tomo completo,
    `paginas_indice == (963, 967)`, 129 / 133, rango 1–955.
- **`tests/test_cli.py`** (+2): `pdf index` imprime "carátulas" y "129" y
  `pdf_page 2–6`; `--muestra 3` imprime la primera carátula y la línea de
  carátulas multi-fallo.

### `CLAUDE.md` (parte del `/init` de esta sesión)

Cuatro secciones agregadas: **Estado del código** (qué existe vs. qué es plan),
convención de migraciones y contrato del handler de jobs en **Reglas del
código**, y una sección **Tests** (layout plano, sin `conftest.py`, fixtures,
`slow`).

## Qué decidí por mi cuenta

- **Corte de columna fijo en `width / 2`.** Probé un gutter dinámico (el hueco
  de x más grande entre palabras cerca del centro): en 3 de las 5 páginas el
  hueco real quedaba a x≈220 y arrastraba texto de la otra columna. Probé
  0.47 y 0.52: peor, meten *bleed*. `width / 2` exacto separa limpio las 5
  páginas del Tomo 348. Calibrado a este tomo (R-2); otro con la caja corrida
  entra como regresión con su fixture.
- **`localizar` mira solo la cabecera, no el texto completo.** El índice general
  (`pdf_page 968`) termina con la línea de tabla de contenidos `Indice por los
  nombres de las partes (i)`, que hace `match` de substring en el texto completo
  y metía la 968 en el rango. Mirar solo las 2 primeras líneas (donde va el
  running header real) lo resuelve.
- **`EntradaIndice.paginas` es tupla, no se explota.** `ps. 443 y 494` es una
  carátula que aparece en dos fallos. A nivel índice se guarda como una entrada
  con dos páginas; PR-07 (que arma los `fallos` con su cita y su rango) la
  parte. Explotar acá adelantaría una decisión que es de PR-07.
- **Continuación `y 955` pegada a la misma columna.** Una lista larga de páginas
  puede cortar de renglón. Solo se pega si la línea es *solo* números y el
  buffer está vacío (la entrada anterior ya cerró). No cruza el borde entre
  columnas (no pasa en el Tomo 348; si pasara se perdería esa página y entraría
  como regresión).
- **Sin ruta de persistencia.** Igual que PR-04 y PR-05, y a pedido explícito de
  Kevin en el chat: `parsear_indice` es función con test y `spectre pdf index`
  mide. Construir filas de `fallos` necesita un tomo registrado (PR-16/17) y es
  el trabajo de PR-07. PR-19 arma el pipeline y ahí se llama.
- **Fixture = recorte real de 7 páginas.** Prueba el parser contra el texto real
  de pdfplumber (el layout a dos columnas, el corte de renglón, el falso
  positivo del índice general), no contra una reproducción. Cubre la sección
  entera, así que la medición corre sin `slow`; el `slow` solo verifica que
  `localizar` la encuentre entre las 968 páginas.
- **Marca `slow` para la aceptación sobre el tomo entero.** `localizar` recorre
  páginas desde el final llamando `extract_text` y el tomo completo tarda con
  pdfplumber. Mismo mecanismo que PR-04/05.

## En qué me desvié del plan

- **Encadené PR-06 tras PR-05 en la misma sesión**, contra "un PR por sesión"
  (`CLAUDE.md` / plan §1). A pedido explícito de Kevin en el chat. Además, y a
  diferencia de PR-04→05, **PR-05 todavía no está mergeado a `main`**: la rama
  `pr-06-indice-partes` sale de `pr-05-limpieza-texto`, así que este PR arrastra
  el commit de PR-05 hasta que ese entre. Al mergear, primero PR-05, después
  PR-06.
- **El número de aceptación no da: 129 carátulas / 133 referencias vs. 126.** No
  lo forcé; el test fija el número medido (129 / 133) como regresión. Hipótesis
  del gap:
  - **Referencias cruzadas.** El índice de partes lista algunas entradas que
    remiten a un fallo listado también bajo otra parte, p. ej. `Haras El Moro SA
    s/ queja ... en Carol, María Luisa y otros c/ Haras El Moro SA ...: p. 716`.
    Tiene su propia página (716 ≠ 755 de "Carol"), así que puede ser un fallo
    distinto o una remisión. PR-07, que arma los fallos reales y **chequea
    solapamientos y cobertura 1→953**, va a decir cuáles de las 129 no son el
    inicio de un fallo distinto.
  - **Carátulas multi-fallo** (3) contadas de otra forma en la verificación
    original.
  - El plan dice "~126 fallos" con tilde de aproximación en varios lugares.
  - **A confirmar con Kevin** cómo se contó el 126.
- **`p. 955`** (3ª referencia de "Tabacalera Sarandí") queda 2 por encima del
  "de la página 1 a la 953" del plan. El Tomo 348 tiene ~956 páginas oficiales
  (offset 6 sobre 968 menos el índice), así que 955 es una página válida; el
  "1 a 953" del plan es el span de páginas de *inicio* de fallo, y 955 es una
  referencia no-inicial. El test lo fija explícito (`max == 955`).
- **Marca `slow` nueva** para `test_aceptacion_tomo_348` (el mecanismo ya existe
  desde PR-04).
- **`CLAUDE.md`** editado por el `/init` de la sesión (4 secciones nuevas).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 32 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 131 passed, 3 deselected (~13 s)
./.venv/Scripts/python.exe -m pytest -q -m slow            # -> 3 passed (~10 min, usa data/tomos/348.pdf)
```

Medición de aceptación a mano:

```
./.venv/Scripts/python.exe -m spectre.cli pdf index data/tomos/348.pdf
# páginas del índice     pdf_page 963–967
# carátulas              129
# referencias de página  133
# páginas citadas        1–955
# carátulas en varios fallos (3):
#   [443, 494]  Fernández de Kirchner, Cristina Elisabet y otros s/ incidente ...
#   [43, 45]    Ferrari, María Alicia c/ Levinas, Gabriel Isaías s/ Incidente
#   [569, 841, 955]  Tabacalera Sarandí S.A. c/ EN - AFIP - DGI s/ proceso ...
```

Sobre el fixture: `pdf_page 2–6`, 129 / 133, mismas anclas — coincide con el
tomo entero (la sección está completa en el recorte).

Auditoría del corte de columna: probé `width * {0.47, 0.5, 0.52}` y un gutter
dinámico por hueco de palabras; solo `0.5` separa las 5 páginas sin arrastrar
texto de la columna vecina (queda un residuo en 1 carátula, ver Dudas).

## Dudas que quedaron

- **126 (plan) vs. 129 / 133 (medido).** La principal. El parser lee bien
  (ancla `Zárate → 380` exacta, `Raskovsky → 1`, cobertura 1→953 + la ref 955).
  Confirmar con Kevin el conteo original; PR-07 debería cerrar el número al
  armar los fallos y chequear solapamientos.
- **Residuo de columna en 1 carátula.** `pdf_page 966`, entrada #122: sale
  `Souza, Amanda Graciela c/ Ente 23.283 y 23.412 Cooperador Leyes y otro s/
  otros reclamos` — el `23.283 y 23.412` viene de una referencia vecina que el
  corte a `width/2` no separó del todo en esa página. **No afecta el conteo ni
  la página** (p. 294 es correcta); ensucia el texto de la carátula. Anotado
  para limpieza fina (¿PR-07, al normalizar carátulas contra el texto real del
  fallo?).
- **Carátulas en MAYÚSCULAS / versalitas.** `DEFENSOR DEL PUEBLO DE LA NACION C/
  ESTADO NACIONAL Y OTRO S/ AMPAROS Y SUMARISIMOS: p. 895` queda tal cual. El
  `clean.py` de PR-05 normalizaría versalitas, pero opera sobre páginas de
  cuerpo, no sobre el índice. ¿Normalizar la carátula acá o en PR-07 (que ya va
  a comparar la carátula del índice con la del encabezado del fallo)?
- **Corte fijo a `width/2` calibrado al Tomo 348.** Otro tomo con la caja de
  texto corrida va a necesitar recalibrar. Entra como regresión con su fixture
  (R-2), como las regex de encabezado de PR-04.
- **`localizar` recorre desde el final llamando `extract_text`.** En el Tomo 348
  son 7 páginas hasta encontrar la sección — barato. Si algún tomo tuviera el
  índice lejos del final sería más caro, pero el índice siempre va al final del
  volumen.
