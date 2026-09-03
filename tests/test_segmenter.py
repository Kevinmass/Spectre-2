"""PR-07 — segmentador de fallos.

Criterio de aceptación (plan §6): 126 fallos en el Tomo 348, sin solapamientos,
cubriendo de la página 1 a la 953; el fallo más largo son 57 páginas (legítimo,
el fallback no debe partirlo) y la mediana 4.

**Medido:** 133 fallos (las 129 carátulas del índice, con 3 que figuran en
varios fallos), cobertura 1→956, 0 solapamientos, **más largo 57** y **mediana
4** — los dos números de estructura del plan dan exactos; la diferencia en el
total (126 vs 133) viene de PR-06 y queda anotada en `bitacora-PR-07.md`.

`test_fallback_no_parte_el_fallo_largo` corre el Plan B sobre 6 páginas reales
del Tomo 348 (inicio de "Acevedo", 4 páginas de su interior, inicio de "Favero")
y verifica que el fallback no mete un corte dentro del fallo de 57 páginas.
"""

from pathlib import Path

import pytest

from spectre.corpus.fallo import (
    EntradaIndice,
    FalloSegmentado,
    ResumenSegmentacion,
    parsear_indice,
    segmentar,
    segmentar_desde_indice,
    segmentar_por_delimitadores,
)
from spectre.corpus.pdf import PaginaTexto, extraer_texto

FIXTURE_CUERPO = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p189-246.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"


# --- segmentar_desde_indice ---------------------------------------- #


def _ent(caratula, *paginas):
    return EntradaIndice(caratula, tuple(paginas))


def test_rangos_desde_el_indice():
    fallos = segmentar_desde_indice(
        [_ent("A c/ B s/ x", 1), _ent("C c/ D s/ y", 21), _ent("E c/ F s/ z", 31)],
        tomo_numero=348,
        pagina_fin_cuerpo=40,
    )
    assert [(f.cita, f.pagina_inicio, f.pagina_fin) for f in fallos] == [
        ("348:1", 1, 20),
        ("348:21", 21, 30),
        ("348:31", 31, 40),
    ]
    assert fallos[0].paginas == 20


def test_caratula_multi_fallo_se_explota():
    fallos = segmentar_desde_indice(
        [_ent("Uno c/ Dos s/ x", 10), _ent("Kirchner s/ incidente", 20, 50)],
        tomo_numero=348,
        pagina_fin_cuerpo=90,
    )
    assert [f.cita for f in fallos] == ["348:10", "348:20", "348:50"]
    assert [f.caratula for f in fallos] == [
        "Uno c/ Dos s/ x",
        "Kirchner s/ incidente",
        "Kirchner s/ incidente",
    ]


def test_paginas_de_inicio_repetidas_es_ruidoso():
    with pytest.raises(ValueError, match="repetidas"):
        segmentar_desde_indice(
            [_ent("A c/ B s/ x", 5), _ent("C c/ D s/ y", 5)],
            tomo_numero=348,
            pagina_fin_cuerpo=50,
        )


def test_indice_cita_mas_alla_del_cuerpo_es_ruidoso():
    with pytest.raises(ValueError, match="termina en"):
        segmentar_desde_indice(
            [_ent("A c/ B s/ x", 1), _ent("C c/ D s/ y", 99)],
            tomo_numero=348,
            pagina_fin_cuerpo=50,
        )


def test_sin_entradas_es_ruidoso():
    with pytest.raises(ValueError, match="no hay entradas"):
        segmentar_desde_indice([], tomo_numero=348, pagina_fin_cuerpo=50)


# --- segmentar_por_delimitadores (Plan B) -------------------------- #


def _pag(pdf_page, oficial, *lineas):
    return PaginaTexto(
        pdf_page=pdf_page, texto="\n".join(lineas), pagina_oficial=oficial
    )


CARATULA_A = "gómEz, juan c/ EstAdo nacionAL s/ amparo"
CARATULA_B = "PéREz, anA c/ obRA sociAL s/ despido"


def test_detecta_un_fallo_por_caratula_en_versalita():
    paginas = [
        _pag(1, 1, "DE JUSTICIA DE LA NACIÓN 1", "348", CARATULA_A, "AMPARO", "cuerpo"),
        _pag(2, 2, "2 FALLOS DE LA CORTE SUPREMA", "348", "más cuerpo del fallo"),
        _pag(3, 3, "DE JUSTICIA DE LA NACIÓN 3", "348", CARATULA_B, "DESPIDO", "texto"),
    ]
    fallos = segmentar_por_delimitadores(paginas, tomo_numero=348, pagina_fin_cuerpo=3)
    assert [f.cita for f in fallos] == ["348:1", "348:3"]
    assert fallos[0].pagina_fin == 2  # el primero llega hasta antes del segundo
    assert all(f.metodo == "delimitadores" for f in fallos)


def test_no_corta_por_fallo_de_la_corte_ni_autos_y_vistos():
    # Páginas interiores con delimitadores de texto pero sin carátula: un fallo.
    paginas = [
        _pag(1, 1, "DE JUSTICIA DE LA NACIÓN 1", "348", CARATULA_A, "AMPARO"),
        _pag(2, 2, "2 FALLOS DE LA CORTE SUPREMA", "348", "-I-", "Suprema Corte:"),
        _pag(3, 3, "DE JUSTICIA DE LA NACIÓN 3", "348", "FALLO DE LA CORTE SUPREMA"),
        _pag(
            4,
            4,
            "4 FALLOS DE LA CORTE SUPREMA",
            "348",
            "Buenos Aires, 3 de marzo de 2025.",
        ),
        _pag(
            5, 5, "DE JUSTICIA DE LA NACIÓN 5", "348", "Autos y Vistos; Considerando:"
        ),
    ]
    fallos = segmentar_por_delimitadores(paginas, tomo_numero=348, pagina_fin_cuerpo=5)
    assert len(fallos) == 1
    assert (fallos[0].pagina_inicio, fallos[0].pagina_fin) == (1, 5)


def test_sin_ninguna_caratula_es_ruidoso():
    paginas = [_pag(1, 1, "DE JUSTICIA DE LA NACIÓN 1", "348", "puro cuerpo")]
    with pytest.raises(ValueError, match="ninguna carátula"):
        segmentar_por_delimitadores(paginas, tomo_numero=348, pagina_fin_cuerpo=1)


def test_fallback_no_parte_el_fallo_largo():
    # 6 páginas reales: inicio de "Acevedo" (oficial 189), 4 de su interior
    # (190, 199, 244, 245) e inicio de "Favero" (246). El fallo de 57 páginas
    # no se parte: solo 189 y 246 traen carátula.
    paginas = extraer_texto(FIXTURE_CUERPO)
    fallos = segmentar_por_delimitadores(
        paginas, tomo_numero=348, pagina_fin_cuerpo=246
    )
    assert [f.cita for f in fallos] == ["348:189", "348:246"]
    assert fallos[0].pagina_inicio == 189
    assert fallos[0].pagina_fin == 245
    assert fallos[0].paginas == 57
    assert fallos[0].caratula.startswith("Acevedo, Eva María c/ Manufactura Textil")


# --- ResumenSegmentacion: métricas ------------------------------- #


def _resumen(*tramos):
    fallos = tuple(
        FalloSegmentado(f"f{i}", f"348:{a}", a, b, "indice")
        for i, (a, b) in enumerate(tramos)
    )
    return ResumenSegmentacion(fallos, "indice", dudosa=False)


def test_metricas_del_resumen():
    r = _resumen((1, 10), (11, 12), (13, 20), (21, 21))
    assert r.cantidad == 4
    assert r.cobertura == (1, 21)
    assert r.solapamientos == ()
    assert r.huecos == ()
    assert r.pagina_mas_larga == 10  # el tramo 1-10
    assert r.mediana_paginas == 5  # [10, 2, 8, 1] -> ordenado [1,2,8,10] -> 5


def test_resumen_detecta_solapamiento_y_hueco():
    r = _resumen((1, 10), (8, 15), (30, 40))
    assert r.solapamientos == (("348:1", "348:8"),)
    assert r.huecos == ((15, 30),)


# --- aceptación: el Tomo 348 completo --------------------------- #


@pytest.mark.slow
@pytest.mark.skipif(
    not TOMO_348.is_file(),
    reason="falta data/tomos/348.pdf (fixture real de 968 páginas, no versionado)",
)
def test_aceptacion_tomo_348():
    entradas = parsear_indice(TOMO_348)
    paginas = extraer_texto(TOMO_348)
    r = segmentar(entradas, paginas, tomo_numero=348)

    assert r.metodo == "indice"
    assert not r.dudosa
    assert r.cantidad == 133  # plan: 126 (ver bitácora); estructura abajo da exacto
    assert r.solapamientos == ()
    assert r.cobertura == (1, 956)  # plan: "1 a 953"; última ref del índice: 955
    assert r.pagina_mas_larga == 57  # plan exacto
    assert r.mediana_paginas == 4  # plan exacto

    por_cita = {f.cita: f for f in r.fallos}
    assert por_cita["348:1"].caratula.startswith("Raskovsky, Luis Ernesto c/ Perrone")
    assert por_cita["348:189"].paginas == 57  # "Acevedo ... s/ quiebra"
