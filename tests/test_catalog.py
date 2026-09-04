"""PR-16 — catálogo de tomos CSJN (D-9 del plan).

Criterio de aceptación (plan §6): catálogo con los 349 tomos y el año de cada
uno.

`test_parsear_*` y `test_listar_catalogo_con_paginas_falsas` son puros (sin
red): corren siempre, contra un recorte real guardado en `tests/fixtures/` o
contra páginas fabricadas a mano. `test_listar_catalogo_real` (marca `red`)
pega contra el sitio real de la CSJN — confirma el criterio de aceptación tal
cual, pero queda fuera del run por defecto (CI no depende de que ese sitio
esté arriba): `pytest -m red tests/test_catalog.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spectre.corpus.csjn.catalog import (
    EntradaCatalogo,
    _parsear_etiqueta,
    listar_catalogo,
    parsear_pagina,
)

FIXTURE = Path(__file__).parent / "fixtures" / "csjn_catalogo_p1.html"


def test_parsear_etiqueta_con_volumen():
    assert _parsear_etiqueta("349-I") == (349, "I")
    assert _parsear_etiqueta("347-II") == (347, "II")


def test_parsear_etiqueta_sin_volumen():
    assert _parsear_etiqueta("216") == (216, None)
    assert _parsear_etiqueta("  1  ") == (1, None)


def test_parsear_pagina_fixture_real():
    html = FIXTURE.read_text(encoding="utf-8")
    entradas, pagina, total_paginas = parsear_pagina(html)

    assert pagina == 1
    assert total_paginas == 5
    assert entradas == [
        EntradaCatalogo(349, "I", "2026", "447"),
        EntradaCatalogo(348, "I", "2025", "445"),
        EntradaCatalogo(347, "I", "2024", "443"),
        EntradaCatalogo(347, "II", "2024", "446"),
        EntradaCatalogo(346, "I", "2023", "441"),
    ]


def test_parsear_pagina_detecta_el_mismo_numero_en_dos_volumenes():
    html = FIXTURE.read_text(encoding="utf-8")
    entradas, _, _ = parsear_pagina(html)
    con_347 = [e for e in entradas if e.numero == 347]
    assert {e.volumen for e in con_347} == {"I", "II"}
    assert {e.csjn_tomo_id for e in con_347} == {"443", "446"}


def test_parsear_pagina_sin_indicador_de_paginacion_revienta():
    with pytest.raises(ValueError):
        parsear_pagina("<div>no hay filas ni pie de página acá</div>")


def test_listar_catalogo_con_paginas_falsas():
    # dos páginas fabricadas a mano: prueba el bucle de paginación sin red.
    pagina_1 = (
        '<div class="lg-col-span-4"><span>2</span></div>'
        '<div class="lg-col-span-3"><span>1900</span></div>'
        'href="/sj/verTomo?tomoId=20"'
        "gina&nbsp;<span>1</span> de <span>2</span>"
    )
    pagina_2 = (
        '<div class="lg-col-span-4"><span>1</span></div>'
        '<div class="lg-col-span-3"><span>1899/1900</span></div>'
        'href="/sj/verTomo?tomoId=10"'
        "gina&nbsp;<span>2</span> de <span>2</span>"
    )
    pedidas: list[int] = []

    def _fake(pagina: int) -> str:
        pedidas.append(pagina)
        return pagina_1 if pagina == 1 else pagina_2

    entradas = listar_catalogo(pedir_pagina=_fake)

    assert pedidas == [1, 2]
    assert entradas == [
        EntradaCatalogo(2, None, "1900", "20"),
        EntradaCatalogo(1, None, "1899/1900", "10"),
    ]


# --- red: contra el sitio real de la CSJN -------------------------------- #


@pytest.mark.red
def test_listar_catalogo_real():
    # El sitio es un recurso vivo (la CSJN publica tomos nuevos): no se fija
    # un total exacto, se verifica la forma que el criterio de aceptación
    # pide — contiguo desde el 1, con **al menos** los 349 del plan (escrito
    # 03/09/2026; medido esta sesión: 349 números, 421 filas).
    entradas = listar_catalogo()

    numeros = {e.numero for e in entradas}
    assert min(numeros) == 1
    assert numeros == set(range(1, max(numeros) + 1))  # sin huecos
    assert len(numeros) >= 349

    assert all(e.anio for e in entradas)  # "el año de cada uno"

    ids = [e.csjn_tomo_id for e in entradas]
    assert len(ids) == len(set(ids))  # cada fila, un id de la CSJN distinto

    # el hallazgo del spike: algunos números tienen más de un volumen físico
    por_numero: dict[int, list[str | None]] = {}
    for e in entradas:
        por_numero.setdefault(e.numero, []).append(e.volumen)
    con_mas_de_uno = {n: v for n, v in por_numero.items() if len(v) > 1}
    assert con_mas_de_uno  # p. ej. 347: ["I", "II"]
    assert por_numero[347] == ["I", "II"]
