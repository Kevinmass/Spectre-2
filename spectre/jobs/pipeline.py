"""Pipeline completo de ingesta, como una cadena de jobs (PR-19).

descargar → extraer → limpiar → segmentar → estructurar → fragmentar →
embeber → indexar. Cada flecha es un job **por etapa, por tomo**, encolado en
la tabla `jobs` (PR-03) — no un job gigante que hace las ocho cosas. Eso es
lo que hace
"reanudable por etapa" real: si el proceso muere a mitad de `fragmentar`, el
runner rescata el job zombi (`recuperar_zombis`) y lo reintenta desde el
principio de esa sola etapa; `descargar`, `extraer`, `limpiar` y `segmentar`
ya quedaron commiteados y no se repiten. Y "progreso consultable" es
`tomos.estado`, que avanza en una sola dirección y se puede leer en cualquier
momento sin tocar la cola.

**Por qué el encadenado no vive dentro de los handlers.** El contrato del
runner (`jobs/runner.py`) prohíbe que un handler llame `commit()`: el runner
es dueño del límite transaccional de *ese* job. Si un handler encolara acá
adentro el job de la etapa siguiente con `Runner.encolar` (que sí commitea),
un job "hecho" podría dejar en la cola un siguiente-job **antes** de que el
propio commit del job actual se confirme — y si el proceso muere en el medio,
ese siguiente job correría sobre datos que el rollback del actual todavía no
escribió. Por eso encadenar es trabajo de `correr_pipeline`, que corre
**fuera** de cualquier handler: encola la etapa que falte para cada tomo,
drena la cola entera (`Runner.run()`), y repite. Cada vuelta solo ve avanzar
`tomos.estado` una vez que el job anterior de verdad terminó (`hecho`).

**Por qué `Repo` necesita `auto_commit=False` acá.** Los handlers sí usan
`db/repo.py` (D-12: todo el acceso a datos pasa por ahí) — pero con
`Repo(conn, auto_commit=False)`, así sus escrituras quedan pendientes hasta
que el runner cierra la transacción del job entero. Ver el docstring de
`Repo` en `db/repo.py`.

**Calidad y D-10.** La etapa `extraer` mide la calidad del tomo (PR-18) y la
guarda en `tomos.calidad`. Un tomo `requiere_ocr` se frena ahí: no hay un
`estado` propio para "en cola de OCR" (no se inventa un valor más para el
CHECK de `tomos.estado`, migración 0004) — la cola visible que pide D-10 es
"todo tomo con `estado='extraido'` y `calidad='requiere_ocr'`", consultable
sin agregar nada al esquema.

**Los vectores no viven en SQLite** (D-5: van en LanceDB). La etapa `embeber`
calcula los embeddings y los sube al índice vectorial en el mismo job que
marca `chunks.modelo_embedding` — es el único lugar donde el vector existe, no
hay dónde dejarlo a medio camino para una etapa `indexar` separada que lo
suba después. `indexar` (la última etapa) por eso no tiene mucho que hacer:
el índice léxico (FTS5) ya se mantiene solo con los triggers de la migración
0003 sobre cada `INSERT` en `chunks` (D-6, PR-14) — nada que empujar ahí.
`indexar` verifica que el índice vectorial tenga un vector por cada chunk del
tomo y recién ahí sella `tomos.estado='indexado'` / `indexado_at`.

**Citas.** El MVP dejó esto sin hacer a propósito (era materia prima del grafo
de precedentes, fuera del MVP, §8.3). **PR-C1 lo termina**: la etapa
`estructurar` corre `extraer_citas` (PR-10) sobre el mismo `texto_del_fallo`
que usa para los metadatos y vuelca el resultado a la tabla `citas` —una fila
por precedente citado—, borrando primero las del fallo para que un reintento no
duplique. No hay etapa ni estado nuevo: la cita es una propiedad estructural
del fallo y sale del texto que `estructurar` ya tiene en la mano.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from spectre.db import Repo, Tomo, ahora_iso
from spectre.jobs.runner import EN_PROCESO, FALLIDO, PENDIENTE, Job, Runner

#: (nombre de la etapa, estado de `tomos` al que llega si termina bien), en
#: orden. El tipo de job es `f"pipeline.{nombre}"`.
ETAPAS: tuple[tuple[str, str], ...] = (
    ("descargar", "descargado"),
    ("extraer", "extraido"),
    ("limpiar", "limpio"),
    ("segmentar", "segmentado"),
    ("estructurar", "estructurado"),
    ("fragmentar", "fragmentado"),
    ("embeber", "embebido"),
    ("indexar", "indexado"),
)

#: `tomos.estado` en el orden que recorre el pipeline; índice i = cuántas
#: etapas ya completó un tomo en ese estado.
_ORDEN_ESTADOS = ("registrado", *[estado for _, estado in ETAPAS])

_TIPO_JOB = {nombre: f"pipeline.{nombre}" for nombre, _ in ETAPAS}


def progreso(tomo: Tomo) -> tuple[int, int]:
    """Cuántas etapas del pipeline completó `tomo`, sobre el total."""
    return _ORDEN_ESTADOS.index(tomo.estado), len(ETAPAS)


def siguiente_etapa(tomo: Tomo) -> tuple[str, str] | None:
    """La próxima `(nombre, estado_destino)` para este tomo, o `None` si ya
    terminó (`indexado`) o está frenado por D-10 (`extraido` +
    `calidad='requiere_ocr'`: no se sigue procesando un escaneo)."""
    if tomo.estado == "indexado":
        return None
    if tomo.estado == "extraido" and tomo.calidad == "requiere_ocr":
        return None
    return ETAPAS[_ORDEN_ESTADOS.index(tomo.estado)]


# --------------------------------------------------------------------------- #
# Helpers de lectura para los handlers (reconstruyen PaginaTexto desde SQLite)
# --------------------------------------------------------------------------- #


def _paginas_texto(repo: Repo, tomo_id: int) -> list:
    from spectre.corpus.pdf import PaginaTexto

    return [
        PaginaTexto(p.pdf_page, p.texto_crudo or "", p.pagina_oficial)
        for p in repo.list_paginas(tomo_id)
    ]


def _paginas_por_oficial(repo: Repo, tomo_id: int) -> dict:
    return {
        p.pagina_oficial: p
        for p in _paginas_texto(repo, tomo_id)
        if p.pagina_oficial is not None
    }


# --------------------------------------------------------------------------- #
# Handlers: uno por etapa. Contrato del runner: reciben (conn, job), escriben
# solo por `conn` (acá, a través de `Repo(conn, auto_commit=False)`) y nunca
# llaman commit()/rollback() — eso lo hace el runner alrededor del handler.
# --------------------------------------------------------------------------- #


def _tomo_o_reventar(repo: Repo, tomo_id: int) -> Tomo:
    tomo = repo.get_tomo(tomo_id)
    if tomo is None:
        raise ValueError(f"no existe el tomo {tomo_id}")
    return tomo


def _h_descargar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.config import get_settings
    from spectre.corpus.csjn import descargar_tomo

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))
    if not tomo.csjn_tomo_id:
        raise ValueError(
            f"tomo {tomo.numero}: sin csjn_tomo_id, no se puede descargar "
            "(usá `spectre ingest --pdf` para subirlo a mano)"
        )
    destino = get_settings().tomos_dir / f"{tomo.numero}.pdf"
    descarga = descargar_tomo(tomo.csjn_tomo_id, destino)
    repo.actualizar_tomo(
        tomo.id,
        pdf_path=str(descarga.ruta),
        sha256=descarga.sha256,
        estado="descargado",
    )


def _h_extraer(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.corpus.pdf import (
        calcular_offset,
        extraer_texto,
        medir_calidad,
        persistir,
    )

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))
    if not tomo.pdf_path:
        raise ValueError(f"tomo {tomo.numero}: sin pdf_path, todavía no se descargó")

    paginas = extraer_texto(tomo.pdf_path)
    persistir(repo, tomo.id, paginas, calcular_offset(paginas))

    calidad = medir_calidad(paginas)
    repo.actualizar_tomo(tomo.id, calidad=calidad.calidad, estado="extraido")


def _h_limpiar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.corpus.pdf import limpiar_tomo

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))
    limpiar_tomo(repo, tomo.id)
    repo.actualizar_tomo(tomo.id, estado="limpio")


def _h_segmentar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.corpus.fallo import parsear_indice, segmentar

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))
    if not tomo.pdf_path:
        raise ValueError(
            f"tomo {tomo.numero}: sin pdf_path, no se puede releer el índice"
        )

    paginas = _paginas_texto(repo, tomo.id)
    try:
        entradas = parsear_indice(tomo.pdf_path)
    except ValueError:
        entradas = None
    resumen = segmentar(entradas, paginas, tomo_numero=tomo.numero)

    repo.borrar_fallos(tomo.id)  # idempotente: un reintento no duplica fallos
    for f in resumen.fallos:
        repo.insert_fallo(
            tomo.id,
            f.caratula,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
            pagina_fin=f.pagina_fin,
        )
    repo.actualizar_tomo(tomo.id, estado="segmentado")


def _h_estructurar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.corpus.fallo import (
        extraer_citas,
        extraer_metadatos,
        texto_del_fallo,
    )

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))

    por_oficial = _paginas_por_oficial(repo, tomo.id)
    if not por_oficial:
        raise ValueError(f"tomo {tomo.numero}: no hay páginas con número oficial")
    fin_cuerpo = max(por_oficial)

    fallos = repo.list_fallos(tomo.id)
    for i, f in enumerate(fallos):
        if f.pagina_inicio is None:
            continue
        siguiente = fallos[i + 1].pagina_inicio if i + 1 < len(fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=siguiente,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        meta = extraer_metadatos(texto, caratula=f.caratula)
        repo.actualizar_fallo(
            f.id,
            fecha=meta.fecha,
            jueces=json.dumps(meta.jueces, ensure_ascii=False),
            tribunal_origen=meta.tribunal_origen,
            tipo_recurso=meta.tipo_recurso,
            actor=meta.actor,
            actor_tipo=meta.actor_tipo,
            demandado=meta.demandado,
            demandado_tipo=meta.demandado_tipo,
        )

        # Citas salientes a precedentes (PR-C1, termina PR-10). Borrar primero:
        # un reintento de esta etapa no debe acumular.
        repo.borrar_citas_de_fallo(f.id)
        citas = extraer_citas(texto)
        if citas:
            repo.insert_citas(
                f.id,
                [(c.tomo_citado, c.pagina_citada, c.contexto) for c in citas],
            )
    repo.actualizar_tomo(tomo.id, estado="estructurado")


def _h_fragmentar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.chunking import fragmentar_fallo
    from spectre.corpus.fallo import partir_secciones, texto_del_fallo_paginado

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))

    por_oficial = _paginas_por_oficial(repo, tomo.id)
    if not por_oficial:
        raise ValueError(f"tomo {tomo.numero}: no hay páginas con número oficial")
    fin_cuerpo = max(por_oficial)

    fallos = repo.list_fallos(tomo.id)
    for i, f in enumerate(fallos):
        if f.pagina_inicio is None or f.cita is None:
            continue
        siguiente = fallos[i + 1].pagina_inicio if i + 1 < len(fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=siguiente,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        secciones = partir_secciones("\n".join(t for _, t in paginado))
        if not secciones:
            continue

        repo.borrar_secciones_de_fallo(f.id)  # idempotente: cascada a chunks
        ids_seccion = repo.insert_secciones(
            f.id, [(s.tipo, s.autor, s.orden, s.texto) for s in secciones]
        )
        chunks = fragmentar_fallo(
            secciones, paginado, cita=f.cita, pagina_inicio=f.pagina_inicio
        )
        repo.insert_chunks(
            f.id,
            [
                (ids_seccion[c.seccion_orden], c.orden, c.texto, c.pagina_oficial)
                for c in chunks
            ],
        )
    repo.actualizar_tomo(tomo.id, estado="fragmentado")


def _h_embeber(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.config import get_settings
    from spectre.embed import cargar_modelo
    from spectre.index import IndiceVectorial

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))

    modelo = cargar_modelo()
    pendientes = [
        c
        for c in repo.list_chunks_de_tomo(tomo.id)
        if c.modelo_embedding != modelo.nombre
    ]
    if pendientes:
        vectores = modelo.embed([c.texto for c in pendientes])
        idx = IndiceVectorial(get_settings().vectors_dir, dimension=modelo.dimension)
        # El índice vectorial es un archivo LanceDB aparte, no la transacción
        # SQLite de este job (D-5: los vectores no viven en la base). `upsert`
        # es idempotente (merge_insert por chunk_id, PR-13): si el job muere
        # justo después de esta línea y antes del commit de más abajo, un
        # reintento recalcula y vuelve a subir los mismos vectores sin
        # duplicar filas en LanceDB — trabajo repetido, no dato corrupto.
        idx.upsert(
            (c.id, v, modelo.nombre) for c, v in zip(pendientes, vectores, strict=True)
        )
        repo.marcar_chunks_embebidos([c.id for c in pendientes], modelo.nombre)
    repo.actualizar_tomo(tomo.id, estado="embebido")


def _h_indexar(conn: sqlite3.Connection, job: Job) -> None:
    from spectre.config import get_settings
    from spectre.index import IndiceVectorial

    repo = Repo(conn, auto_commit=False)
    tomo = _tomo_o_reventar(repo, int(job.payload["tomo_id"]))

    chunk_ids = {c.id for c in repo.list_chunks_de_tomo(tomo.id)}
    if chunk_ids:
        idx = IndiceVectorial(get_settings().vectors_dir)
        faltan = chunk_ids - idx.ids()
        if faltan:
            raise RuntimeError(
                f"tomo {tomo.numero}: {len(faltan)} chunks sin vector en el "
                "índice vectorial (la etapa 'embeber' no terminó bien)"
            )
    # El índice léxico (FTS5) se mantiene solo: los triggers de la migración
    # 0003 lo sincronizan en cada INSERT sobre `chunks` (D-6). Nada que hacer
    # acá para ese lado.
    repo.actualizar_tomo(tomo.id, estado="indexado", indexado_at=ahora_iso())


_HANDLERS = {
    "descargar": _h_descargar,
    "extraer": _h_extraer,
    "limpiar": _h_limpiar,
    "segmentar": _h_segmentar,
    "estructurar": _h_estructurar,
    "fragmentar": _h_fragmentar,
    "embeber": _h_embeber,
    "indexar": _h_indexar,
}


def registrar_handlers(runner: Runner) -> None:
    """Registra las ocho etapas en `runner`. Un `Runner` nuevo por corrida
    (no se puede registrar el mismo tipo dos veces, `jobs/runner.py`)."""
    for nombre, tipo in _TIPO_JOB.items():
        runner.registrar(tipo, _HANDLERS[nombre])


# --------------------------------------------------------------------------- #
# Orquestación: registrar un tomo, encolar su próxima etapa, correr todo.
# --------------------------------------------------------------------------- #


def iniciar_tomo(
    repo: Repo,
    *,
    numero: int,
    pdf_path: str | None = None,
    csjn_tomo_id: str | None = None,
) -> int:
    """Registra el tomo si no existía, o completa `pdf_path` /
    `csjn_tomo_id` si faltaban, sin pisar el progreso que ya tenga. Con
    `pdf_path` (subida manual, D-9) el tomo arranca directo en `descargado`:
    no hace falta la etapa `descargar`. Se llama con un `Repo` normal
    (`auto_commit=True`): es código de arranque, no un handler."""
    tomo = repo.get_tomo_por_numero(numero)
    if tomo is None:
        estado_inicial = "descargado" if pdf_path else "registrado"
        return repo.insert_tomo(
            numero,
            csjn_tomo_id=csjn_tomo_id,
            pdf_path=pdf_path,
            estado=estado_inicial,
        )

    campos: dict[str, object] = {}
    if pdf_path and not tomo.pdf_path:
        campos["pdf_path"] = pdf_path
        if tomo.estado == "registrado":
            campos["estado"] = "descargado"
    if csjn_tomo_id and not tomo.csjn_tomo_id:
        campos["csjn_tomo_id"] = csjn_tomo_id
    if campos:
        repo.actualizar_tomo(tomo.id, **campos)
    return tomo.id


def _estado_del_ultimo_job(
    conn: sqlite3.Connection, tipo: str, tomo_id: int
) -> str | None:
    """El `estado` de la corrida más reciente de `tipo` para este tomo, o
    `None` si nunca se encoló. No usa `json_extract` (evita depender de que
    el SQLite del sistema traiga compilado JSON1): trae los jobs del tipo y
    mira el payload ya parseado, en Python."""
    filas = conn.execute(
        "SELECT payload, estado FROM jobs WHERE tipo = ? ORDER BY id DESC", (tipo,)
    )
    for fila in filas:
        payload = json.loads(fila["payload"]) if fila["payload"] else {}
        if payload.get("tomo_id") == tomo_id:
            return str(fila["estado"])
    return None


def encolar_siguiente_etapa(runner: Runner, tomo_id: int) -> str | None:
    """Encola el job de la próxima etapa que le falte a `tomo_id`, si no hay
    ya uno en cola/corriendo y la etapa no falló antes (un `fallido` no se
    reintenta solo: hace falta un `spectre ingest` explícito después de
    arreglar lo que rompió). Devuelve el nombre de la etapa encolada, o
    `None` si no encoló nada (terminado, frenado por D-10, o ya en curso)."""
    repo = Repo(runner.conn)
    tomo = _tomo_o_reventar(repo, tomo_id)
    etapa = siguiente_etapa(tomo)
    if etapa is None:
        return None
    nombre, _ = etapa
    tipo = _TIPO_JOB[nombre]
    if _estado_del_ultimo_job(runner.conn, tipo, tomo_id) in (
        PENDIENTE,
        EN_PROCESO,
        FALLIDO,
    ):
        return None
    runner.encolar(tipo, {"tomo_id": tomo_id})
    return nombre


def correr_pipeline(
    conn: sqlite3.Connection,
    tomos_ids: Iterable[int],
    *,
    max_intentos: int = 3,
) -> dict[int, Tomo]:
    """Corre el pipeline completo sobre estos tomos: encola la etapa que le
    falta a cada uno, drena la cola, repite. Reanudable por construcción —
    volver a llamarla (mismo proceso o uno nuevo) retoma desde `tomos.estado`,
    que es lo único que hace falta para saber qué falta: no hay estado de la
    corrida en memoria. Devuelve el `Tomo` final de cada uno."""
    runner = Runner(conn, max_intentos=max_intentos)
    registrar_handlers(runner)
    tomos_ids = list(tomos_ids)
    repo = Repo(conn)

    for _ in ETAPAS:  # a lo sumo una vuelta por etapa: 8 rondas alcanzan
        for tomo_id in tomos_ids:
            encolar_siguiente_etapa(runner, tomo_id)
        runner.run()
        # Ojo: el corte no puede depender de si esta vuelta encoló algo
        # *nuevo* — un job que ya estaba en cola de una corrida anterior
        # (reanudación) hace progreso real sin que `encolar_siguiente_etapa`
        # devuelva nada. Lo que importa es si a alguien todavía le queda
        # etapa por delante.
        if all(
            siguiente_etapa(repo.get_tomo(tomo_id)) is None for tomo_id in tomos_ids
        ):
            break

    return {tomo_id: repo.get_tomo(tomo_id) for tomo_id in tomos_ids}
