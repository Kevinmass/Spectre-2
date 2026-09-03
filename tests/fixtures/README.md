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
