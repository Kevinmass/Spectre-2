"""PR-05 — limpieza de texto: encabezados, des-hifenado, versalitas.

Criterio de aceptación (plan §6): casos reales del Tomo 348; el conteo de
palabras baja ~4,5% al des-hifenar una muestra. La muestra grande (el cuerpo
entero) se mide en `test_aceptacion_dehifenado_tomo_348` (marca `slow`,
necesita `data/tomos/348.pdf`).
"""

from pathlib import Path

import pytest

from spectre.corpus.pdf import (
    contar_palabras,
    extraer_texto,
    limpiar,
    limpiar_tomo,
)
from spectre.corpus.pdf.clean import (
    _normalizar_versalitas,
    _sin_encabezado,
    _unir_guiones,
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


# --- encabezados repetidos ---------------------------------------- #


def test_saca_encabezado_de_pagina_impar():
    t = "DE JUSTICIA DE LA NACIÓN 15\n348\nConsiderando que la cuestión"
    assert _sin_encabezado(t) == "Considerando que la cuestión"


def test_saca_encabezado_de_pagina_par():
    t = "14 FALLOS DE LA CORTE SUPREMA\n348\nEl recurso extraordinario"
    assert _sin_encabezado(t) == "El recurso extraordinario"


def test_saca_encabezado_apilado_de_inicio_de_mes():
    # pdf_page 7 del Tomo 348: los dos encabezados + el nombre suelto.
    t = (
        "DE JUSTICIA DE LA NACIÓN 1\n348\n"
        "FALLOS DE LA CORTE SUPREMA\nFEBRERO\nRaskovsky"
    )
    assert _sin_encabezado(t) == "FEBRERO\nRaskovsky"  # el mes NO es encabezado


def test_no_toca_el_cuerpo_sin_encabezado():
    t = "Considerando:\n1º) Que los antecedentes de la causa"
    assert _sin_encabezado(t) == t


def test_no_come_mas_de_cuatro_lineas():
    t = "348\n348\n348\n348\n348\nde verdad esto es cuerpo"
    # 5 líneas de "348": se sacan 4, la quinta queda aunque parezca encabezado.
    assert _sin_encabezado(t) == "348\nde verdad esto es cuerpo"


# --- des-hifenado ------------------------------------------------- #


def test_une_palabra_cortada():
    assert _unir_guiones("consti-\ntuya") == "constituya"


def test_une_con_espacios_alrededor_del_guion():
    # el ejemplo textual del plan
    assert _unir_guiones("rese -\nñados") == "reseñados"


def test_une_a_traves_de_varias_lineas():
    t = "El recurso extraordi-\nnario ha sido bien conce-\ndido"
    assert _unir_guiones(t) == "El recurso extraordinario ha sido bien concedido"


def test_no_une_marcador_de_seccion():
    assert _unir_guiones("-I-\nLa Sala E de la Cámara") == "-I-\nLa Sala E de la Cámara"


def test_no_une_si_sigue_en_mayuscula():
    assert _unir_guiones("Banco-\nNación") == "Banco-\nNación"


def test_no_une_guion_que_no_esta_a_fin_de_linea():
    assert _unir_guiones("bien de familia - régimen") == "bien de familia - régimen"
    assert _unir_guiones("art. 14 bis-ter de la ley") == "art. 14 bis-ter de la ley"


# --- versalitas ------------------------------------------------------ #


def test_normaliza_caratula_real_del_tomo_348():
    # carátula del primer fallo, pdf_page 7
    cruda = "Raskovsky, Luis ERnEsto c/ PERRonE, GabRiELa aLEjandRa"
    assert (
        _normalizar_versalitas(cruda)
        == "Raskovsky, Luis Ernesto c/ Perrone, Gabriela Alejandra"
    )


def test_normaliza_nombre_de_juez():
    assert _normalizar_versalitas("caRLos FERnando RosEnkRantz") == (
        "Carlos Fernando Rosenkrantz"
    )


def test_no_toca_mayusculas_ni_capitalizado_ni_minusculas():
    t = "FALLOS DE LA CORTE SUPREMA Constitución Nacional artículo 14 bis"
    assert _normalizar_versalitas(t) == t


def test_no_toca_siglas_ni_numeros():
    t = "recurso FCB 22477/2014/CS1 ante la CSJN por el art. 14"
    assert _normalizar_versalitas(t) == t


# --- limpiar (todo junto) sobre el recorte real --------------------- #


def test_limpiar_pagina_real(paginas):
    import re

    p7 = next(p for p in paginas if p.pdf_page == 7)
    limpia = limpiar(p7.texto)

    assert not limpia.startswith("DE JUSTICIA")
    assert "348\nFALLOS DE LA CORTE SUPREMA" not in limpia
    assert limpia.startswith("FEBRERO")  # el mes se conserva
    assert "Luis Ernesto c/ Perrone, Gabriela Alejandra" in limpia
    assert "no concurre el requisito" in limpia  # "con-\ncurre" + "requisi-\nto"
    assert re.search(r"[a-záéíóúñ]-\n[a-z]", limpia) is None  # sin guiones de corte


def test_limpiar_es_idempotente(paginas):
    p = next(p for p in paginas if p.pdf_page == 13)
    una = limpiar(p.texto)
    assert limpiar(una) == una


def test_contar_palabras():
    assert contar_palabras("uno dos  tres\ncuatro") == 4
    assert contar_palabras("   ") == 0


def test_dehifenado_baja_el_conteo_en_el_recorte(paginas):
    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    crudas = sum(contar_palabras(_sin_encabezado(p.texto)) for p in cuerpo)
    limpias = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    assert limpias < crudas
    assert (crudas - limpias) / crudas > 0.02  # el recorte de portada da ~2,3%


# --- limpiar_tomo (persistencia) ------------------------------------ #


def test_limpiar_tomo_llena_texto_limpio(repo, paginas):
    from spectre.corpus.pdf import calcular_offset, persistir

    tomo_id = repo.insert_tomo(348)
    persistir(repo, tomo_id, paginas, calcular_offset(paginas))

    n = limpiar_tomo(repo, tomo_id)
    assert n == 16

    p7 = repo.get_pagina(tomo_id, 7)
    assert p7.texto_limpio is not None
    assert "Luis Ernesto c/ Perrone" in p7.texto_limpio
    assert not p7.texto_limpio.startswith("DE JUSTICIA")
    # el crudo queda intacto (D-8: los dos conviven)
    assert "DE JUSTICIA DE LA NACIÓN 1" in p7.texto_crudo


def test_limpiar_tomo_sin_paginas_es_ruidoso(repo):
    tomo_id = repo.insert_tomo(999)
    with pytest.raises(ValueError):
        limpiar_tomo(repo, tomo_id)


# --- aceptación: des-hifenado sobre el cuerpo entero -------------- #


@pytest.mark.slow
@pytest.mark.skipif(
    not TOMO_348.is_file(),
    reason="falta data/tomos/348.pdf (fixture real de 968 páginas, no versionado)",
)
def test_aceptacion_dehifenado_tomo_348():
    paginas = extraer_texto(TOMO_348)
    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    crudas = sum(contar_palabras(_sin_encabezado(p.texto)) for p in cuerpo)
    limpias = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    reduccion = (crudas - limpias) / crudas

    # El plan estima ~4,5%; medido con des-hifenado verificado como completo
    # (7.709 de 7.712 guiones unibles) da ~2,2%. Ver bitácora PR-05.
    assert 0.018 <= reduccion <= 0.028

    # Lo que importa aguas abajo: el cuerpo limpio queda cerca de las 332.999
    # palabras que el plan fija para PR-11.
    assert abs(limpias - 332_999) / 332_999 < 0.02
