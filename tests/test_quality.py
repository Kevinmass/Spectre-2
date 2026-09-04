"""PR-18 — sonda de calidad: caracteres por página, digital vs requiere_ocr
(D-10 del plan).

Criterio de aceptación (plan §6): el Tomo 348 clasifica `digital`; un tomo
anterior a 1950 clasifica `requiere_ocr` y **no** se indexa como si estuviera
vacío. La mitad del criterio se mide contra el tomo real en
`test_aceptacion_tomo_348` (marca `slow`, necesita `data/tomos/348.pdf`). La
otra mitad —un escaneo real de antes de 1950— necesita bajarlo del sitio de la
CSJN, y esta sesión no tuvo acceso de red (`sjservicios.csjn.gov.ar` no
respondió: ver `spectre/corpus/pdf/quality.py`). Se prueba en cambio con una
lista de `PaginaTexto` fabricada a mano que reproduce la forma exacta de un
escaneo sin OCR (texto vacío o casi en casi todas las páginas) — mismo tipo de
objeto que consume `medir_calidad`, así que el camino de código es el mismo
que correría sobre un PDF real. Pendiente: repetir con un tomo real de la
CSJN cuando haya red (ver bitácora PR-18).
"""

from pathlib import Path

import pytest

from spectre.corpus.pdf import PaginaTexto, extraer_texto, medir_calidad
from spectre.corpus.pdf.quality import ResultadoCalidad

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"


@pytest.fixture(scope="session")
def paginas():
    return extraer_texto(FIXTURE)


# --- medir_calidad sobre listas fabricadas -------------------------------- #


def test_tomo_con_texto_clasifica_digital():
    paginas = [PaginaTexto(i, "palabra " * 500, i) for i in range(1, 51)]
    r = medir_calidad(paginas)
    assert isinstance(r, ResultadoCalidad)
    assert r.calidad == "digital"
    assert r.total == 50
    assert r.con_texto == 50
    assert r.cobertura == 1.0


def test_escaneo_sin_capa_de_texto_clasifica_requiere_ocr():
    # Forma real de un escaneo sin OCR: extract_text() da "" en casi todas las
    # páginas (pdfplumber no tiene de dónde sacar texto de una imagen).
    paginas = [PaginaTexto(i, "", None) for i in range(1, 201)]
    r = medir_calidad(paginas)
    assert r.calidad == "requiere_ocr"
    assert r.con_texto == 0
    assert r.cobertura == 0.0
    assert r.caracteres_totales == 0


def test_escaneo_con_alguna_pagina_de_portada_digital_sigue_siendo_ocr():
    # Ni siquiera un puñado de páginas con texto real (portada, alguna hoja
    # suelta escaneada + OCR de baja calidad) alcanza si el grueso del tomo
    # está vacío.
    paginas = [PaginaTexto(1, "TOMO 5 - AÑO 1901", None)]
    paginas += [PaginaTexto(i, "", None) for i in range(2, 301)]
    r = medir_calidad(paginas)
    assert r.calidad == "requiere_ocr"


def test_tomo_a_mitad_de_camino_no_llega_a_digital():
    # Cobertura exactamente en el borde: la mitad de las páginas sin texto
    # aprovechable no es "casi todo digital", es un tomo dudoso, y el umbral
    # (D-05) no lo redondea para arriba.
    paginas = [PaginaTexto(i, "palabra " * 500, i) for i in range(1, 6)]
    paginas += [PaginaTexto(i, "", None) for i in range(6, 12)]
    r = medir_calidad(paginas)
    assert r.cobertura < 0.5
    assert r.calidad == "requiere_ocr"


def test_sin_paginas_es_ruidoso():
    with pytest.raises(ValueError):
        medir_calidad([])


def test_caracteres_por_pagina_es_el_promedio():
    paginas = [
        PaginaTexto(1, "a" * 1000, 1),
        PaginaTexto(2, "a" * 2000, 2),
        PaginaTexto(3, "a" * 3000, 3),
    ]
    r = medir_calidad(paginas)
    assert r.caracteres_totales == 6000
    assert r.caracteres_por_pagina == pytest.approx(2000.0)


# --- sobre el recorte real del Tomo 348 ----------------------------------- #


def test_recorte_real_clasifica_digital(paginas):
    r = medir_calidad(paginas)
    assert r.calidad == "digital"
    assert r.total == 16
    # las 6 páginas de portada/índice del recorte bajan la cobertura, pero no
    # tanto como para cruzar el umbral.
    assert r.cobertura > 0.5


# --- aceptación: el Tomo 348 completo -------------------------------------- #


@pytest.mark.slow
@pytest.mark.skipif(
    not TOMO_348.is_file(),
    reason="falta data/tomos/348.pdf (fixture real de 968 páginas, no versionado)",
)
def test_aceptacion_tomo_348():
    paginas = extraer_texto(TOMO_348)
    r = medir_calidad(paginas)
    assert r.calidad == "digital"
    assert r.total == 968
    # medido: mediana 2.335 caracteres/página, solo 6/968 páginas (0,6%) por
    # debajo del umbral de 200 caracteres.
    assert r.cobertura >= 0.99
