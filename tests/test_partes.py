"""PR-C5 — clasificación del tipo de parte (`corpus/fallo/partes.py`).

Reglas + listas: `estado` / `organismo` / `empresa` / `persona_fisica` / `None`.
Los casos límite (banco público vs. privado, sociedad del Estado, razón social
sin sufijo) van con su decisión explícita.
"""

from __future__ import annotations

import pytest

from spectre.corpus.fallo.partes import clasificar_parte

_CASOS = {
    # --- estado ---
    "Estado Nacional": "estado",
    "E.N. - Ministerio de Defensa": "estado",
    "Estado Nacional - Ministerio de Economía": "estado",
    "Provincia de Buenos Aires": "estado",
    "Provincia de Santiago del Estero": "estado",
    "Gobierno de la Ciudad de Buenos Aires": "estado",
    "GCBA": "estado",
    "G.C.B.A.": "estado",
    "Municipalidad de Villa Gesell": "estado",
    "Comuna de Rosario": "estado",
    "Ministerio de Trabajo, Empleo y Seguridad Social": "estado",
    "AFIP": "estado",
    "A.F.I.P. - DGI": "estado",
    "Administración Federal de Ingresos Públicos": "estado",
    "ANSeS": "estado",
    "Dirección General Impositiva": "estado",
    "Fisco Nacional": "estado",
    "Poder Ejecutivo Nacional": "estado",
    # --- organismo ---
    "Banco Central de la República Argentina": "organismo",
    "B.C.R.A.": "organismo",
    "Banco de la Nación Argentina": "organismo",
    "Banco de la Provincia de Buenos Aires": "organismo",
    "Universidad Nacional de Córdoba": "organismo",
    "Universidad de Buenos Aires": "organismo",
    "Instituto Nacional de Servicios Sociales para Jubilados y Pensionados": (
        "organismo"
    ),
    "PAMI": "organismo",
    "Caja Nacional de Previsión": "organismo",
    "Obra Social de Empleados de Comercio": "organismo",
    "Superintendencia de Seguros de la Nación": "organismo",
    "ENARGAS": "organismo",
    "Colegio Público de Abogados de la Capital Federal": "organismo",
    "Y.P.F. Sociedad del Estado": "organismo",
    "Dirección Nacional de Vialidad": "organismo",
    # --- empresa ---
    "Y.P.F. S.A.": "empresa",
    "YPF S.A.": "empresa",
    "Telecom Argentina S.A.": "empresa",
    "Aguas Argentinas S.A.": "empresa",
    "Banco Macro S.A.": "empresa",
    "Banco Río de la Plata S.A.": "empresa",
    "La Caja A.R.T. S.A.": "empresa",
    "Nobleza Piccardo S.A.I.C. y F.": "empresa",
    "Massuh S.A.": "empresa",
    "Cooperativa de Trabajo Portuarios Ltda.": "empresa",
    "Transportes Automotores La Estrella S.A.": "empresa",
    "Editorial Perfil S.A.": "empresa",
    "Editorial Perfil": "empresa",
    "Frigorífico Regional Salto": "empresa",
    # --- persona física ---
    "Pérez, Juan Carlos": "persona_fisica",
    "Rodríguez, María": "persona_fisica",
    "García": "persona_fisica",
    "N.N.": "persona_fisica",
    "Sucesión de López, Pedro": "persona_fisica",
    "Gómez, Ana y otros": "persona_fisica",
    "Fernández Blanco, José María": "persona_fisica",
    # --- sin clasificar (no se fuerza) ---
    "Asociación Civil Ambientalista": None,
    "Fundación Vida Silvestre Argentina": None,
    "Consorcio de Propietarios Avenida Corrientes 1234": None,
    "": None,
    "   ": None,
}


@pytest.mark.parametrize("texto,esperado", list(_CASOS.items()))
def test_clasificar_parte(texto, esperado):
    assert clasificar_parte(texto) == esperado


def test_none_y_vacio():
    assert clasificar_parte(None) is None
    assert clasificar_parte("") is None


def test_orden_organismo_antes_que_empresa_y_estado():
    # "Banco de la Nación Argentina" tiene "Nación Argentina" (patrón de estado)
    # y "Banco" (patrón de empresa); organismo gana por orden.
    assert clasificar_parte("Banco de la Nación Argentina") == "organismo"


def test_insensible_a_acentos_y_mayusculas():
    assert clasificar_parte("estado nacional") == "estado"
    assert clasificar_parte("MUNICIPALIDAD DE VILLA GESELL") == "estado"
