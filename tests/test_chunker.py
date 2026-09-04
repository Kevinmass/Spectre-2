"""PR-11 — chunker consciente de secciones.

Criterio de aceptación (plan §6): ningún chunk con texto de dos secciones; el
cuerpo del Tomo 348 des-hifenado (~333.000 palabras) a 400/80 da ~1.041 chunks
si se cuenta global. `test_aceptacion` mide sobre los tomos 348 y 349.

Medido: 348 -> 1.112 chunks (197 secciones; global 330.840/320 = 1.033), 349 ->
1.087 (226 secciones). El +7% sobre la referencia global es el redondeo por
sección (cada sección cierra su última ventana). 0 chunks fuera de su sección en
ambos tomos.
"""

from pathlib import Path

import pytest

from spectre.chunking import (
    Chunk,
    fragmentar_fallo,
    fragmentar_seccion,
    normalizar_espacios,
    ubicar_pagina,
    ventanas,
)
from spectre.corpus.fallo import (
    SeccionFallo,
    parsear_indice,
    partir_secciones,
    segmentar,
    texto_del_fallo_paginado,
)
from spectre.corpus.pdf import contar_palabras, extraer_texto, limpiar

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"
TOMOS = {
    348: Path(__file__).resolve().parents[1] / "data" / "tomos" / "348.pdf",
    349: Path(__file__).resolve().parents[1] / "data" / "tomos" / "349.pdf",
}


# --- ventanas: la mecánica de la ventana deslizante --------------- #


def test_ventanas_lista_vacia():
    assert ventanas([]) == []


def test_ventanas_texto_corto_es_una_sola():
    pal = ["a"] * 250
    assert ventanas(pal, objetivo=400, solape=80) == [pal]


def test_ventanas_justo_el_objetivo_es_una_sola():
    pal = [str(i) for i in range(400)]
    assert ventanas(pal, objetivo=400, solape=80) == [pal]


def test_ventanas_dos_con_solape_correcto():
    pal = [str(i) for i in range(700)]
    v = ventanas(pal, objetivo=400, solape=80)
    assert len(v) == 2
    assert v[0] == [str(i) for i in range(400)]
    assert v[1] == [str(i) for i in range(320, 700)]
    # las últimas 80 de la primera son las primeras 80 de la segunda
    assert v[0][-80:] == v[1][:80]


def test_ventanas_tres():
    pal = [str(i) for i in range(1000)]
    v = ventanas(pal, objetivo=400, solape=80)
    assert [len(x) for x in v] == [400, 400, 360]
    assert v[1][-80:] == v[2][:80]


def test_ventanas_no_abre_una_ventana_de_puro_solape():
    # con exactamente `objetivo` palabras hay una sola ventana, no una 2ª que
    # sería toda solape; con una palabra más aparece la cola.
    assert len(ventanas([str(i) for i in range(400)], objetivo=400, solape=80)) == 1
    assert len(ventanas([str(i) for i in range(430)], objetivo=400, solape=80)) == 2


@pytest.mark.parametrize("obj,sol", [(0, 0), (100, 100), (100, 150), (100, -1)])
def test_ventanas_parametros_invalidos(obj, sol):
    with pytest.raises(ValueError):
        ventanas(["a", "b"], objetivo=obj, solape=sol)


# --- fragmentar: chunks con su metadata -------------------------- #


def _sec(tipo, texto, orden, autor=None):
    return SeccionFallo(tipo=tipo, autor=autor, orden=orden, texto=texto)


def test_fragmentar_seccion_hereda_cita_seccion_y_orden():
    sec = _sec("voto", "palabra " * 900, 2, autor="Juez X")
    chunks = fragmentar_seccion(sec, cita="348:145", pagina_inicio=145, paginas_norm=[])
    assert len(chunks) == 3
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(c.cita == "348:145" for c in chunks)
    assert all(c.seccion_tipo == "voto" and c.seccion_autor == "Juez X" for c in chunks)
    assert all(c.seccion_orden == 2 for c in chunks)
    assert [c.orden for c in chunks] == [0, 1, 2]
    # sin páginas donde ubicar -> cae en la de inicio
    assert all(c.pagina_oficial == 145 for c in chunks)


def test_fragmentar_fallo_ningun_chunk_cruza_secciones():
    may = _sec("mayoria", " ".join(f"may{i}" for i in range(500)), 0)
    dis = _sec("disidencia", " ".join(f"dis{i}" for i in range(500)), 1, autor="Y")
    paginado = [(145, may.texto), (146, dis.texto)]
    chunks = fragmentar_fallo([may, dis], paginado, cita="348:145", pagina_inicio=145)
    por_orden = {0: may.texto.split(), 1: dis.texto.split()}
    for c in chunks:
        pal = por_orden[c.seccion_orden]
        w = c.texto.split()
        # es una ventana contigua de SU sección, y de ninguna otra
        assert any(pal[k : k + len(w)] == w for k in range(len(pal) - len(w) + 1))
        otra = por_orden[1 - c.seccion_orden]
        assert not any(otra[k : k + len(w)] == w for k in range(len(otra) - len(w) + 1))


def test_fragmentar_fallo_hereda_la_pagina_por_texto():
    may = _sec("mayoria", " ".join(f"m{i}" for i in range(300)), 0)
    voto = _sec("voto", " ".join(f"v{i}" for i in range(300)), 1)
    paginado = [(145, may.texto), (146, "ruido " + voto.texto + " mas ruido")]
    chunks = fragmentar_fallo([may, voto], paginado, cita="348:145", pagina_inicio=145)
    por_tipo = {c.seccion_tipo: c for c in chunks}
    assert por_tipo["mayoria"].pagina_oficial == 145
    assert por_tipo["voto"].pagina_oficial == 146


def test_ubicar_pagina_devuelve_none_si_no_esta():
    pn = [(10, "el zorro marrón salta"), (11, "sobre el perro perezoso")]
    assert ubicar_pagina("texto que no aparece en ninguna parte del todo", pn) is None
    assert ubicar_pagina("el zorro marrón salta", pn) == 10


# --- integración: un fallo real con voto concurrente ------------- #


def test_chunks_de_un_fallo_real_respetan_las_secciones():
    paginas = extraer_texto(FIXTURE)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    paginado = texto_del_fallo_paginado(
        por_oficial,
        pagina_inicio=34,
        pagina_inicio_siguiente=36,
        pagina_fin_cuerpo=max(por_oficial),
    )
    texto = "\n".join(t for _, t in paginado)
    secciones = partir_secciones(texto)
    assert [s.tipo for s in secciones] == ["mayoria", "voto"]
    chunks = fragmentar_fallo(secciones, paginado, cita="348:34", pagina_inicio=34)

    assert chunks
    assert {c.seccion_tipo for c in chunks} == {"mayoria", "voto"}
    assert all(c.cita == "348:34" for c in chunks)
    por_orden = {s.orden: s.texto.split() for s in secciones}
    for c in chunks:
        pal = por_orden[c.seccion_orden]
        w = c.texto.split()
        assert any(pal[k : k + len(w)] == w for k in range(len(pal) - len(w) + 1))


# --- aceptación: Tomo 348 (~1.041) y Tomo 349 ------------------- #


@pytest.mark.slow
@pytest.mark.parametrize("tomo", [348, 349])
def test_aceptacion(tomo):
    pdf = TOMOS[tomo]
    if not pdf.is_file():
        pytest.skip(f"falta {pdf} (fixture real no versionado)")
    entradas = parsear_indice(pdf)
    paginas = extraer_texto(pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin = max(por_oficial)
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    total = fuera_de_seccion = ubicados = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin,
        )
        texto = "\n".join(t for _, t in paginado)
        secciones = partir_secciones(texto)
        chunks = fragmentar_fallo(
            secciones, paginado, cita=f.cita, pagina_inicio=f.pagina_inicio
        )
        por_orden = {s.orden: s.texto.split() for s in secciones}
        pn = [(o, normalizar_espacios(t)) for o, t in paginado]
        for c in chunks:
            total += 1
            pal = por_orden[c.seccion_orden]
            w = c.texto.split()
            if not any(pal[k : k + len(w)] == w for k in range(len(pal) - len(w) + 1)):
                fuera_de_seccion += 1
            if ubicar_pagina(normalizar_espacios(c.texto), pn) is not None:
                ubicados += 1

    # D-4: ningún chunk con texto de dos secciones (es una ventana de una sola).
    assert fuera_de_seccion == 0, f"{fuera_de_seccion} chunks fuera de su sección"

    # herencia de página: casi todos se ubican por texto (el resto cae en la
    # página de inicio del fallo, que no es inventar).
    assert ubicados / total > 0.95, f"solo {ubicados}/{total} chunks ubicados"

    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    cw = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    referencia = cw // 320  # cuenta global, ignora bordes de sección
    if tomo == 348:
        # el real es por sección y da ~7% más que la cuenta global; se tolera un
        # 20% para no atarlo al 133≠126 fallos de PR-06/07.
        assert referencia * 0.9 <= total <= referencia * 1.2, (
            f"Tomo 348: {total} chunks (referencia global {referencia})"
        )
    else:
        assert total > 0
