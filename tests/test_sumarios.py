"""PR-C2 — sumarios oficiales de la CSJN por tomo y página.

Los `test_*` puros (parseo + bucle de paginación con un transporte falso)
corren siempre. `test_*_real` (marca `red`) pega contra el sitio real de la
Secretaría de Jurisprudencia y queda fuera del run por defecto, igual que el
catálogo de PR-16: `pytest -m red tests/test_sumarios.py`.

Recon del flujo y la forma de los datos: `docs/qa/spike-C2-sumarios.md`.
"""

from __future__ import annotations

import pytest

from spectre.corpus.csjn.sumarios import (
    Sumario,
    _fecha_iso,
    _id_documento,
    _map_sumario,
    _map_voces,
    _materia,
    _texto_plano,
    _total_resultados,
    _voces,
    buscar_sumarios,
    buscar_voces,
)

# --- parseo puro -------------------------------------------------------- #


def test_texto_plano_saca_tags_y_colapsa_espacios():
    assert _texto_plano("<p>Es <b>arbitraria</b>\n  la\tsentencia.</p>") == (
        "Es arbitraria la sentencia."
    )
    assert _texto_plano("caf&eacute; &amp; t&eacute;") == "café & té"
    assert _texto_plano(None) == ""
    assert _texto_plano("") == ""


def test_voces_separa_por_guion_rodeado_de_espacios():
    assert _voces("DEPOSITO PREVIO - INTERESES - RECURSO DE QUEJA") == (
        "DEPOSITO PREVIO",
        "INTERESES",
        "RECURSO DE QUEJA",
    )
    # un guion pegado (nombre compuesto) no parte la voz
    assert _voces("BUENOS AIRES-CAPITAL - COMPETENCIA") == (
        "BUENOS AIRES-CAPITAL",
        "COMPETENCIA",
    )
    assert _voces("") == ()
    assert _voces(None) == ()


def test_fecha_iso_normaliza_dd_mm_yyyy():
    assert _fecha_iso("13/02/2025") == "2025-02-13"
    assert _fecha_iso("1/9/2024") == "2024-09-01"
    assert _fecha_iso("2025-02-13") is None  # ya no es dd/mm/yyyy
    assert _fecha_iso("") is None
    assert _fecha_iso(None) is None


def test_id_documento_extrae_de_link():
    assert (
        _id_documento(
            "/documentos/verDocumentoByIdLinksJSP.html?idDocumento=8059511&cache=1"
        )
        == "8059511"
    )
    assert _id_documento("sin id") is None
    assert _id_documento(None) is None


def test_total_resultados_lee_la_variable_del_html():
    assert _total_resultados('...\nvar totalResultados = "7";\n...') == 7
    assert _total_resultados("var totalResultados = 0;") == 0
    assert _total_resultados("<html>nada</html>") is None


def test_map_sumario_arma_el_dataclass():
    obj = {
        "tomo": 348,
        "pagina": 34,
        "autos": "GOBIERNO DE LA CIUDAD DE BUENOS AIRES s/INCIDENTE",
        "fechaString": "13/02/2025",
        "voces": "DEPOSITO PREVIO - INTERESES - RECURSO DE QUEJA",
        "texto": "<p>El inter&eacute;s se devenga desde la queja.</p>",
        "linkDocumento": (
            "/documentos/verDocumentoByIdLinksJSP.html?idDocumento=8059511"
        ),
    }
    s = _map_sumario(obj, tomo=348, pagina=34)
    assert s == Sumario(
        tomo=348,
        pagina=34,
        caratula="GOBIERNO DE LA CIUDAD DE BUENOS AIRES s/INCIDENTE",
        fecha="2025-02-13",
        voces=("DEPOSITO PREVIO", "INTERESES", "RECURSO DE QUEJA"),
        texto="El interés se devenga desde la queja.",
        id_documento="8059511",
    )


def test_map_sumario_usa_el_respaldo_de_tomo_pagina_si_falta():
    s = _map_sumario({"autos": "X", "texto": "y"}, tomo=349, pagina=1)
    assert (s.tomo, s.pagina) == (349, 1)
    assert s.voces == ()
    assert s.fecha is None
    assert s.materia is None


def test_materia_lee_materia_secretaria_string_o_objeto():
    assert _materia({"materiaSecretaria": "DERECHO ADMINISTRATIVO"}) == (
        "DERECHO ADMINISTRATIVO"
    )
    assert _materia({"materiaSecretaria": {"descripcion": "DERECHO PENAL"}}) == (
        "DERECHO PENAL"
    )
    assert _materia({"materiaSecretaria": "  "}) is None
    assert _materia({}) is None
    assert _materia(None) is None


def test_map_sumario_toma_la_materia_del_analisis_documental():
    obj = {
        "tomo": 348,
        "pagina": 34,
        "texto": "sumario",
        "analisisDocumental": {"materiaSecretaria": "DERECHO ADMINISTRATIVO"},
    }
    assert _map_sumario(obj, tomo=348, pagina=34).materia == "DERECHO ADMINISTRATIVO"


def test_map_voces_descarta_lo_incompleto():
    datos = [
        {"codigoValor": 1144, "valor": "CONTRATO ADMINISTRATIVO"},
        {"codigoValor": None, "valor": "SIN CODIGO"},
        {"codigoValor": 2, "valor": "  "},
        {"codigoValor": 5, "valor": "OTRA"},
    ]
    voces = _map_voces(datos)
    assert [(v.codigo, v.valor) for v in voces] == [
        (1144, "CONTRATO ADMINISTRATIVO"),
        (5, "OTRA"),
    ]


# --- buscar_sumarios: el bucle de paginación, con un transporte falso --- #


class _FakeTransporte:
    def __init__(self, total, paginas):
        self._total = total
        self._paginas = paginas
        self.abierta = False
        self.starts: list[int] = []

    def abrir_sesion(self):
        self.abierta = True

    def buscar(self, tomo, pagina):
        return self._total

    def paginar(self, start_index):
        self.starts.append(start_index)
        i = start_index // 10
        return list(self._paginas[i]) if i < len(self._paginas) else []


def _obj(n):
    return {"tomo": 348, "pagina": 36, "autos": f"caso {n}", "texto": f"sumario {n}"}


def test_buscar_sumarios_total_cero_no_pagina():
    tr = _FakeTransporte(0, [])
    assert buscar_sumarios(348, 145, transporte=tr) == []
    assert tr.starts == []  # ni se pidió una página


def test_buscar_sumarios_una_pagina():
    tr = _FakeTransporte(3, [[_obj(1), _obj(2), _obj(3)]])
    out = buscar_sumarios(348, 36, transporte=tr)
    assert [s.texto for s in out] == ["sumario 1", "sumario 2", "sumario 3"]
    assert tr.starts == [0]
    assert tr.abierta


def test_buscar_sumarios_varias_paginas():
    p1 = [_obj(i) for i in range(10)]
    p2 = [_obj(i) for i in range(10, 13)]
    tr = _FakeTransporte(13, [p1, p2])
    out = buscar_sumarios(348, 36, transporte=tr)
    assert len(out) == 13
    assert tr.starts == [0, 10]


def test_buscar_sumarios_trunca_si_el_server_devuelve_de_mas():
    tr = _FakeTransporte(2, [[_obj(1), _obj(2), _obj(3), _obj(4)]])
    assert len(buscar_sumarios(348, 36, transporte=tr)) == 2


def test_buscar_sumarios_corta_si_una_pagina_viene_vacia_antes_del_total():
    # defensa: total dice 20 pero el server se queda sin datos en la 1ª página
    tr = _FakeTransporte(20, [[_obj(1), _obj(2)]])
    assert len(buscar_sumarios(348, 36, transporte=tr)) == 2
    assert tr.starts == [0, 10]  # intentó la 2ª, vino vacía, cortó


# --- red: contra el sitio real de la CSJN ------------------------------ #


@pytest.mark.red
def test_buscar_sumarios_real_tomo_348():
    # 348:36 (Municipalidad de Villa Gesell) tiene varios sumarios; medido esta
    # sesión: 7. El sitio es un recurso vivo, no se fija el número exacto.
    sumarios = buscar_sumarios(348, 36)
    assert len(sumarios) >= 2
    for s in sumarios:
        assert s.tomo == 348
        assert s.pagina == 36
        assert s.texto  # el sumario nunca viene vacío
        assert s.voces  # y siempre trae al menos una voz
        assert s.fecha == "2025-02-13"


@pytest.mark.red
def test_buscar_sumarios_real_pagina_sin_sumario_da_vacio():
    # 348:145 no es inicio de un fallo con sumarios en la base
    assert buscar_sumarios(348, 145) == []


@pytest.mark.red
def test_buscar_voces_real_autocompleta_el_tesauro():
    voces = buscar_voces("contrato administrativo")
    valores = {v.valor for v in voces}
    assert "CONTRATO ADMINISTRATIVO" in valores
    assert all(isinstance(v.codigo, int) for v in voces)
