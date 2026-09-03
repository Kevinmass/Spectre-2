# Bitácora PR-07 — Segmentador de fallos

Fecha: 03/09/2026
Criterio de aceptación (plan §6): 126 fallos en el Tomo 348, sin solapamientos,
cubriendo de la página 1 a la 953. El fallo más largo son 57 páginas (legítimo,
el fallback no debe partirlo) y la mediana es de 4.

**Medido sobre el Tomo 348 (vía índice):**

| número | plan | medido |
|---|---|---|
| fallos | 126 | **133** (129 carátulas del índice; 3 figuran en varios fallos) |
| solapamientos | 0 | **0** |
| cobertura | 1 → 953 | **1 → 956** |
| fallo más largo | 57 | **57** ✅ ("Acevedo ... s/ quiebra", 348:189, págs. 189–245) |
| mediana | 4 | **4** ✅ |

Los dos números de estructura del plan (57 y 4) dan **exactos**, lo que valida el
método. El total (126 vs 133) arrastra la diferencia ya medida en PR-06 (126 vs
129 carátulas del índice) más la explosión de las 3 carátulas multi-fallo. No se
forzó — hipótesis y verificación abajo.

## Qué hice

### `spectre/corpus/fallo/segmenter.py`

- **`FalloSegmentado(caratula, cita, pagina_inicio, pagina_fin, metodo)`** —
  `cita` es `<tomo>:<pág. inicio>` (D-3), p. ej. `348:189`. Páginas oficiales,
  ambos extremos inclusive. `metodo` es `"indice"` o `"delimitadores"`.
- **`segmentar_desde_indice(entradas, *, tomo_numero, pagina_fin_cuerpo)`** —
  **Plan A** (D-2). Cada carátula del índice de partes (PR-06) arranca un fallo
  en su página oficial. El rango va hasta la página anterior al arranque del
  siguiente; el último, hasta `pagina_fin_cuerpo`. Las carátulas que figuran en
  varios fallos (`ps. 443 y 494`) producen **un fallo por página**. Falla
  ruidosamente (D-05) si dos carátulas arrancan en la misma página o si el
  índice cita más allá del cuerpo: no se inventa un rango.
- **`segmentar_por_delimitadores(paginas, *, tomo_numero, pagina_fin_cuerpo)`** —
  **Plan B**, para un tomo sin índice parseable. Un fallo arranca donde una
  página del cuerpo trae la **carátula en versalita** en sus primeras 8 líneas
  (`_linea_es_caratula`: tiene `c/` o `s/` y ≥2 palabras que `es_versalita`
  marca). Los delimitadores de texto del plan —`FALLO DE LA CORTE`, `Autos y
  Vistos`, `Buenos Aires, <fecha>`— **no** se usan para cortar: D-2 midió que
  sobre-parten (54 de 121 páginas con delimitador caen dentro de un fallo ya
  empezado). El resultado se marca `dudosa`.
- **`segmentar(entradas | None, paginas, *, tomo_numero)`** — orquesta:
  `pagina_fin_cuerpo` = mayor número de página oficial detectado; si hay
  `entradas` usa Plan A (los errores propagan), si no Plan B con `dudosa=True`.
- **`ResumenSegmentacion`** — `fallos`, `metodo`, `dudosa` y las propiedades que
  miden la aceptación: `cantidad`, `cobertura`, `solapamientos`, `huecos`,
  `pagina_mas_larga`, `mediana_paginas`.

`corpus/fallo/` no importa `index/` ni `embed/`. Importa `es_versalita` de
`corpus/pdf/clean` (mismo criterio que la normalización de PR-05) — es un cruce
dentro de `corpus/`, en el sentido del pipeline (pdf → fallo).

### `spectre/corpus/pdf/clean.py`

- **`_es_versalita` → `es_versalita`** (pública), reexportada en
  `corpus/pdf/__init__.py`. La usa el segmentador para reconocer la carátula que
  encabeza cada fallo. Sin cambio de comportamiento; los tests de PR-05 pasan
  igual (prueban vía `limpiar`).

### `spectre/cli.py`

- **`spectre pdf segment <pdf> [--tomo N] [--muestra N]`** — extrae el texto,
  parsea el índice (si puede) y arma los fallos; imprime método, cantidad,
  cobertura, solapamientos, huecos, fallo más largo y mediana. Con `--muestra N`,
  los primeros N fallos con su cita `Fallos: 348:189`. El número de tomo se
  infiere del nombre del archivo (`348.pdf`, `tomo348_indice.pdf`) o se pasa con
  `--tomo`. No persiste nada: mide, como `stats` / `clean` / `index`.

### Fixture: `tests/fixtures/tomo348_cuerpo_p189-246.pdf`

Seis páginas **no contiguas** del Tomo 348: inicio de "Acevedo" (oficial 189),
cuatro de su interior (190, 199, 244, 245) e inicio de "Favero" (246). Prueba que
el Plan B ve dos inicios y **no mete un corte** dentro del fallo de 57 páginas.
100 KB. Comando de regeneración en `tests/fixtures/README.md`.

### Tests

- **`tests/test_segmenter.py`** (14; 1 `slow`):
  - `segmentar_desde_indice`: rangos correctos + citas; carátula multi-fallo se
    explota (una entrada `(20, 50)` → dos fallos `348:20` y `348:50`); páginas de
    inicio repetidas → `ValueError`; índice que cita más allá del cuerpo →
    `ValueError`; sin entradas → `ValueError`.
  - `segmentar_por_delimitadores`: detecta un fallo por carátula en versalita;
    **no corta** por `-I-` / `Suprema Corte:` / `FALLO DE LA CORTE SUPREMA` /
    `Buenos Aires, <fecha>` / `Autos y Vistos` (páginas interiores sintéticas →
    un solo fallo); sin ninguna carátula → `ValueError`.
  - `test_fallback_no_parte_el_fallo_largo`: sobre el fixture real, el Plan B da
    `348:189` (189–245, **57 páginas**) y `348:246`; las 4 páginas interiores no
    disparan un corte.
  - `ResumenSegmentacion`: `cantidad` / `cobertura` / `pagina_mas_larga` /
    `mediana_paginas` sobre tramos armados a mano; detección de solapamiento y
    hueco.
  - **`test_aceptacion_tomo_348`** (`slow` + `skipif`): 133 fallos, 0
    solapamientos, cobertura (1, 956), más largo 57, mediana 4; `348:1` es
    Raskovsky, `348:189` tiene 57 páginas.
- **`tests/test_cli.py`** (+3): `pdf segment` sobre `tomo348_indice.pdf` imprime
  método/más largo 57/mediana 4/solapamientos 0; `--muestra 2` imprime
  `Fallos: 348:1` y la carátula de Raskovsky; PDF con nombre sin número →
  `SystemExit` pidiendo `--tomo`.

### `CLAUDE.md` y memoria (meta de la sesión)

- **`CLAUDE.md` → "Reglas de trabajo"**: reemplacé "Un PR por sesión. No
  encadenar dos." por la metodología nueva que pidió Kevin: trabajar el PR
  indicado, al terminar `git push` + `gh pr create`, y **esperar nueva
  instrucción** (no arrancar el siguiente por cuenta propia). Actualicé el
  encabezado "Estado del código" a PR-06.
- Guardé la misma regla en la memoria del proyecto
  (`workflow-pr-push-open-wait`).

## Qué decidí por mi cuenta

- **La carátula en versalita es el corte del Plan B, no los delimitadores de
  texto.** El plan dice "fallback por delimitadores"; D-2 midió que `FALLO DE LA
  CORTE` / `Autos y Vistos` / `Buenos Aires, <fecha>` sobre-parten porque los
  disparan los dictámenes del Procurador y las resoluciones intermedias. La
  carátula en versalita (`acEvEdo, Eva maRía c/ ... s/ quiEbRa`) aparece **una
  sola vez por fallo**, al principio, y no en el interior. Verificado sobre 4
  páginas interiores reales del fallo de 57 páginas: ninguna la trae. Los
  delimitadores del plan quedan como confirmación conceptual, no como corte.
- **Explotar las carátulas multi-fallo.** `ps. 443 y 494` = las mismas partes en
  dos fallos distintos → dos `FalloSegmentado` con citas `348:443` y `348:494`.
  Es lo que hace que el conteo sea 133 y no 129.
- **`pagina_fin_cuerpo` = mayor número de página oficial detectado.** En el Tomo
  348 es 956 (la última página de cuerpo antes del índice). El último fallo
  (`348:955`, Tabacalera) llega hasta ahí.
- **`es_versalita` pública** en vez de importar la privada `_es_versalita` entre
  módulos hermanos. Es reutilizable y ya tiene tests indirectos.
- **`segmentar` no hace fallback si el Plan A tira `ValueError`.** Solo cae al
  Plan B si `entradas` viene vacío/`None` (el CLI pasa `None` cuando
  `parsear_indice` falló). Un error de `segmentar_desde_indice` (páginas
  repetidas, cita fuera de rango) es un bug que tiene que verse, no taparse con
  el fallback.
- **Sin ruta de persistencia**, como PR-04/05/06 y a pedido de Kevin: funciones
  con test + `spectre pdf segment` que mide. Construir filas de `fallos` necesita
  un tomo registrado (PR-16/17) y lo arma PR-19.
- **Fixture de 6 páginas no contiguas.** Cubre el caso que pide el plan ("el
  fallback no debe partir el fallo de 57 páginas") con ~100 KB en vez de traer
  las 58 páginas del fallo entero.

## En qué me desvié del plan

- **Encadené PR-07 tras PR-06 en la misma sesión.** A pedido explícito de Kevin,
  que además pidió formalizar la metodología (trabajar el PR, push, `gh pr
  create`, esperar) — quedó en `CLAUDE.md`. PR-06 ya está mergeado a `main`
  (PR #7), así que la rama `pr-07-segmentador` sale de `main` limpio.
- **El total no da: 133 fallos vs. 126.** No lo forcé; el test fija 133 como
  regresión. La diferencia:
  - PR-06 ya medía 129 carátulas en el índice, no 126 (hipótesis: entradas de
    referencia cruzada, p. ej. `Haras El Moro SA s/ queja ... en Carol ...:
    p. 716`, que tienen su propia página pero pueden no ser un fallo distinto).
  - Las 3 carátulas multi-fallo suman 4 fallos más (129 → 133).
  - **A confirmar con Kevin.** PR-08/PR-09 (metadatos y secciones), al abrir cada
    fallo y buscar su fecha/jueces, van a decir cuáles de los 133 rangos no
    tienen un fallo de verdad adentro.
- **Cobertura 1 → 956, no 1 → 953.** El "953" del plan es la última entrada
  "normal" del índice (`AFIP c/ Organización ...: p. 953`). La 3ª referencia de
  Tabacalera (p. 955) y las páginas de cuerpo hasta la 956 son el delta. 955 es
  una página oficial válida del tomo (el cuerpo llega a 956).
- **`clean._es_versalita` renombrada a `es_versalita`** (pública). Toca código de
  PR-05; sin cambio de comportamiento.
- **`CLAUDE.md` / memoria** editados por la metodología nueva (arriba).

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check . --output-format=concise   # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .                  # -> 35 files already formatted
./.venv/Scripts/python.exe -m pytest -q                    # -> 145 passed, 4 deselected (~18 s)
./.venv/Scripts/python.exe -m pytest -q -m slow            # -> 4 passed (~10 min, usa data/tomos/348.pdf)
```

Medición de aceptación a mano:

```
./.venv/Scripts/python.exe -m spectre.cli pdf segment data/tomos/348.pdf
# método           indice
# fallos           133
# cobertura        página 1 a 956
# solapamientos    0
# huecos           0
# fallo más largo  57 páginas
# mediana          4 páginas
```

Sobre `tomo348_indice.pdf` (tiene el índice entero + 1 página de cuerpo, oficial
956): mismos números — 133, cobertura (1, 956), más largo 57, mediana 4.

Fallback sobre `tomo348_cuerpo_p189-246.pdf`:

```
./.venv/Scripts/python.exe -m spectre.cli pdf segment tests/fixtures/tomo348_cuerpo_p189-246.pdf
# método           delimitadores  (dudosa)
# fallos           2
# cobertura        página 189 a 246
# fallo más largo  57 páginas      <- "Acevedo", 189-245, sin partir
```

## Dudas que quedaron

- **126 (plan) vs. 133 (medido).** La estructura (más largo 57, mediana 4) da
  exacta, así que el método está bien. El conteo arrastra el gap de PR-06.
  Confirmar con Kevin; PR-08/09 deberían cerrarlo.
- **Carátulas del Plan B en versalita a medias.** `limpiar` capitaliza palabra
  por palabra, así que `acEvEdo, Eva maRía c/ manuFactuRa tExtiL san justo s/
  quiEbRa` sale `Acevedo, Eva María c/ Manufactura Textil san justo s/ Quiebra`
  (las palabras que en el PDF van en minúscula quedan en minúscula). Es cosmético
  y solo afecta al fallback; la carátula canónica es la del índice. PR-08, que va
  a comparar la carátula del índice con la del encabezado del fallo, puede
  reconciliarlas.
- **El Plan B podría sobre-partir en un tomo real sin índice.** No lo pude medir
  (el único fixture grande, el Tomo 348, sí tiene índice). Si una página arranca
  citando un fallo ajeno en versalita con `c/`, el fallback lo tomaría como
  inicio. Por eso el resultado va marcado `dudosa` y R-2 dice indexar a nivel
  página en ese caso. El primer tomo sin índice entra como fixture de regresión.
- **`_LINEAS_CABEZA = 8`** es generoso para saltar el encabezado + la cola del
  fallo anterior en la misma página (caso "Favero", carátula en la línea 5).
  Calibrado al Tomo 348.
