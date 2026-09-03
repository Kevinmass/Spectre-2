"""CLI de Spectre.

Estado PR-02: subcomandos reales `config` (imprime rutas resueltas) y `db`
(migraciones y estado del esquema). El resto existe en `--help` pero **revienta
si lo invocás**: ningún stub que reporte éxito (D-05).
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
