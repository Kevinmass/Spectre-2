# Fixtures de tests

## `tomo348_p1-16.pdf`

Las primeras 16 páginas del Tomo 348 de Fallos de la CSJN
(`data/tomos/348.pdf`, no versionado). Publicación oficial de dominio público.

- pdf_page 1–6: portada e índice de consulta — sin número de página oficial.
- pdf_page 7–16: cuerpo, páginas oficiales 1–10 (encabezado impar y par),
  offset 6.

Sirve para probar `spectre.corpus.pdf.extract` sin depender del PDF completo
(968 páginas, 3 MB). Los números de aceptación del plan (≥95 % de páginas con
número, offset único 6) se miden sobre el tomo entero en
`test_extract.py::test_aceptacion_tomo_348`, que se saltea si el archivo no está.

Regenerar (con el tomo completo en `data/tomos/348.pdf`):

```python
from pypdf import PdfReader, PdfWriter

r = PdfReader("data/tomos/348.pdf")
w = PdfWriter()
for i in range(16):
    w.add_page(r.pages[i])
with open("tests/fixtures/tomo348_p1-16.pdf", "wb") as f:
    w.write(f)
```

## `tomo348_indice.pdf`

Las páginas `pdf_page` 962–968 del Tomo 348: la última página del cuerpo, las
5 del **ÍNDICE POR LOS NOMBRES DE LAS PARTES** (963–967) y el índice general
(968). Sirve para probar `spectre.corpus.fallo.index_parser` —localización de la
sección y parseo de carátula → página— sin el PDF completo.

Medido sobre estas páginas: 129 carátulas, 133 referencias de página (3
carátulas aparecen en varios fallos). `test_index_parser.py::test_aceptacion_*`
repite sobre el tomo entero.

Regenerar:

```python
from pypdf import PdfReader, PdfWriter

r = PdfReader("data/tomos/348.pdf")
w = PdfWriter()
for i in range(961, 968):  # pdf_page 962..968
    w.add_page(r.pages[i])
with open("tests/fixtures/tomo348_indice.pdf", "wb") as f:
    w.write(f)
```

## `tomo348_cuerpo_p189-246.pdf`

Seis páginas **no contiguas** del Tomo 348, elegidas para probar el fallback por
delimitadores del segmentador (`spectre.corpus.fallo.segmenter`, PR-07):

- `pdf_page` 195 (oficial 189): inicio del fallo "Acevedo ... s/ quiebra", el más
  largo del tomo (57 páginas).
- `pdf_page` 196, 205, 250, 251 (oficiales 190, 199, 244, 245): interior de ese
  mismo fallo — traen `Fallos:` citados, `FALLO DE LA CORTE`, etc., pero **no**
  carátula.
- `pdf_page` 252 (oficial 246): inicio del fallo siguiente ("Favero ...").

El fallback tiene que ver dos inicios (189 y 246) y no meter ningún corte en el
medio. Regenerar:

```python
from pypdf import PdfReader, PdfWriter

r = PdfReader("data/tomos/348.pdf")
w = PdfWriter()
for pp in (195, 196, 205, 250, 251, 252):
    w.add_page(r.pages[pp - 1])
with open("tests/fixtures/tomo348_cuerpo_p189-246.pdf", "wb") as f:
    w.write(f)
```
