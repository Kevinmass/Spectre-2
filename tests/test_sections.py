"""PR-09 — secciones del fallo: dictamen, mayoría, votos, disidencias.

Criterio de aceptación (plan §6): un fallo con votos concurrentes conocido (p.
145 del Tomo 348) se parte en las secciones correctas; ningún texto queda
huérfano. La página 145 cae dentro del fallo "Loyola" (`348:113`, 52 páginas),
que trae dictamen del Procurador y tres votos concurrentes (Rosenkrantz,
Lorenzetti, García-Mansilla).

`test_aceptacion_loyola` verifica esa partición. `test_sin_huerfanos_*` mide
sobre los tomos 348 y 349 que casi ninguna línea de contenido queda fuera de una
sección (solo marcadores estructurales: `Considerando:`, encabezados, etc.).
"""

import re
from pathlib import Path

import pytest

from spectre.corpus.fallo import (
    parsear_indice,
    partir_secciones,
    segmentar,
    texto_del_fallo,
)
from spectre.corpus.pdf import extraer_texto

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
TOMOS = {
    348: Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf",
    349: Path(__file__).resolve().parents[1] / "data" / "tomos" / "349.pdf",
}

_MARCADOR = re.compile(
    r"^(FALLO DE LA CORTE SUPREMA|Considerando\s*:|Autos y [Vv]istos.*|"
    r"Suprema Corte\s*:|Dictamen de la Procuraci.*|Vistos( los autos)?.*|"
    r"Resulta\s*:|voto (?:del?|de la|de los)\b.*|"
    r"[Dd]isidencia (?:del?|de la|de los)\b.*|-?[IVX]{1,6}-?\)?\s*$)",
    re.IGNORECASE,
)


def _huerfanas(texto: str) -> list[str]:
    from collections import Counter

    secciones = partir_secciones(texto)
    orig = Counter(ln.strip() for ln in texto.splitlines() if ln.strip())
    cubierto: Counter[str] = Counter()
    for s in secciones:
        cubierto.update(ln.strip() for ln in s.texto.splitlines() if ln.strip())
    return [ln for ln in (orig - cubierto).elements() if not _MARCADOR.match(ln)]


# --- partir_secciones: sobre texto armado a mano -------------------- #


def test_fallo_sin_encabezados_es_una_sola_mayoria():
    secs = partir_secciones("PARTES\nun sumario cualquiera\ny otra línea")
    assert [(s.tipo, s.autor) for s in secs] == [("mayoria", None)]
    assert "un sumario cualquiera" in secs[0].texto


def test_texto_vacio_no_da_secciones():
    assert partir_secciones("   \n  ") == []


def test_dictamen_mayoria_y_voto():
    texto = (
        "DERECHO\nun sumario de la mayoría\n"
        "Dictamen de la Procuración General\n"
        "Suprema Corte:\n-I-\ntexto del dictamen\n"
        "FALLO DE LA CORTE SUPREMA\nBuenos Aires, 1 de marzo de 2025.\n"
        "Considerando:\n1°) Que la mayoría resuelve.\n"
        "voto Del Señor Ministro Doctor don Ricardo Luis Lorenzetti\n"
        "Considerando:\n1°) Que en mi opinión.\n"
    )
    secs = partir_secciones(texto)
    assert [(s.tipo, s.autor) for s in secs] == [
        ("dictamen", None),
        ("mayoria", None),
        ("voto", "Ricardo Luis Lorenzetti"),
    ]
    assert "texto del dictamen" in secs[0].texto
    assert "un sumario de la mayoría" in secs[1].texto
    assert "Que en mi opinión." in secs[2].texto
    assert not _huerfanas(texto)


def test_sumario_se_atribuye_por_su_etiqueta():
    texto = (
        "UNO\nsumario sin etiqueta\n"
        "DOS\nsumario de la concurrencia (Voto del juez Lorenzetti).\n"
        "FALLO DE LA CORTE SUPREMA\nConsiderando:\nQue sí.\n"
        "voto Del Señor Ministro Doctor don Ricardo Luis Lorenzetti\n"
        "Considerando:\nQue concurro.\n"
    )
    secs = {(s.tipo, s.autor): s.texto for s in partir_secciones(texto)}
    assert "sumario sin etiqueta" in secs[("mayoria", None)]
    assert "sumario de la concurrencia" in secs[("voto", "Ricardo Luis Lorenzetti")]


def test_sumario_de_disidencia_crea_la_seccion_si_no_hay_bloque():
    texto = (
        "TEMA\nla disidencia sostuvo lo contrario (Disidencia del juez Rosenkrantz).\n"
        "-La Corte, por mayoría, declaró inadmisible el recurso (art. 280 CPCCN)-.\n"
        "FALLO DE LA CORTE SUPREMA\nConsiderando:\nQue es inadmisible.\n"
    )
    secs = [(s.tipo, s.autor) for s in partir_secciones(texto)]
    assert ("disidencia", "Rosenkrantz") in secs
    assert not _huerfanas(texto)


def test_encabezado_conjunto_de_dos_jueces():
    texto = (
        "FALLO DE LA CORTE SUPREMA\nConsiderando:\nQue la mayoría decide.\n"
        "Disidencia Del Señor Presidente Doctor don Horacio Rosatti y del\n"
        "Señor Ministro Doctor don Ricardo Luis Lorenzetti\n"
        "Considerando:\nQue disentimos.\n"
    )
    secs = partir_secciones(texto)
    disi = [s for s in secs if s.tipo == "disidencia"]
    assert len(disi) == 1
    assert disi[0].autor == "Horacio Rosatti, Ricardo Luis Lorenzetti"


def test_mencion_inline_no_es_encabezado():
    texto = (
        "FALLO DE LA CORTE SUPREMA\nConsiderando:\n"
        "1°) Que, como se dijo en la disidencia de los jueces Lorenzetti y\n"
        "Zaffaroni (Fallos: 340:1); 341:23, la cuestión es otra.\n"
        "Por ello, se resuelve.\n"
    )
    secs = partir_secciones(texto)
    assert [s.tipo for s in secs] == ["mayoria"]
    assert "Zaffaroni" in secs[0].texto


# --- integración: un fallo con voto, desde el fixture -------------- #


def test_fallo_con_voto_desde_fixture():
    paginas = extraer_texto(FIXTURE)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    texto = texto_del_fallo(
        por_oficial,
        pagina_inicio=34,
        pagina_inicio_siguiente=36,
        pagina_fin_cuerpo=36,
    )
    secs = partir_secciones(texto)
    assert [(s.tipo, s.autor) for s in secs] == [
        ("mayoria", None),
        ("voto", "Ricardo Luis Lorenzetti"),
    ]
    assert not _huerfanas(texto)


# --- aceptación: Loyola (p. 145 del Tomo 348) y sin huérfanos ---- #


def _texto_del_fallo(tomo: int, cita: str) -> str:
    entradas = parsear_indice(TOMOS[tomo])
    paginas = extraer_texto(TOMOS[tomo])
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(entradas, paginas, tomo_numero=tomo)
    i = next(k for k, f in enumerate(r.fallos) if f.cita == cita)
    sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
    return texto_del_fallo(
        por_oficial,
        pagina_inicio=r.fallos[i].pagina_inicio,
        pagina_inicio_siguiente=sig,
        pagina_fin_cuerpo=fin,
    )


@pytest.mark.slow
@pytest.mark.skipif(not TOMOS[348].is_file(), reason="falta data/tomos/348.pdf")
def test_aceptacion_loyola():
    secs = partir_secciones(_texto_del_fallo(348, "348:113"))
    resumen = [(s.tipo, s.autor) for s in secs]
    assert resumen == [
        ("dictamen", None),
        ("mayoria", None),
        ("voto", "Carlos Fernando Rosenkrantz"),
        ("voto", "Ricardo Luis Lorenzetti"),
        ("voto", "Manuel José García-Mansilla"),
    ]
    # ningún texto de contenido queda huérfano; lo único fuera de las secciones
    # son marcadores estructurales (incluida la 2ª línea de un encabezado de voto
    # cuando el apellido dobla de renglón: `Rosenkrantz`, `García-Mansilla`).
    sueltas = _huerfanas(_texto_del_fallo(348, "348:113"))
    assert len(sueltas) <= 3, sueltas


@pytest.mark.slow
@pytest.mark.parametrize("tomo", [348, 349])
def test_sin_huerfanos_en_el_tomo(tomo):
    pdf = TOMOS[tomo]
    if not pdf.is_file():
        pytest.skip(f"falta {pdf}")
    entradas = parsear_indice(pdf)
    paginas = extraer_texto(pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    huerfanas = total = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        huerfanas += len(_huerfanas(texto))
        total += sum(1 for ln in texto.splitlines() if ln.strip())

    assert huerfanas / total < 0.01, f"{huerfanas}/{total} líneas huérfanas"
