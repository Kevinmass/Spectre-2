"""Servidor FastAPI (PR-20): estático + un estado real para la UI.

Sirve `spectre/web/` (HTML/CSS/JS planos, sin build) y expone `/api/estado`:
sin eso, la interfaz no tiene forma de distinguir "no hay nada indexado
todavía" de "hay resultados pero está mostrando 0" — mostrar cualquier cosa
que no sea el estado real de la base sería el mismo defecto que D-05
(ningún stub que reporte éxito) aplicado a la UI. La búsqueda en sí y la
gestión de la biblioteca son PR-21/PR-23; acá solo hay lectura.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from spectre.config import get_settings
from spectre.db import Repo, connect

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def crear_app(*, on_startup: Callable[[], None] | None = None) -> FastAPI:
    """Arma la app. `on_startup` corre una vez el socket ya está escuchando
    (lo usa `spectre serve` para abrir el navegador sin adivinar un delay)."""

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        if on_startup is not None:
            on_startup()
        yield

    app = FastAPI(title="Spectre", lifespan=_lifespan)

    @app.get("/api/estado")
    def estado() -> dict:
        s = get_settings()
        if not s.db_path.exists():
            return {"tomos": [], "chunks": 0}
        conn = connect(s.db_path)
        try:
            repo = Repo(conn)
            tomos = [
                {"numero": t.numero, "estado": t.estado, "calidad": t.calidad}
                for t in repo.list_tomos()
            ]
            return {"tomos": tomos, "chunks": repo.contar_chunks()}
        finally:
            conn.close()

    # Al final: StaticFiles(html=True) sirve index.html en "/" y es un
    # catch-all, así que las rutas de la API tienen que quedar registradas
    # antes para no perder contra el mount.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
