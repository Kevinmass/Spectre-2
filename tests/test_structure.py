"""PR-08 — metadatos del fallo.

Criterio de aceptación (plan §6): ≥90% de los fallos del Tomo 348 con fecha y
jueces; los que fallan quedan marcados, no inventados.

**Medido (índice → segmentación → metadatos):**

| tomo | fecha | jueces | fecha y jueces |
|---|---|---|---|
| 348 | 133/133 (100%) | 123/133 (92,5%) | 123/133 (92,5%) |
| 349 | 153/153 (100%) | 140/153 (91,5%) | 140/153 (91,5%) |

Los ~8% sin jueces son entradas del índice que reproducen solo el sumario con la
nota `(*) Sentencia del <fecha>. Ver fallo.`: el cuerpo del fallo (con las
firmas) no está en esas páginas. Quedan con `jueces=()` — marcados, no
inventados. `test_aceptacion_*` mide sobre 348 **y** 349 (dos tomos, sin sesgo
de un solo archivo).
"""

from pathlib import Path

import pytest

from spectre.corpus.fallo import (
    extraer_metadatos,
    parsear_indice,
    segmentar,
    texto_del_fallo,
)
from spectre.corpus.pdf import extraer_texto

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
TOMOS = {
    348: Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf",
    349: Path(__file__).resolve().parents[1] / "data" / "tomos" / "349.pdf",
}


# --- extraer_metadatos: sobre texto armado a mano ------------------- #

_CIERRE_3 = (
    "Por ello, se desestima el recurso. Notifíquese y devuélvase.\n"
    "Horacio Rosatti — Carlos Fernando Rosenkrantz — Ricardo Luis\n"
    "Lorenzetti.\n"
    "Recurso de queja interpuesto por el Estado Nacional, representado por el Dr. X.\n"
    "Tribunal de origen: Sala III de la Cámara Federal de la Seguridad Social.\n"
)


def test_fecha_de_la_corte():
    txt = "FALLO DE LA CORTE SUPREMA\nBuenos Aires, 6 de febrero de 2025.\nVistos"
    m = extraer_metadatos(txt, caratula="A c/ B s/ x")
    assert m.fecha == "2025-02-06"


def test_fecha_toma_la_ultima_no_la_del_dictamen():
    txt = (
        "Buenos Aires, 3 de marzo de 2025.\n-Del dictamen ...\n"
        "FALLO DE LA CORTE SUPREMA\nBuenos Aires, 21 de mayo de 2025.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").fecha == "2025-05-21"


def test_fecha_desde_la_nota_ver_fallo():
    txt = "algo de doctrina\n(*) Sentencia del 12 de marzo de 2025. Ver fallo.\n"
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").fecha == "2025-03-12"


def test_fecha_setiembre_variante():
    txt = "Buenos Aires, 1 de setiembre de 2025.\n"
    assert extraer_metadatos(txt, caratula="A s/ x").fecha == "2025-09-01"


def test_jueces_bloque_partido_en_dos_lineas():
    m = extraer_metadatos(_CIERRE_3, caratula="A c/ B s/ x")
    assert m.jueces == (
        "Horacio Rosatti",
        "Carlos Fernando Rosenkrantz",
        "Ricardo Luis Lorenzetti",
    )


def test_jueces_con_aclaraciones_pegadas():
    txt = (
        "Notifíquese.\n"
        "Horacio Rosatti (según su voto)— Carlos Fernando Rosenkrantz —\n"
        "Ricardo Luis Lorenzetti.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").jueces == (
        "Horacio Rosatti",
        "Carlos Fernando Rosenkrantz",
        "Ricardo Luis Lorenzetti",
    )


def test_jueces_apellido_en_minuscula_tomo_349():
    txt = (
        "Hágase saber.\n"
        "Horacio rosatti — Carlos Fernando rosenkrantz — Ricardo luis\n"
        "lorenzetti.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").jueces == (
        "Horacio Rosatti",
        "Carlos Fernando Rosenkrantz",
        "Ricardo Luis Lorenzetti",
    )


def test_jueces_firma_de_uno_solo():
    txt = (
        "declarar la inconstitucionalidad del artículo 22. Notifíquese,\n"
        "comuníquese y, oportunamente, archívese.\n"
        "Horacio Rosatti.\n"
        "Parte actora: Cepas Argentinas S.A.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").jueces == ("Horacio Rosatti",)


def test_jueces_sin_firmas_queda_vacio_no_inventa():
    txt = (
        "doctrina del sumario\n"
        "-Del dictamen de la Procuración General al que la Corte remite-(*)\n"
        "(*) Sentencia del 12 de marzo de 2025. Ver fallo.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").jueces == ()


def test_no_confunde_una_frase_con_em_dash_con_firmas():
    txt = (
        "Notifíquese.\n"
        "La sentencia — según el voto de la mayoría — resolvió la cuestión.\n"
    )
    assert extraer_metadatos(txt, caratula="A c/ B s/ x").jueces == ()


def test_tribunal_origen_partido_en_dos_lineas():
    txt = (
        "Notifíquese.\nHoracio Rosatti — Carlos Rosenkrantz — Ricardo Lorenzetti.\n"
        "Tribunal de origen: Superior Tribunal de Justicia de la Provincia de "
        "La Pampa,\nSala A.\n"
    )
    m = extraer_metadatos(txt, caratula="A c/ B s/ x")
    assert m.tribunal_origen == (
        "Superior Tribunal de Justicia de la Provincia de La Pampa, Sala A"
    )


def test_tipo_de_recurso():
    assert (
        extraer_metadatos(_CIERRE_3, caratula="A c/ B s/ x").tipo_recurso
        == "recurso de queja"
    )
    txt = 'Vistos los autos: "Recurso de hecho deducido por la demandada".\n'
    assert extraer_metadatos(txt, caratula="A c/ B").tipo_recurso == "recurso de hecho"


def test_partes_actor_y_demandado():
    m = extraer_metadatos(
        "", caratula="Raskovsky, Luis c/ Perrone, Gabriela s/ ejecutivo"
    )
    assert m.actor == "Raskovsky, Luis"
    assert m.demandado == "Perrone, Gabriela"


def test_partes_sin_c_barra_una_sola_parte():
    m = extraer_metadatos("", caratula="N.N. s/ incidente de incompetencia")
    assert m.actor == "N.N."
    assert m.demandado is None


# --- texto_del_fallo ---------------------------------------------- #


@pytest.fixture(scope="module")
def paginas_fixture():
    pgs = extraer_texto(FIXTURE)
    return {p.pagina_oficial: p for p in pgs if p.pagina_oficial is not None}


def test_arma_el_texto_y_corta_en_la_proxima_caratula(paginas_fixture):
    # Albarracín arranca en 31; el siguiente (N.N.) en 33.
    txt = texto_del_fallo(
        paginas_fixture,
        pagina_inicio=31,
        pagina_inicio_siguiente=33,
        pagina_fin_cuerpo=36,
    )
    assert "FALLO DE LA CORTE SUPREMA" in txt
    assert "Horacio Rosatti — Carlos Fernando Rosenkrantz" in txt
    # cortó antes de la carátula de N.N.
    assert "incidente de incompetencia" not in txt.lower()


def test_metadatos_de_un_fallo_real(paginas_fixture):
    txt = texto_del_fallo(
        paginas_fixture,
        pagina_inicio=31,
        pagina_inicio_siguiente=33,
        pagina_fin_cuerpo=36,
    )
    m = extraer_metadatos(
        txt,
        caratula=(
            "Albarracín, Carlos Ciro c/ Estado Nacional – Ministerio de "
            "Defensa s/ Personal Militar y Civil de las FFAA y de Seg."
        ),
    )
    assert m.fecha == "2025-02-06"
    assert m.jueces == (
        "Horacio Rosatti",
        "Carlos Fernando Rosenkrantz",
        "Ricardo Luis Lorenzetti",
    )
    assert "Cámara Federal de la Seguridad Social" in m.tribunal_origen
    assert m.tipo_recurso == "recurso de hecho"
    assert m.actor == "Albarracín, Carlos Ciro"
    assert m.demandado.startswith("Estado Nacional")


# --- aceptación: Tomo 348 y Tomo 349 --------------------------- #


@pytest.mark.slow
@pytest.mark.parametrize("tomo", [348, 349])
def test_aceptacion(tomo):
    pdf = TOMOS[tomo]
    if not pdf.is_file():
        pytest.skip(f"falta {pdf} (fixture real no versionado)")
    entradas = parsear_indice(pdf)
    paginas = extraer_texto(pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    con_fecha = con_jueces = ambos = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        txt = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        m = extraer_metadatos(txt, caratula=f.caratula)
        con_fecha += m.fecha is not None
        con_jueces += bool(m.jueces)
        ambos += m.fecha is not None and bool(m.jueces)

    n = r.cantidad
    assert con_fecha / n >= 0.90, f"fecha {con_fecha}/{n}"
    assert con_jueces / n >= 0.90, f"jueces {con_jueces}/{n}"
    assert ambos / n >= 0.90, f"fecha y jueces {ambos}/{n}"
