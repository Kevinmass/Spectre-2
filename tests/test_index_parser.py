"""PR-06 — parser del índice por nombres de las partes.

Criterio de aceptación (plan §6): 126 entradas en el Tomo 348, con las páginas
dentro del rango. **Medido: 129 carátulas / 133 referencias de página** (3
carátulas aparecen en varios fallos: `ps. N y M`). La diferencia con el 126 del
plan queda anotada en `docs/qa/bitacora-PR-06.md`; los tests fijan el número
medido y sirven de regresión.

El grueso corre sobre `tests/fixtures/tomo348_indice.pdf` (pdf_page 962–968 del
tomo: última página de cuerpo + las 5 del índice de partes + el índice general).
`test_aceptacion_*` repite sobre `data/tomos/348.pdf` completo (no versionado) y
verifica que `localizar` encuentre la sección entre las 968 páginas.
"""

from pathlib import Path

import pdfplumber
import pytest

from spectre.corpus.fallo import (
    EntradaIndice,
    analizar_indice,
    localizar_indice_partes,
    parsear_indice,
)
from spectre.corpus.fallo.index_parser import _parsear_columna

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_indice.pdf"
TOMO_348 = Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf"

CARATULAS_348 = 129
REFERENCIAS_348 = 133


# --- _parsear_columna: la lógica de armado de entradas ---------------- #


def test_entrada_de_una_linea():
    ent = _parsear_columna(["Baez, Diego c/ Asociart ART S.A. s/ accidente: p. 165"])
    assert ent == [
        EntradaIndice("Baez, Diego c/ Asociart ART S.A. s/ accidente", (165,))
    ]


def test_caratula_en_varias_lineas():
    ent = _parsear_columna(
        [
            "Aeropuertos Argentina 2000 S.A. c/ Comuna",
            "de Delfín Gallo y otro s/ contencioso",
            "administrativo – varios: p. 276",
        ]
    )
    assert len(ent) == 1
    assert ent[0].caratula == (
        "Aeropuertos Argentina 2000 S.A. c/ Comuna de Delfín Gallo y otro "
        "s/ contencioso administrativo – varios"
    )
    assert ent[0].paginas == (276,)


def test_numero_de_pagina_en_el_renglon_siguiente():
    ent = _parsear_columna(
        [
            "Blindaje Seguridad SRL c/ Ponce de León,",
            "Alejandro y otro s/ daños y perjuicios: p.",
            "274",
        ]
    )
    assert ent[0].paginas == (274,)
    assert "p." not in ent[0].caratula


def test_partes_en_varios_fallos_ps_n_y_m():
    ent = _parsear_columna(
        ["Fernández de Kirchner y otros s/ incidente.: ps. 443 y 494"]
    )
    assert ent[0].paginas == (443, 494)


def test_partes_en_varios_fallos_sin_espacio():
    ent = _parsear_columna(["Ferrari c/ Levinas s/ Incidente: ps.43 y 45"])
    assert ent[0].paginas == (43, 45)


def test_cola_de_lista_larga_en_renglon_aparte():
    ent = _parsear_columna(
        [
            "Tabacalera Sarandí S.A. c/ EN - AFIP - DGI s/",
            "proceso de conocimiento: ps. 569, 841",
            "y 955",
        ]
    )
    assert len(ent) == 1
    assert ent[0].paginas == (569, 841, 955)


def test_letra_divisora_del_abecedario_se_descarta():
    ent = _parsear_columna(["A", "Acevedo, Eva María s/ quiebra: p. 189"])
    assert ent == [EntradaIndice("Acevedo, Eva María s/ quiebra", (189,))]


def test_dos_letras_divisoras_juntas_se_descartan():
    ent = _parsear_columna(["N R", "R., J. A. c/ R., M. A. s/ sumarísimo: p. 329"])
    assert [e.caratula for e in ent] == ["R., J. A. c/ R., M. A. s/ sumarísimo"]


def test_fragmento_de_encabezado_al_tope_se_descarta():
    ent = _parsear_columna(
        [
            "E LAS PARTES (i)",
            "MBRES DE LAS PARTES",
            "Baez, Diego Jesús c/ Asociart s/ accidente: p. 165",
        ]
    )
    assert len(ent) == 1
    assert ent[0].caratula.startswith("Baez")


def test_la_palabra_partes_en_una_caratula_no_se_descarta():
    # El filtro de encabezado solo mira las 2 primeras líneas útiles.
    ent = _parsear_columna(
        ["A", "B", "Fulano c/ Estado s/ división de partes comunes: p. 50"]
    )
    assert ent[0].caratula == "Fulano c/ Estado s/ división de partes comunes"
    assert ent[0].paginas == (50,)


def test_columna_sin_referencias_no_produce_entradas():
    assert _parsear_columna(["texto suelto sin cita", "otra línea"]) == []


# --- localizar_indice_partes ------------------------------------------ #


def test_localiza_la_seccion_en_el_fixture():
    with pdfplumber.open(FIXTURE) as pdf:
        rango = localizar_indice_partes(pdf)
    # fixture: idx 0 = cuerpo, 1..5 = índice de partes, 6 = índice general
    assert list(rango) == [1, 2, 3, 4, 5]


def test_no_confunde_el_indice_general_con_el_de_partes():
    # La última página del fixture es el ÍNDICE GENERAL, que termina con la
    # entrada de tabla de contenidos "Indice por los nombres de las partes (i)".
    with pdfplumber.open(FIXTURE) as pdf:
        rango = localizar_indice_partes(pdf)
        ultima = pdf.pages[rango.stop].extract_text()
    assert "INDICE GENERAL" in ultima


def test_falla_ruidoso_si_no_hay_indice_de_partes():
    otro = Path(__file__).parent / "fixtures" / "tomo348_p1-16.pdf"
    with (
        pdfplumber.open(otro) as pdf,
        pytest.raises(ValueError, match="NOMBRES DE LAS PARTES"),
    ):
        localizar_indice_partes(pdf)


def test_archivo_inexistente_es_ruidoso(tmp_path):
    with pytest.raises(FileNotFoundError):
        parsear_indice(tmp_path / "no_esta.pdf")


# --- parsear_indice / analizar_indice sobre el fixture --------------- #


@pytest.fixture(scope="module")
def resumen():
    return analizar_indice(FIXTURE)


def test_cuenta_de_caratulas_y_referencias(resumen):
    assert resumen.caratulas == CARATULAS_348
    assert resumen.referencias == REFERENCIAS_348


def test_paginas_del_indice(resumen):
    assert resumen.paginas_indice == (2, 6)  # pdf_page del fixture


def test_paginas_citadas_dentro_del_rango_del_tomo(resumen):
    citadas = resumen.paginas_citadas
    assert min(citadas) == 1
    assert max(citadas) == 955  # 3ª referencia de Tabacalera; el tomo llega a 956
    assert all(p >= 1 for p in citadas)


def test_entradas_ancla_conocidas(resumen):
    def buscar(prefijo: str) -> EntradaIndice:
        return next(e for e in resumen.entradas if e.caratula.startswith(prefijo))

    # el ejemplo textual de la decisión D-2 del plan
    assert buscar("Zárate, Pablo").paginas == (380,)
    # primera y última página del rango que cubre el índice
    assert buscar("Raskovsky, Luis Ernesto").paginas == (1,)
    assert buscar("AFIP c/ Organización").paginas == (953,)


def test_caratulas_multi_fallo(resumen):
    multi = {e.caratula: e.paginas for e in resumen.entradas if len(e.paginas) > 1}
    assert len(multi) == 3
    assert multi["Ferrari, María Alicia c/ Levinas, Gabriel Isaías s/ Incidente"] == (
        43,
        45,
    )
    tab = next(v for k, v in multi.items() if k.startswith("Tabacalera Sarandí"))
    assert tab == (569, 841, 955)


def test_parsear_indice_devuelve_la_lista_plana(resumen):
    lista = parsear_indice(FIXTURE)
    assert lista == list(resumen.entradas)
    assert all(isinstance(e, EntradaIndice) for e in lista)


# --- aceptación: el Tomo 348 completo ------------------------------- #


@pytest.mark.slow
@pytest.mark.skipif(
    not TOMO_348.is_file(),
    reason="falta data/tomos/348.pdf (fixture real de 968 páginas, no versionado)",
)
def test_aceptacion_tomo_348():
    r = analizar_indice(TOMO_348)
    assert r.paginas_indice == (963, 967)  # localiza la sección entre 968 páginas
    assert r.caratulas == CARATULAS_348
    assert r.referencias == REFERENCIAS_348
    citadas = r.paginas_citadas
    assert (min(citadas), max(citadas)) == (1, 955)
