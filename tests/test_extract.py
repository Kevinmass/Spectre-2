"""PR-04 — extracción de texto por página y paginación oficial.

Criterio de aceptación (plan §6): sobre el Tomo 348, ≥95% de páginas con número
detectado y un único offset (el valor medido es 6). Eso se mide en
`test_aceptacion_tomo_348`, que necesita `data/tomos/348.pdf` (no versionado) y
se saltea si no está. El resto corre contra `tests/fixtures/tomo348_p1-16.pdf`,
un recorte de 16 páginas reales.
"""

from pathlib import Path

import pytest

from spectre.corpus.pdf import (
    PaginaTexto,
    calcular_offset,
    detectar_pagina_oficial,
    extraer_texto,
    persistir,
)
from spectre.db import Repo, connect, migrate

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"


@pytest.fixture(scope="session")
def paginas():
    return extraer_texto(FIXTURE)


@pytest.fixture
def repo(tmp_path):
    c = connect(tmp_path / "spectre.db")
    migrate(c)
    yield Repo(c)
    c.close()


# --- detectar_pagina_oficial ---------------------------------------- #


def test_detecta_encabezado_de_pagina_impar():
    assert (
        detectar_pagina_oficial("DE JUSTICIA DE LA NACIÓN 15\n348\nConsiderando:") == 15
    )


def test_detecta_encabezado_de_pagina_par():
    assert detectar_pagina_oficial("42 FALLOS DE LA CORTE SUPREMA\n348\ntexto") == 42


def test_sin_encabezado_devuelve_none():
    assert (
        detectar_pagina_oficial("Considerando que la cuestión federal\nfue mal") is None
    )


def test_solo_mira_las_primeras_lineas():
    texto = "\n".join(["linea", "otra", "mas", "DE JUSTICIA DE LA NACIÓN 15"])
    assert detectar_pagina_oficial(texto) is None


def test_ignora_numeros_disparatados():
    assert detectar_pagina_oficial("DE JUSTICIA DE LA NACIÓN 99999\n348") is None


def test_ignora_pagina_cero():
    assert detectar_pagina_oficial("0 FALLOS DE LA CORTE SUPREMA\n348") is None


def test_texto_vacio_devuelve_none():
    assert detectar_pagina_oficial("") is None


# --- extraer_texto sobre el recorte real -------------------------------- #


def test_extrae_las_16_paginas(paginas):
    assert [p.pdf_page for p in paginas] == list(range(1, 17))
    assert all(isinstance(p, PaginaTexto) for p in paginas)


def test_portada_sin_numero_cuerpo_con_numero(paginas):
    por_pdf_page = {p.pdf_page: p.pagina_oficial for p in paginas}
    assert [por_pdf_page[i] for i in range(1, 7)] == [None] * 6
    assert [por_pdf_page[i] for i in range(7, 17)] == list(range(1, 11))


def test_texto_crudo_se_conserva(paginas):
    p7 = next(p for p in paginas if p.pdf_page == 7)
    assert "DE JUSTICIA DE LA NACIÓN" in p7.texto  # acento real, sin mojibake
    assert p7.texto == p7.texto  # es str, no bytes


def test_archivo_inexistente_es_ruidoso(tmp_path):
    with pytest.raises(FileNotFoundError):
        extraer_texto(tmp_path / "no_esta.pdf")


# --- calcular_offset ------------------------------------------------ #


def test_offset_del_recorte(paginas):
    r = calcular_offset(paginas)
    assert r.offset == 6
    assert r.total == 16
    assert r.detectadas == 10
    assert r.consistentes == 10
    assert r.discrepancias == ()
    assert r.cobertura == pytest.approx(10 / 16)
    assert r.consistencia == pytest.approx(1.0)


def test_offset_sin_ninguna_deteccion():
    sin_numero = [PaginaTexto(i, "x", None) for i in range(1, 6)]
    r = calcular_offset(sin_numero)
    assert r.offset is None
    assert r.total == 5
    assert r.detectadas == 0
    assert r.cobertura == 0.0
    assert r.consistencia == 0.0


def test_offset_marca_discrepancias():
    filas = [
        PaginaTexto(7, "", 1),  # offset 6
        PaginaTexto(8, "", 2),  # offset 6
        PaginaTexto(9, "", 2),  # offset 7  <- discrepa
        PaginaTexto(10, "", 4),  # offset 6
    ]
    r = calcular_offset(filas)
    assert r.offset == 6
    assert r.detectadas == 4
    assert r.consistentes == 3
    assert r.discrepancias == (9,)


# --- persistir ---------------------------------------------------------- #


def test_persistir_vuelca_paginas_y_actualiza_el_tomo(repo, paginas):
    tomo_id = repo.insert_tomo(348)
    persistir(repo, tomo_id, paginas, calcular_offset(paginas))

    assert repo.contar_paginas(tomo_id) == 16
    p7 = repo.get_pagina(tomo_id, 7)
    assert p7.pagina_oficial == 1
    assert "DE JUSTICIA DE LA NACIÓN" in p7.texto_crudo
    assert p7.texto_limpio is None  # lo completa PR-05

    tomo = repo.get_tomo(tomo_id)
    assert tomo.paginas == 16
    assert tomo.offset_pagina == 6


def test_persistir_reemplaza_no_acumula(repo, paginas):
    tomo_id = repo.insert_tomo(348)
    r = calcular_offset(paginas)
    persistir(repo, tomo_id, paginas, r)
    persistir(repo, tomo_id, paginas, r)
    assert repo.contar_paginas(tomo_id) == 16


# --- aceptación: el Tomo 348 completo ------------------------------- #


@pytest.mark.slow
@pytest.mark.skipif(
    not TOMO_348.is_file(),
    reason="falta data/tomos/348.pdf (fixture real de 968 páginas, no versionado)",
)
def test_aceptacion_tomo_348():
    paginas = extraer_texto(TOMO_348)
    assert len(paginas) == 968

    r = calcular_offset(paginas)
    assert r.offset == 6
    assert r.cobertura >= 0.95  # medido: 956/968 = 98.76%
    assert r.consistencia == 1.0  # medido: 956/956
    assert r.discrepancias == ()
