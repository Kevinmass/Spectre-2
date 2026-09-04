"""Servidor FastAPI (PR-20/21/22): estático + estado real + búsqueda híbrida
+ vista de fallo.

Sirve `spectre/web/` (HTML/CSS/JS planos, sin build) y expone rutas de solo
lectura:

- `/api/estado`: sin ella, la interfaz no tiene forma de distinguir "no hay
  nada indexado todavía" de "hay resultados pero está mostrando 0" — mostrar
  cualquier cosa que no sea el estado real de la base sería el mismo defecto
  que D-05 (ningún stub que reporte éxito) aplicado a la UI.
- `/api/buscar` (PR-21): envuelve `search.buscar_hibrido` (PR-15) para la UI.
  El modelo de embeddings se cachea por instancia de app (cargarlo por
  request sería demasiado lento para el criterio de PR-21, "menos de 3
  segundos"); si `sentence-transformers` no está instalado, degrada sola a
  léxico puro (D-6 no ata la búsqueda a que el modelo real esté disponible)
  y lo dice en la respuesta (`modo`), no lo oculta.
- `/api/fallos/{cita}` (PR-22): el fallo completo por secciones + metadatos +
  citas salientes. Las citas se recalculan sobre el texto ya persistido
  (`extraer_citas`, PR-10) porque el pipeline (PR-19) decidió a propósito no
  guardarlas — son la materia prima de un grafo de precedentes que el plan
  deja fuera del MVP (§8.3) — así que la única forma honesta de mostrarlas es
  calcularlas al vuelo, no inventar una tabla que nadie llena.
- `/api/tomos/{numero}/pdf` (PR-22): sirve el PDF del tomo tal cual está en
  disco, para el enlace "ver en el PDF" de la vista de fallo (D-9: el PDF
  vive en disco, subido a mano o descargado; acá solo se lo expone).

La gestión de la biblioteca (subir/indexar tomos desde la UI) es PR-23.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spectre.config import get_settings
from spectre.corpus.fallo import extraer_citas
from spectre.db import Repo, connect
from spectre.embed import EmbeddingModel
from spectre.index import IndiceVectorial
from spectre.search import buscar_hibrido

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _terminos(consulta: str) -> list[str]:
    """Palabras de >=3 letras de la consulta, para ubicar dónde recortar el
    extracto. La misma lista se le manda a la UI para resaltar (D-4: se
    resalta lo que el usuario pidió, no lo que el ranking decidió)."""
    vistos: dict[str, None] = {}
    for t in re.findall(r"\w+", consulta.lower()):
        if len(t) > 2:
            vistos.setdefault(t, None)
    return list(vistos)


def _extracto(texto: str, terminos: list[str], *, ventana: int = 220) -> str:
    """Recorta `texto` (un chunk entero, ~400 palabras) a una ventana que
    incluya, si puede, la primera aparición de algún término de la consulta
    — sin eso, un extracto de las primeras 220 letras a veces no contiene ni
    una palabra buscada."""
    plano = " ".join(texto.split())
    bajo = plano.lower()
    pos = None
    for t in terminos:
        i = bajo.find(t)
        if i != -1 and (pos is None or i < pos):
            pos = i

    if pos is None:
        recorte = plano[:ventana]
        return recorte + ("…" if len(plano) > ventana else "")

    inicio = max(0, pos - ventana // 3)
    fin = min(len(plano), inicio + ventana)
    prefijo = "…" if inicio > 0 else ""
    sufijo = "…" if fin < len(plano) else ""
    return prefijo + plano[inicio:fin] + sufijo


def crear_app(*, on_startup: Callable[[], None] | None = None) -> FastAPI:
    """Arma la app. `on_startup` corre una vez el socket ya está escuchando
    (lo usa `spectre serve` para abrir el navegador sin adivinar un delay)."""

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        if on_startup is not None:
            on_startup()
        yield

    app = FastAPI(title="Spectre", lifespan=_lifespan)

    # Cachea el modelo de embeddings por instancia de app (no por request:
    # cargarlo de nuevo cada vez rompería el criterio de PR-21). Cada
    # `crear_app()` arranca con su propio caché — los tests no se pisan.
    _modelo_cache: dict[str, EmbeddingModel] = {}

    def _modelo() -> EmbeddingModel:
        if "modelo" not in _modelo_cache:
            from spectre.embed import cargar_modelo

            _modelo_cache["modelo"] = cargar_modelo()
        return _modelo_cache["modelo"]

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

    @app.get("/api/buscar")
    def buscar(
        q: str = Query(..., min_length=1, description="texto a buscar"),
        k: int = Query(10, ge=1, le=50),
        candidatos: int = Query(50, ge=1, le=200),
        anio: int | None = None,
        tribunal: str | None = None,
        seccion: Literal["mayoria", "voto", "disidencia", "dictamen"] | None = None,
        solo_lexico: bool = False,
    ) -> dict:
        consulta = q.strip()
        if not consulta:
            raise HTTPException(422, "la consulta no puede estar vacía")

        s = get_settings()
        if not s.db_path.exists():
            return {"consulta": consulta, "modo": "sin_datos", "resultados": []}

        vector: list[float] | None = None
        modo = "solo_lexico"
        if not solo_lexico:
            try:
                vector = _modelo().embed_uno(consulta)
                modo = "hibrido"
            except ModuleNotFoundError:
                # sentence-transformers no está instalado: D-6 no ata la
                # búsqueda a que el modelo real esté disponible. Se avisa en
                # `modo`, no se finge que hubo búsqueda semántica (D-05).
                vector = None

        conn: sqlite3.Connection = connect(s.db_path)
        try:
            repo = Repo(conn)
            idx_vectorial = IndiceVectorial(s.vectors_dir)
            fusionados = buscar_hibrido(
                conn,
                idx_vectorial,
                consulta,
                vector,
                k=k,
                candidatos=candidatos,
                anio=anio,
                tribunal_origen=tribunal,
                tipo_seccion=seccion,
            )

            terminos = _terminos(consulta)
            resultados = []
            for r in fusionados:
                chunk = repo.get_chunk(r.chunk_id)
                if chunk is None:
                    continue
                fallo = repo.get_fallo(chunk.fallo_id)
                seccion_fila = (
                    repo.get_seccion(chunk.seccion_id)
                    if chunk.seccion_id is not None
                    else None
                )
                resultados.append(
                    {
                        "cita": fallo.cita if fallo else None,
                        "caratula": fallo.caratula if fallo else None,
                        "fecha": fallo.fecha if fallo else None,
                        "seccion_tipo": seccion_fila.tipo if seccion_fila else None,
                        "seccion_autor": seccion_fila.autor if seccion_fila else None,
                        "pagina_oficial": chunk.pagina_oficial,
                        "extracto": _extracto(chunk.texto, terminos),
                        "score": r.score,
                    }
                )
            return {"consulta": consulta, "modo": modo, "resultados": resultados}
        finally:
            conn.close()

    @app.get("/api/fallos/{cita}")
    def fallo_detalle(cita: str) -> dict:
        s = get_settings()
        if not s.db_path.exists():
            raise HTTPException(404, f"no hay ningún fallo con cita {cita}")

        conn = connect(s.db_path)
        try:
            repo = Repo(conn)
            fallo = repo.get_fallo_por_cita(cita)
            if fallo is None:
                raise HTTPException(404, f"no hay ningún fallo con cita {cita}")

            tomo = repo.get_tomo(fallo.tomo_id)
            secciones = repo.list_secciones_de_fallo(fallo.id)
            texto_completo = "\n".join(sec.texto for sec in secciones if sec.texto)
            citas = extraer_citas(texto_completo)
            pdf_path = Path(tomo.pdf_path) if tomo and tomo.pdf_path else None

            return {
                "cita": fallo.cita,
                "caratula": fallo.caratula,
                "fecha": fallo.fecha,
                "tribunal_origen": fallo.tribunal_origen,
                "tipo_recurso": fallo.tipo_recurso,
                "jueces": json.loads(fallo.jueces) if fallo.jueces else [],
                "tomo_numero": tomo.numero if tomo else None,
                "pagina_inicio": fallo.pagina_inicio,
                "pagina_fin": fallo.pagina_fin,
                "offset_pagina": tomo.offset_pagina if tomo else None,
                "pdf_disponible": bool(pdf_path and pdf_path.is_file()),
                "secciones": [
                    {
                        "tipo": sec.tipo,
                        "autor": sec.autor,
                        "orden": sec.orden,
                        "texto": sec.texto,
                    }
                    for sec in secciones
                ],
                "citas_salientes": [
                    {
                        "tomo_citado": c.tomo_citado,
                        "pagina_citada": c.pagina_citada,
                        "contexto": c.contexto,
                    }
                    for c in citas
                ],
            }
        finally:
            conn.close()

    @app.get("/api/tomos/{numero}/pdf")
    def pdf_tomo(numero: int) -> FileResponse:
        s = get_settings()
        if not s.db_path.exists():
            raise HTTPException(404, f"no existe el tomo {numero}")

        conn = connect(s.db_path)
        try:
            tomo = Repo(conn).get_tomo_por_numero(numero)
        finally:
            conn.close()

        if tomo is None:
            raise HTTPException(404, f"no existe el tomo {numero}")
        if not tomo.pdf_path or not Path(tomo.pdf_path).is_file():
            raise HTTPException(
                404, f"el PDF del tomo {numero} no está disponible en este servidor"
            )
        return FileResponse(tomo.pdf_path, media_type="application/pdf")

    # Al final: StaticFiles(html=True) sirve index.html en "/" y es un
    # catch-all, así que las rutas de la API tienen que quedar registradas
    # antes para no perder contra el mount.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
