"""CLI de Spectre.

Estado PR-06: subcomandos reales `config` (rutas resueltas), `db` (migraciones)
y `pdf` (`stats` mide extracción/offset, `clean` mide la limpieza de texto,
`index` parsea el índice por nombres de las partes). El resto existe en `--help`
pero **revienta si lo invocás** (D-05).
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
