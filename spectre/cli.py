"""CLI de Spectre.

Estado PR-01: el único subcomando que hace algo es `config`, que imprime las
rutas resueltas (sirve para verificar D-02 a ojo). El resto existe en
`--help` pero **revienta si lo invocás**: ningún stub que reporte éxito.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from spectre import __version__
from spectre.config import PROJECT_ROOT, get_settings

# subcomando -> PR que lo implementa
_PENDIENTES: dict[str, str] = {
    "db": "PR-02",
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
