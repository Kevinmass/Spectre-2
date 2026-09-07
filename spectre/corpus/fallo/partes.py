"""Clasificación de la naturaleza de una parte (PR-C5).

La observación 01 pidió filtrar la búsqueda por el tipo de parte —"que una sea
una empresa", "que una sea el Estado"—. `structure._partes` ya parte la
carátula en actor / demandado (texto libre); acá se clasifica cada string en:

  - ``estado``          — Estado nacional / provincial / municipal, ministerios,
                          secretarías, AFIP, ANSeS, fisco, poderes del Estado,
                          tribunales y órganos legislativos.
  - ``organismo``       — entes autárquicos y demás personas públicas no
                          estatales en sentido estricto: universidades
                          nacionales, bancos públicos (Nación, Provincia, BCRA),
                          cajas, PAMI, obras sociales, entes reguladores,
                          colegios y consejos profesionales, sociedades del
                          Estado, agencias.
  - ``empresa``         — sociedades comerciales (S.A., S.R.L., SACIF…),
                          cooperativas, aseguradoras, "y Cía.".
  - ``persona_fisica``  — personas humanas ("Apellido, Nombre", "N.N.",
                          sucesiones).
  - ``None``            — no se pudo clasificar (se mide la cobertura, no se
                          fuerza — plan v2 §6). Asociaciones civiles,
                          fundaciones, sindicatos y cámaras gremiales caen acá:
                          la taxonomía de 4 tipos no tiene "entidad civil".

Reglas + listas, sin modelo. Orden: la primera categoría que matchea gana, y el
orden importa —``organismo`` antes que ``estado`` (para que "Banco de la Nación
Argentina" o "Banco de la Provincia de Buenos Aires" no caigan como Estado por
"Nación Argentina" / "Provincia de …"), y ambos antes que ``empresa`` (para que
"Banco de la Nación" no caiga como empresa por "Banco …")—. Módulo puro: no toca
la base ni importa `index`/`embed`.
"""

from __future__ import annotations

import re
import unicodedata

_TIPOS = ("persona_fisica", "empresa", "estado", "organismo")


def _norm(texto: str) -> str:
    """MAYÚSCULAS, sin acentos, guiones unificados a '-', espacios colapsados —
    para el match de patrones."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sin_acentos = sin_acentos.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", sin_acentos).strip().upper()


def _sigla(letras: str) -> str:
    """Regex para una sigla tolerando puntos/espacios entre letras: `_sigla('SA')`
    matchea 'SA', 'S.A.', 'S.A', 'S A'."""
    return r"\b" + r"\.? ?".join(letras) + r"\.?\b"


# --------------------------------------------------------------------------- #
# Listas de patrones (ya sobre texto normalizado por `_norm`). Se compilan una
# vez, más abajo.
# --------------------------------------------------------------------------- #

_PROVINCIAS = (
    "BUENOS AIRES",
    "CATAMARCA",
    "CHACO",
    "CHUBUT",
    "CORDOBA",
    "CORRIENTES",
    "ENTRE RIOS",
    "FORMOSA",
    "JUJUY",
    "LA PAMPA",
    "LA RIOJA",
    "MENDOZA",
    "MISIONES",
    "NEUQUEN",
    "RIO NEGRO",
    "SALTA",
    "SAN JUAN",
    "SAN LUIS",
    "SANTA CRUZ",
    "SANTA FE",
    "SANTIAGO DEL ESTERO",
    "TIERRA DEL FUEGO",
    "TUCUMAN",
)
_PROV_ALT = "|".join(_PROVINCIAS)

_ESTADO = [
    r"\bESTADO NACIONAL\b",
    r"\bESTADO (PROVINCIAL|DE LA PROVINCIA|DE LA CIUDAD)\b",
    r"^E\.? ?N\.? ?-",  # "E.N. - Ministerio …"
    r"^E\.? ?N\.? (MINISTERIO|M |SECRETARIA|SUBSECRETARIA|DIRECCION|VICEJEFATURA|"
    r"ADMINISTRACION|POLICIA|GENDARMERIA|PREFECTURA|CONARE|A ?F ?I ?P|D ?G ?I)",
    r"^E\.? ?N\.?$",
    r"(?<!BANCO DE LA )\bNACION ARGENTINA\b(?! ?- ?BANCO)",  # salvo "Banco … Nación"
    r"\bGOBIERNO (NACIONAL|DE LA CIUDAD|DE LA PROVINCIA)\b",
    r"\bG\.? ?C\.? ?B\.? ?A\b",
    r"\bCIUDAD (AUTONOMA )?DE BUENOS AIRES\b",
    # provincia en cualquier orden: "Provincia de X" y el invertido "X, Provincia de"
    r"\bPROVINCIA DE ?L?\b",
    r"\b(?:" + _PROV_ALT + r"),? PROVINCIA DE\b",
    r"\bMUNICIPALIDAD DE\b",
    r"\bMUNICIPIO DE\b",
    r"\bCOMUNA DE\b",
    r"\bMINISTERIO (DE|PUBLICO)\b",
    r"\bSECRETARIA (DE ESTADO|DE GOBIERNO DE|GENERAL DE LA PRESIDENCIA)\b",
    r"\bSUBSECRETARIA DE\b",
    r"\bJEFATURA DE GABINETE\b",
    r"\bPODER (EJECUTIVO|LEGISLATIVO|JUDICIAL)\b",
    r"\bDEFENSOR(IA)? DEL PUEBLO\b",
    r"\bPROCURACION (DEL TESORO|GENERAL)\b",
    r"\bADMINISTRACION FEDERAL DE INGRESOS PUBLICOS\b",
    _sigla("AFIP"),
    r"\bDIRECCION GENERAL IMPOSITIVA\b",
    _sigla("DGI"),
    r"\bDIRECCION GENERAL DE ADUANAS\b",
    r"\bADMINISTRACION NACIONAL DE LA SEGURIDAD SOCIAL\b",
    r"\bANSES\b",
    _sigla("ANSES"),
    r"\bFISCO (NACIONAL|DE LA PROVINCIA|PROVINCIAL)\b",
    r"\bESTADO MAYOR (GENERAL )?(DEL EJERCITO|DE LA ARMADA|DE LA FUERZA AEREA)\b",
    r"\b(POLICIA FEDERAL|GENDARMERIA NACIONAL|PREFECTURA NAVAL)\b",
    # órganos judiciales / legislativos
    r"\bJUZGADO (FEDERAL|NACIONAL|DE|EN LO|CIVIL|COMERCIAL|LABORAL|ELECTORAL)\b",
    r"\bTRIBUNAL (ORAL|SUPERIOR|FISCAL|DE CUENTAS|ELECTORAL)\b",
    r"\bCAMARA (NACIONAL|FEDERAL|CONTENCIOSO|EN LO|DE APELACIONES|CRIMINAL|"
    r"NACIONAL ELECTORAL|DE DIPUTADOS|DE SENADORES)\b",
    r"\bCORTE SUPREMA\b",
    r"\bHONORABLE (CAMARA|SENADO|CONCEJO|LEGISLATURA)\b",
    r"\bCONCEJO DELIBERANTE\b",
    r"\bLEGISLATURA DE\b",
    r"\bSENADO DE LA NACION\b",
]

_ORGANISMO = [
    r"\bBANCO CENTRAL\b",
    _sigla("BCRA"),
    r"\bBANCO DE LA NACION\b",
    r"\bBANCO NACION\b",
    r"\bBANCO (DE LA )?PROVINCIA DE\b",
    r"\bBANCO (HIPOTECARIO NACIONAL|DE LA CIUDAD)\b",
    r"\bNACION ARGENTINA ?- ?BANCO\b",
    r"\bUNIVERSIDAD (NACIONAL|DE BUENOS AIRES|TECNOLOGICA NACIONAL|DE LA)\b",
    _sigla("UBA"),
    r"\bINSTITUTO (NACIONAL|PROVINCIAL|DE OBRA SOCIAL|DE SERVICIOS SOCIALES|"
    r"NAC\b)",
    _sigla("INSSJP"),
    _sigla("PAMI"),
    r"\bCAJA (NACIONAL|DE PREVISION|DE JUBILACIONES|COMPLEMENTARIA|FORENSE|"
    r"DE SEGUROS|DE VALORES)\b",
    r"\bOBRA SOCIAL\b",
    _sigla("OSDE"),
    r"\bSUPERINTENDENCIA DE\b",
    r"\bENTE (NACIONAL|REGULADOR|UNICO|PROVINCIAL|COOPERADOR)\b",
    r"\bENARGAS\b",
    _sigla("ENRE"),
    _sigla("CNRT"),
    _sigla("ANMAT"),
    _sigla("AFSCA"),
    _sigla("AABE"),
    r"\bCOMISION (NACIONAL|FEDERAL)\b",
    r"\bAGENCIA (DE ADMINISTRACION|NACIONAL|FEDERAL|GUBERNAMENTAL|DE RECAUDACION)\b",
    r"\bCOLEGIO (PUBLICO|PROFESIONAL|DE ABOGADOS|DE ESCRIBANOS|DE MEDICOS|"
    r"DE MARTILLEROS|DE FARMACEUTICOS|DE INGENIEROS|DE ARQUITECTOS|"
    r"DE CORREDORES|DE BIOQUIMICOS|DE PSICOLOGOS)\b",
    r"\bCONSEJO (PROFESIONAL DE|DE LA MAGISTRATURA|INTERUNIVERSITARIO|NACIONAL|"
    r"FEDERAL|NACIONAL DE INVESTIGACIONES)\b",
    r"\bLOTERIA (NACIONAL|DE)\b",
    r"\bSOCIEDAD DEL ESTADO\b",
    r"\bEMPRESA DEL ESTADO\b",
    _sigla("SE") + r"(?:\s+Y\s+OTRO|\s*$)",  # "… S.E." al final o antes de "y otro"
    r"\bADMINISTRACION (GENERAL DE PUERTOS|DE PARQUES NACIONALES|NACIONAL DE "
    r"MEDICAMENTOS|NACIONAL DE AVIACION)\b",
    r"\b(VIALIDAD NACIONAL|DIRECCION NACIONAL DE VIALIDAD)\b",
    r"\bCORREO (OFICIAL|ARGENTINO)\b",
    r"\bAGUA Y ENERGIA ELECTRICA\b",
    r"\bF\.? ?E\.? ?M\.? ?E\.? ?S\.? ?A\b",  # ferrocarriles
    r"\bSERVICIO (DE CATASTRO|PENITENCIARIO|METEOROLOGICO|NACIONAL)\b",
]

_EMPRESA = [
    _sigla("SACIF") + r"|" + _sigla("SACIFIA") + r"|" + _sigla("SACIFI"),
    _sigla("SACI"),
    _sigla("SAICYF") + r"|" + _sigla("SAIC") + r"|" + _sigla("SAICF"),
    _sigla("SAS"),
    _sigla("SAU"),
    _sigla("SRL"),
    _sigla("SCA"),
    _sigla("SCS"),
    _sigla("SA"),
    _sigla("SH") + r"(?:\s+Y\s+OTRO|\s*$)",
    r"\bSOCIEDAD ANONIMA\b",
    r"\bSOCIEDAD (DE|EN) (RESPONSABILIDAD LIMITADA|COMANDITA)\b",
    r"\bSOCIEDAD COLECTIVA\b",
    r"\bY (CIA|COMPANIA)\b",
    r"\bCIA\.? (DE|ARGENTINA|FINANCIERA|DE SEGUROS)\b",
    r"\bLTDA\b",
    r"\b(LIMITED|INCORPORATED|CORP(ORATION)?)\b",
    _sigla("LLC") + r"|" + _sigla("INC"),
    r"\bCOOPERATIVA\b",
    r"\bCOOP\b",
    r"\bMUTUAL\b",  # entidad civil, pero privada: se agrupa como empresa
    r"\bASEGURADORA\b",
    _sigla("ART") + r"|\bASOCIACION ART\b|\bASEGURADORA DE RIESGOS\b",
    r"\bCOMPANIA (DE|ARGENTINA|FINANCIERA)\b",
    r"\bBANCO\b(?!.*(CENTRAL|NACION|PROVINCIA DE|HIPOTECARIO NACIONAL|DE LA CIUDAD))",
    # sustantivos de actividad comercial (razón social sin sufijo societario)
    r"\b(EDITORIAL|TRANSPORTES?|AUTOMOTORES|INDUSTRIAS?|LABORATORIOS?|"
    r"CONSTRUCTORA|INMOBILIARIA|DISTRIBUIDORA|FRIGORIFICO|SUPERMERCADOS?|"
    r"EXPRESO|LINEAS AEREAS|NAVIERA|PETROLERA|MINERA|TABACALERA|CERVECERIA|"
    r"BODEGAS?|CITRICOLA|AGROPECUARIA|TELEVISORA|RADIODIFUSORA|EMISORA)\b",
]

# "parece un nombre de persona": "Apellido, Nombre" o pocas palabras sin
# ninguna palabra-clave de entidad.
_RE_NN = re.compile(r"^N\.? ?N\.?$|^N\.? ?N\.? ")
_RE_SUCESION = re.compile(r"^SUCESI[OÓ]N(ES)? (DE|AB INTESTATO)\b|^SUCESORES DE\b")
_PALABRAS_ENTIDAD = re.compile(
    r"\b(SOCIEDAD|ASOCIACION|FUNDACION|COOPERATIVA|MUTUAL|INSTITUTO|EMPRESA|"
    r"COMPANIA|CIA|CONSORCIO|FEDERACION|SINDICATO|UNION|CAMARA|COLEGIO|"
    r"CLUB|IGLESIA|PARROQUIA|OBISPADO|MUNICIPALIDAD|PROVINCIA|ESTADO|NACION|"
    r"MINISTERIO|BANCO|UNIVERSIDAD|DIRECCION|ADMINISTRACION|COMISION|CONSEJO|"
    r"ENTE|CAJA|FISCO|GOBIERNO|SUPERINTENDENCIA|PARTIDO|MOVIMIENTO|AGENCIA|"
    r"JUZGADO|TRIBUNAL|LEGISLATURA|SENADO|CONCEJO)\b"
)
_RE_PARENTESIS = re.compile(r"\([^)]*\)")
_RE_PREFIJO_NUM = re.compile(r"^(Y )?\d+ ")

_ESTADO_RE = [re.compile(p) for p in _ESTADO]
_ORGANISMO_RE = [re.compile(p) for p in _ORGANISMO]
_EMPRESA_RE = [re.compile(p) for p in _EMPRESA]


def _parece_persona(norm: str) -> bool:
    base = re.sub(r"\s+Y\s+OTROS?\.?$", "", norm).strip()
    base = _RE_PARENTESIS.sub("", base).strip()  # "Heredia, Gonzalo (24609)"
    base = _RE_PREFIJO_NUM.sub("", base).strip()  # "y 468 ASSUPA" → "ASSUPA"
    base = re.sub(r"\s+P/ S[IÍ]\b.*$", "", base).strip()  # "Pagano Andrea p/ sí …"
    if _RE_NN.match(base) or _RE_SUCESION.match(base):
        return True
    if _PALABRAS_ENTIDAD.search(base):
        return False
    if any(ch.isdigit() for ch in base):
        return False
    if "," in base:
        izquierda = base.split(",", 1)[0].split()
        return 1 <= len(izquierda) <= 3
    palabras = base.split()
    # 1 a 4 palabras, y no un acrónimo suelto ("YPF", "OSDE")
    if not 1 <= len(palabras) <= 4:
        return False
    return not (len(palabras) == 1 and len(palabras[0]) <= 5)


def clasificar_parte(texto: str | None) -> str | None:
    """El tipo de `texto` (un lado de la carátula) o `None` si no se pudo
    clasificar. Ver el docstring del módulo para las categorías y el orden."""
    if not texto or not texto.strip():
        return None
    norm = _norm(texto)
    if any(rx.search(norm) for rx in _ORGANISMO_RE):
        return "organismo"
    if any(rx.search(norm) for rx in _ESTADO_RE):
        return "estado"
    if any(rx.search(norm) for rx in _EMPRESA_RE):
        return "empresa"
    if _parece_persona(norm):
        return "persona_fisica"
    return None
