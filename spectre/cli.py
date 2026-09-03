"""CLI de Spectre.

Estado PR-09: subcomandos reales `config` (rutas resueltas), `db` (migraciones)
y `pdf` (`stats` mide extracción/offset, `clean` mide la limpieza de texto,
`index` parsea el índice por nombres de las partes, `segment` arma los fallos
con su cita, `meta` extrae fecha / jueces / recurso / tribunal / partes,
`sections` parte cada fallo en dictamen / mayoría / votos / disidencias). El
resto existe en `--help` pero **revienta si lo invocás** (D-05).
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Callable, Sequence

from spectre import __version__
from spectre.config import PROJECT_ROOT, get_settings
from spectre.db import connect, migraciones_disponibles, migrate

# subcomando -> PR que lo implementa
_PENDIENTES: dict[str, str] = {
    "ingest": "PR-19",
    "serve": "PR-20",
}


def _cmd_config(_args: argparse.Namespace) -> int:
    s = get_settings()
    filas = [
        ("project_root", PROJECT_ROOT),
        ("data_dir", s.data_dir),
        ("tomos_dir", s.tomos_dir),
        ("db_path", s.db_path),
        ("vectors_dir", s.vectors_dir),
        ("embedding_model", s.embedding_model),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_db_migrate(_args: argparse.Namespace) -> int:
    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    try:
        nuevas = migrate(conn)
    finally:
        conn.close()
    if nuevas:
        print(f"aplicadas en {s.db_path}:")
        for version in nuevas:
            print(f"  {version}")
    else:
        print(f"sin migraciones pendientes ({s.db_path})")
    return 0


def _cmd_db_status(_args: argparse.Namespace) -> int:
    s = get_settings()
    disponibles = [p.stem for p in migraciones_disponibles()]
    print(f"base: {s.db_path}")

    if not s.db_path.exists():
        print("  (la base no existe todavía — corré `spectre db migrate`)")
        for version in disponibles:
            print(f"  [pendiente] {version}")
        return 0

    conn = connect(s.db_path)
    try:
        try:
            aplicadas = {
                row["version"]
                for row in conn.execute("SELECT version FROM _migraciones")
            }
        except sqlite3.OperationalError:
            aplicadas = set()
    finally:
        conn.close()

    if not disponibles:
        print("  (no hay migraciones)")
    for version in disponibles:
        marca = "aplicada " if version in aplicadas else "pendiente"
        print(f"  [{marca}] {version}")
    huerfanas = aplicadas - set(disponibles)
    for version in sorted(huerfanas):
        print(f"  [huérfana ] {version}  (registrada pero sin archivo)")
    return 0


def _cmd_pdf_stats(args: argparse.Namespace) -> int:
    # Import perezoso: pdfplumber es pesado y solo `pdf` lo necesita.
    from spectre.corpus.pdf import calcular_offset, extraer_texto

    paginas = extraer_texto(args.pdf)
    r = calcular_offset(paginas)
    filas = [
        ("pdf", args.pdf),
        ("páginas", r.total),
        ("con nº oficial", f"{r.detectadas}  ({r.cobertura:.1%})"),
        ("offset", r.offset),
        ("consistencia", f"{r.consistentes}/{r.detectadas}  ({r.consistencia:.1%})"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    if r.discrepancias:
        muestra = ", ".join(str(n) for n in r.discrepancias[:15])
        cola = " ..." if len(r.discrepancias) > 15 else ""
        etq = "discrepancias".ljust(ancho)
        print(f"{etq}  {len(r.discrepancias)} en pdf_page {muestra}{cola}")
    return 0


def _cmd_pdf_clean(args: argparse.Namespace) -> int:
    from spectre.corpus.pdf import contar_palabras, extraer_texto, limpiar

    paginas = extraer_texto(args.pdf)
    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    crudas = sum(contar_palabras(p.texto) for p in cuerpo)
    limpias = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    reduccion = (crudas - limpias) / crudas if crudas else 0.0
    filas = [
        ("pdf", args.pdf),
        ("páginas de cuerpo", len(cuerpo)),
        ("palabras crudas", crudas),
        ("palabras limpias", limpias),
        ("reducción", f"{reduccion:.2%}  (des-hifenado)"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    if args.muestra is not None:
        elegida = next((p for p in paginas if p.pdf_page == args.muestra), None)
        if elegida is None:
            raise SystemExit(f"el PDF no tiene pdf_page {args.muestra}")
        print(f"\n--- pdf_page {args.muestra} limpia ---\n{limpiar(elegida.texto)}")
    return 0


def _cmd_pdf_index(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import analizar_indice

    r = analizar_indice(args.pdf)
    citadas = r.paginas_citadas
    filas = [
        ("pdf", args.pdf),
        ("páginas del índice", f"pdf_page {r.paginas_indice[0]}–{r.paginas_indice[1]}"),
        ("carátulas", r.caratulas),
        ("referencias de página", r.referencias),
        ("páginas citadas", f"{min(citadas)}–{max(citadas)}"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    multi = [e for e in r.entradas if len(e.paginas) > 1]
    if multi:
        print(f"\ncarátulas en varios fallos ({len(multi)}):")
        for e in multi:
            paginas = ", ".join(str(p) for p in e.paginas)
            print(f"  [{paginas}]  {e.caratula}")
    if args.muestra is not None:
        print(f"\n--- primeras {args.muestra} entradas ---")
        for e in r.entradas[: args.muestra]:
            paginas = ",".join(str(p) for p in e.paginas)
            print(f"  p.{paginas:<9} {e.caratula}")
    return 0


def _tomo_de_nombre(pdf: str) -> int | None:
    import re
    from pathlib import Path

    m = re.search(r"\d{2,4}", Path(pdf).stem)
    return int(m.group()) if m else None


def _cmd_pdf_segment(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import parsear_indice, segmentar
    from spectre.corpus.pdf import extraer_texto

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    ini, fin = r.cobertura
    metodo = r.metodo + ("  (dudosa)" if r.dudosa else "")
    filas = [
        ("pdf", args.pdf),
        ("método", metodo),
        ("fallos", r.cantidad),
        ("cobertura", f"página {ini} a {fin}"),
        ("solapamientos", len(r.solapamientos)),
        ("huecos", len(r.huecos)),
        ("fallo más largo", f"{r.pagina_mas_larga} páginas"),
        ("mediana", f"{r.mediana_paginas:g} páginas"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    for a, b in r.solapamientos:
        print(f"  solapa: {a} con {b}")
    for a, b in r.huecos:
        print(f"  hueco: entre página {a} y {b}")
    if args.muestra is not None:
        print(f"\n--- primeros {args.muestra} fallos ---")
        for f in r.fallos[: args.muestra]:
            print(f"  Fallos: {f.cita:10} ({f.paginas:>2} pág)  {f.caratula}")
    return 0


def _cmd_pdf_meta(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import (
        extraer_metadatos,
        parsear_indice,
        segmentar,
        texto_del_fallo,
    )
    from spectre.corpus.pdf import extraer_texto

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    metas = []
    for i, f in enumerate(r.fallos):
        siguiente = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=siguiente,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        metas.append((f, extraer_metadatos(texto, caratula=f.caratula)))

    n = len(metas)
    con_fecha = sum(1 for _, m in metas if m.fecha)
    con_jueces = sum(1 for _, m in metas if m.jueces)
    ambos = sum(1 for _, m in metas if m.fecha and m.jueces)
    con_trib = sum(1 for _, m in metas if m.tribunal_origen)
    con_tipo = sum(1 for _, m in metas if m.tipo_recurso)
    con_dem = sum(1 for _, m in metas if m.demandado)
    filas = [
        ("pdf", args.pdf),
        ("fallos", n),
        ("con fecha", f"{con_fecha}/{n}  ({con_fecha / n:.1%})"),
        ("con jueces", f"{con_jueces}/{n}  ({con_jueces / n:.1%})"),
        ("con fecha y jueces", f"{ambos}/{n}  ({ambos / n:.1%})"),
        ("con tribunal origen", f"{con_trib}/{n}  ({con_trib / n:.1%})"),
        ("con tipo de recurso", f"{con_tipo}/{n}  ({con_tipo / n:.1%})"),
        ("con demandado", f"{con_dem}/{n}  (resto: una sola parte)"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")

    sin = [f.cita for f, m in metas if not (m.fecha and m.jueces)]
    if sin:
        print(f"\nsin fecha o jueces ({len(sin)}): {', '.join(sin)}")
    if args.muestra is not None:
        print(f"\n--- primeros {args.muestra} fallos ---")
        for f, m in metas[: args.muestra]:
            print(f"  Fallos: {f.cita}")
            print(f"    fecha:     {m.fecha}")
            print(f"    jueces:    {', '.join(m.jueces) or '—'}")
            print(f"    recurso:   {m.tipo_recurso or '—'}")
            print(f"    t. origen: {m.tribunal_origen or '—'}")
            print(f"    partes:    {m.actor or '—'}  c/  {m.demandado or '—'}")
    return 0


def _cmd_pdf_sections(args: argparse.Namespace) -> int:
    import re

    from spectre.corpus.fallo import (
        parsear_indice,
        partir_secciones,
        segmentar,
        texto_del_fallo,
    )
    from spectre.corpus.pdf import extraer_texto

    marcador = re.compile(
        r"^(FALLO DE LA CORTE SUPREMA|Considerando\s*:|Autos y [Vv]istos.*|"
        r"Suprema Corte\s*:|Dictamen de la Procuraci.*|Vistos( los autos)?.*|"
        r"Resulta\s*:|voto (?:del?|de la|de los)\b.*|"
        r"[Dd]isidencia (?:del?|de la|de los)\b.*|-?[IVX]{1,6}-?\)?\s*$)",
        re.IGNORECASE,
    )

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    if args.cita:
        objetivo = next((f for f in r.fallos if f.cita == args.cita), None)
        if objetivo is None:
            raise SystemExit(f"no hay un fallo con cita {args.cita}")
        i = r.fallos.index(objetivo)
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=objetivo.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        print(f"Fallos: {objetivo.cita}  {objetivo.caratula}\n")
        for s in partir_secciones(texto):
            palabras = len(s.texto.split())
            print(
                f"  [{s.orden}] {s.tipo:11} {s.autor or '—':40} {palabras:5} palabras"
            )
        return 0

    con_dict = con_voto = con_disi = una_sola = 0
    huerfanas = total = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        secciones = partir_secciones(texto)
        tipos = {s.tipo for s in secciones}
        con_dict += "dictamen" in tipos
        con_voto += "voto" in tipos
        con_disi += "disidencia" in tipos
        una_sola += len(secciones) <= 1
        orig = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        cubierto: list[str] = []
        for s in secciones:
            cubierto += [ln.strip() for ln in s.texto.splitlines() if ln.strip()]
        from collections import Counter

        falta = Counter(orig) - Counter(cubierto)
        huerfanas += sum(1 for ln in falta.elements() if not marcador.match(ln))
        total += len(orig)

    n = len(r.fallos)
    filas = [
        ("pdf", args.pdf),
        ("fallos", n),
        ("con dictamen", f"{con_dict}/{n}"),
        ("con >=1 voto", f"{con_voto}/{n}"),
        ("con >=1 disidencia", f"{con_disi}/{n}"),
        ("una sola sección", f"{una_sola}/{n}"),
        (
            "líneas de contenido huérfanas",
            f"{huerfanas}/{total}  ({huerfanas / total:.2%})",
        ),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _hacer_stub(nombre: str, pr: str) -> Callable[[argparse.Namespace], int]:
    def _run(_args: argparse.Namespace) -> int:
        raise SystemExit(
            f"spectre {nombre}: no implementado todavía (llega en {pr}). "
            f"El subcomando existe pero no hace nada aún."
        )

    return _run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectre",
        description="Motor de búsqueda semántica sobre Fallos de la CSJN.",
    )
    parser.add_argument("--version", action="version", version=f"spectre {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<subcomando>")

    p_config = sub.add_parser("config", help="Imprime la configuración resuelta")
    p_config.set_defaults(func=_cmd_config)

    p_db = sub.add_parser("db", help="Esquema SQLite: migraciones y estado")
    db_sub = p_db.add_subparsers(dest="db_command", required=True, metavar="<acción>")
    p_db_migrate = db_sub.add_parser(
        "migrate", help="Aplica las migraciones pendientes (crea la base si falta)"
    )
    p_db_migrate.set_defaults(func=_cmd_db_migrate)
    p_db_status = db_sub.add_parser(
        "status", help="Lista migraciones aplicadas y pendientes"
    )
    p_db_status.set_defaults(func=_cmd_db_status)

    p_pdf = sub.add_parser("pdf", help="Lectura de PDFs de tomos")
    pdf_sub = p_pdf.add_subparsers(
        dest="pdf_command", required=True, metavar="<acción>"
    )
    p_pdf_stats = pdf_sub.add_parser(
        "stats",
        help="Extrae el texto de un tomo y mide cobertura de nº oficial y offset",
    )
    p_pdf_stats.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_stats.set_defaults(func=_cmd_pdf_stats)

    p_pdf_clean = pdf_sub.add_parser(
        "clean",
        help="Limpia el texto del cuerpo y mide la reducción de palabras",
    )
    p_pdf_clean.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_clean.add_argument(
        "--muestra", type=int, metavar="PDF_PAGE", help="imprime esa página ya limpia"
    )
    p_pdf_clean.set_defaults(func=_cmd_pdf_clean)

    p_pdf_index = pdf_sub.add_parser(
        "index",
        help="Parsea el índice por nombres de las partes y cuenta las carátulas",
    )
    p_pdf_index.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_index.add_argument(
        "--muestra", type=int, metavar="N", help="imprime las primeras N entradas"
    )
    p_pdf_index.set_defaults(func=_cmd_pdf_index)

    p_pdf_segment = pdf_sub.add_parser(
        "segment",
        help="Arma los fallos del tomo (rango de página + cita) desde el índice",
    )
    p_pdf_segment.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_segment.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_segment.add_argument(
        "--muestra", type=int, metavar="N", help="imprime los primeros N fallos"
    )
    p_pdf_segment.set_defaults(func=_cmd_pdf_segment)

    p_pdf_meta = pdf_sub.add_parser(
        "meta",
        help="Extrae fecha, jueces, recurso, tribunal y partes de cada fallo",
    )
    p_pdf_meta.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_meta.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_meta.add_argument(
        "--muestra", type=int, metavar="N", help="imprime los primeros N fallos"
    )
    p_pdf_meta.set_defaults(func=_cmd_pdf_meta)

    p_pdf_sections = pdf_sub.add_parser(
        "sections",
        help="Parte cada fallo en dictamen / mayoría / votos / disidencias",
    )
    p_pdf_sections.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_sections.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_sections.add_argument(
        "--cita", help="detalla las secciones de un fallo (ej. 348:113)"
    )
    p_pdf_sections.set_defaults(func=_cmd_pdf_sections)

    for nombre, pr in _PENDIENTES.items():
        p = sub.add_parser(nombre, help=f"(vacío — {pr})")
        p.set_defaults(func=_hacer_stub(nombre, pr))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
