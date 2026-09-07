"""Servidor FastAPI (PR-20/21/22/23): estático + estado real + búsqueda
híbrida + vista de fallo + biblioteca.

Sirve `spectre/web/` (HTML/CSS/JS planos, sin build) y expone rutas de solo
lectura:

- `/api/estado`: sin ella, la interfaz no tiene forma de distinguir "no hay
  nada indexado todavía" de "hay resultados pero está mostrando 0" — mostrar
  cualquier cosa que no sea el estado real de la base sería el mismo defecto
  que D-05 (ningún stub que reporte éxito) aplicado a la UI. Desde PR-23
  incluye, por tomo, el progreso del pipeline (`etapas_hechas`/`etapas_
  total`, de `jobs.progreso`) y el error de la última etapa fallida si la
  hay — sin eso, un tomo trabado se ve igual que uno que está progresando.
- `/api/buscar` (PR-21): envuelve `search.buscar_hibrido` (PR-15) para la UI.
  El modelo de embeddings se cachea por instancia de app (cargarlo por
  request sería demasiado lento para el criterio de PR-21, "menos de 3
  segundos"); si `sentence-transformers` no está instalado, degrada sola a
  léxico puro (D-6 no ata la búsqueda a que el modelo real esté disponible)
  y lo dice en la respuesta (`modo`), no lo oculta. Desde PR-A1 la respuesta
  va **agrupada por fallo**: cada resultado es un fallo con sus `pasajes`
  anidados (uno por tipo de sección) y `total_pasajes` para el contador
  "N pasajes más" — antes eran chunks sueltos y una misma sentencia tapaba a
  las demás (relevamiento del plan v2, §2.1). PR-A2 expone en la UI los
  filtros que el backend ya aceptaba (`tribunal`, `seccion`, `solo_lexico`) y
  pasa el de año a rango (`anio_desde` / `anio_hasta`, inclusivos, sueltos o
  combinados).
- `/api/fallos/{cita}` (PR-22 + PR-C1): el fallo completo por secciones +
  metadatos + citas **salientes** (a qué precedentes cita) y **entrantes**
  (qué fallos del corpus indexado lo citan). Desde PR-C1 el pipeline persiste
  las salientes en la tabla `citas` (etapa `estructurar`), así que se leen de
  ahí; si un tomo se indexó antes de PR-C1 y no tiene filas, se recalculan al
  vuelo con `extraer_citas` (PR-10) para no perder la vista —las entrantes, en
  cambio, necesitan el reindexado: no se pueden calcular sin las citas de todos
  los demás fallos ya guardadas—.
- `/api/tomos/{numero}/pdf` (PR-22): sirve el PDF del tomo tal cual está en
  disco, para el enlace "ver en el PDF" de la vista de fallo (D-9: el PDF
  vive en disco, subido a mano o descargado; acá solo se lo expone).

Y dos rutas que escriben (PR-23, biblioteca):

- `POST /api/tomos/{numero}/indexar`: registra el tomo (o retoma uno que ya
  existe, D-9 importador de la CSJN) y corre el pipeline completo
  (`jobs.correr_pipeline`, PR-19) **en segundo plano** (`BackgroundTasks` de
  Starlette — hilo del pool que ya trae el framework, no un worker casero:
  el pipeline puede tardar minutos con el modelo real, y un solo proceso
  FastAPI no puede bloquearse esperando eso sin dejar de atender el resto de
  la UI, incluido el polling de progreso de esta misma corrida). Responde
  202 apenas el tomo queda registrado; el progreso se seguí por `/api/estado`.
- `POST /api/tomos/{numero}/subir`: sube un PDF a mano (D-9) a `data/tomos/`
  y arranca el mismo pipeline en segundo plano, saltando la etapa
  `descargar`.

Ninguna de las dos reintenta sola una etapa que ya falló (D-05, y es el
mismo comportamiento que ya tenía `spectre ingest` desde PR-19) — el `error`
de `/api/estado` está para que la UI lo diga, no para fingir que un click
en "indexar" la destraba.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from spectre.config import get_settings
from spectre.corpus.fallo import extraer_citas
from spectre.db import Repo, Tomo, connect, migrate
from spectre.embed import EmbeddingModel
from spectre.index import IndiceVectorial
from spectre.jobs import correr_pipeline, iniciar_tomo, progreso, siguiente_etapa
from spectre.search import PALABRAS_VACIAS, agrupar_por_fallo, buscar_hibrido

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _error_de_etapa_fallida(conn: sqlite3.Connection, tomo: Tomo) -> dict | None:
    """Si la próxima etapa de `tomo` tiene un job `fallido` como último
    intento, el detalle (`etapa`, `mensaje`) — mismo criterio que
    `cli._cmd_ingest`: un `fallido` no se reintenta solo (D-05), así que la
    UI tiene que poder mostrarlo en vez de un progreso trabado sin
    explicación."""
    pendiente = siguiente_etapa(tomo)
    if pendiente is None:
        return None
    etapa, _ = pendiente
    fila = conn.execute(
        "SELECT error FROM jobs WHERE tipo = ? AND estado = 'fallido'"
        " ORDER BY id DESC LIMIT 1",
        (f"pipeline.{etapa}",),
    ).fetchone()
    if fila is None:
        return None
    return {"etapa": etapa, "mensaje": fila["error"]}


def _tomo_a_dict(conn: sqlite3.Connection, tomo: Tomo) -> dict:
    hechas, total = progreso(tomo)
    return {
        "numero": tomo.numero,
        "estado": tomo.estado,
        "calidad": tomo.calidad,
        "etapas_hechas": hechas,
        "etapas_total": total,
        "error": _error_de_etapa_fallida(conn, tomo),
    }


def _correr_pipeline_en_fondo(db_path: Path, tomo_id: int) -> None:
    """Lo que corre `BackgroundTasks` para `/api/tomos/.../indexar` y
    `/subir`: una conexión propia (la del request ya se cerró para cuando
    esto arranca) y el mismo `correr_pipeline` que usa `spectre ingest`."""
    conn = connect(db_path)
    try:
        correr_pipeline(conn, [tomo_id])
    finally:
        conn.close()


class _IndexarPayload(BaseModel):
    csjn_tomo_id: str | None = None


def _terminos(consulta: str) -> list[str]:
    """Palabras de contenido de la consulta (>=3 letras, sin palabras vacías
    del castellano), para ubicar dónde recortar el extracto — sin filtrar las
    vacías, "responsabilidad del estado" centra el extracto en el primer
    "del". El resaltado de la UI usa su propia lista gemela
    (`PALABRAS_VACIAS` en `app.js`)."""
    vistos: dict[str, None] = {}
    for t in re.findall(r"\w+", consulta.lower()):
        if len(t) > 2 and t not in PALABRAS_VACIAS:
            vistos.setdefault(t, None)
    return list(vistos)


def _borde_palabra_adelante(plano: str, i: int) -> int:
    """La primera posición >= `i` que es principio de palabra (después de un
    espacio, o el final del texto). Sirve para no arrancar un extracto a
    mitad de palabra."""
    n = len(plano)
    i = max(0, min(i, n))
    if i == 0 or i == n or plano[i - 1].isspace():
        return i
    while i < n and not plano[i].isspace():
        i += 1
    while i < n and plano[i].isspace():
        i += 1
    return i


def _borde_palabra_atras(plano: str, i: int) -> int:
    """El principio de la palabra que contiene a `i` (o `i` si ya es
    principio de palabra)."""
    while i > 0 and not plano[i - 1].isspace():
        i -= 1
    return i


def _inicio_de_oracion(plano: str, pos: int, *, max_atras: int) -> int | None:
    """El comienzo de la oración que contiene `pos` (fin de oración = `.`/`?`/
    `!` + espacio + mayúscula, para no cortar en abreviaturas tipo "art. 14"),
    si esa oración empieza a no más de `max_atras` caracteres hacia atrás. Si
    no, `None` — el término está muy adentro de una oración larga y arrancar
    ahí dejaría un extracto sin contexto."""
    desde = max(0, pos - max_atras)
    ultimo = None
    for m in re.finditer(r"[.?!]\s+(?=[A-ZÁÉÍÓÚÜÑ])", plano[desde:pos]):
        ultimo = m
    return desde + ultimo.end() if ultimo is not None else None


def _extracto(texto: str, terminos: list[str], *, ventana: int = 220) -> str:
    """Recorta `texto` (un chunk entero, ~400 palabras) a una ventana de
    ~`ventana` caracteres que incluya, si puede, la primera aparición de
    algún término de la consulta. El corte respeta bordes de palabra (nunca
    arranca a mitad de una) y prefiere el principio de la oración que contiene
    el término si empieza cerca (PR-A4)."""
    plano = " ".join(texto.split())
    n = len(plano)
    if n <= ventana:
        return plano

    bajo = plano.lower()
    pos = None
    for t in terminos:
        i = bajo.find(t)
        if i != -1 and (pos is None or i < pos):
            pos = i

    if pos is None:
        fin = _borde_palabra_atras(plano, ventana) or ventana
        return plano[:fin].rstrip() + "…"

    oracion = _inicio_de_oracion(plano, pos, max_atras=ventana // 2)
    if oracion is not None:
        inicio, limpio = oracion, True
    else:
        inicio = _borde_palabra_adelante(plano, max(0, pos - ventana // 3))
        if inicio > pos:  # nunca dejar el término fuera del extracto
            inicio = _borde_palabra_atras(plano, pos)
        limpio = inicio == 0

    fin = min(n, max(pos + 2 * ventana // 3, inicio + ventana))
    fin = _borde_palabra_atras(plano, fin)
    if fin <= pos:  # ventana degenerada: no recortar de más
        fin = min(n, inicio + ventana)

    prefijo = "" if limpio else "…"
    sufijo = "" if fin >= n else "…"
    return prefijo + plano[inicio:fin].strip() + sufijo


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
            tomos = [_tomo_a_dict(conn, t) for t in repo.list_tomos()]
            return {"tomos": tomos, "chunks": repo.contar_chunks()}
        finally:
            conn.close()

    @app.get("/api/buscar")
    def buscar(
        q: str = Query(..., min_length=1, description="texto a buscar"),
        k: int = Query(10, ge=1, le=50),
        candidatos: int = Query(50, ge=1, le=200),
        anio_desde: int | None = Query(None, ge=1800, le=2200),
        anio_hasta: int | None = Query(None, ge=1800, le=2200),
        tribunal: str | None = None,
        seccion: Literal["mayoria", "voto", "disidencia", "dictamen"] | None = None,
        solo_lexico: bool = False,
    ) -> dict:
        consulta = q.strip()
        if not consulta:
            raise HTTPException(422, "la consulta no puede estar vacía")
        tribunal = tribunal.strip() if tribunal and tribunal.strip() else None

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
            idx_vectorial = IndiceVectorial(s.vectors_dir)
            # Se fusiona hasta `candidatos` chunks (no `k`) y recién después se
            # agrupa: si se cortara en `k` chunks, `k` fallos distintos no
            # entrarían nunca (una sentencia con varios pasajes se comería los
            # lugares). `agrupar_por_fallo` deja los `k` mejores fallos.
            fusionados = buscar_hibrido(
                conn,
                idx_vectorial,
                consulta,
                vector,
                k=candidatos,
                candidatos=candidatos,
                anio_desde=anio_desde,
                anio_hasta=anio_hasta,
                tribunal_origen=tribunal,
                tipo_seccion=seccion,
            )
            agrupados = agrupar_por_fallo(conn, fusionados, limite=k)

            terminos = _terminos(consulta)
            resultados = [
                {
                    "cita": g.cita,
                    "caratula": g.caratula,
                    "fecha": g.fecha,
                    "tribunal_origen": g.tribunal_origen,
                    "score": g.score,
                    "total_pasajes": g.total_pasajes,
                    "pasajes": [
                        {
                            "seccion_tipo": p.seccion_tipo,
                            "seccion_autor": p.seccion_autor,
                            "pagina_oficial": p.pagina_oficial,
                            "extracto": _extracto(p.texto, terminos),
                            "score": p.score,
                        }
                        for p in g.pasajes
                    ],
                }
                for g in agrupados
            ]
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

            # Salientes: de la tabla `citas` (PR-C1). Si el tomo se indexó antes
            # de PR-C1 no hay filas — se recalculan al vuelo, como en PR-22.
            citas = repo.list_citas_de_fallo(fallo.id)
            if not citas:
                citas = extraer_citas(texto_completo)
            entrantes = repo.citas_entrantes(fallo.id)
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
                "citas_entrantes": [
                    {
                        "cita": e.cita,
                        "caratula": e.caratula,
                        "pagina_citada": e.pagina_citada,
                        "contexto": e.contexto,
                    }
                    for e in entrantes
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

    @app.post("/api/tomos/{numero}/indexar", status_code=202)
    def indexar_tomo(
        numero: int, payload: _IndexarPayload, background_tasks: BackgroundTasks
    ) -> dict:
        s = get_settings()
        s.ensure_dirs()
        conn = connect(s.db_path)
        try:
            migrate(conn)
            repo = Repo(conn)
            tomo_id = iniciar_tomo(
                repo, numero=numero, csjn_tomo_id=payload.csjn_tomo_id
            )
            tomo = repo.get_tomo(tomo_id)
            cuerpo = _tomo_a_dict(conn, tomo)
        finally:
            conn.close()

        background_tasks.add_task(_correr_pipeline_en_fondo, s.db_path, tomo_id)
        return cuerpo

    @app.post("/api/tomos/{numero}/subir", status_code=202)
    async def subir_tomo(
        numero: int, background_tasks: BackgroundTasks, archivo: UploadFile
    ) -> dict:
        if not (archivo.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "el archivo tiene que ser un PDF")

        s = get_settings()
        s.ensure_dirs()
        destino = s.tomos_dir / f"{numero}.pdf"
        destino.write_bytes(await archivo.read())

        conn = connect(s.db_path)
        try:
            migrate(conn)
            repo = Repo(conn)
            tomo_id = iniciar_tomo(repo, numero=numero, pdf_path=str(destino))
            tomo = repo.get_tomo(tomo_id)
            cuerpo = _tomo_a_dict(conn, tomo)
        finally:
            conn.close()

        background_tasks.add_task(_correr_pipeline_en_fondo, s.db_path, tomo_id)
        return cuerpo

    # Al final: StaticFiles(html=True) sirve index.html en "/" y es un
    # catch-all, así que las rutas de la API tienen que quedar registradas
    # antes para no perder contra el mount.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
