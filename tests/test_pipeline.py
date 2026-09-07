"""PR-19 — pipeline completo de ingesta como cadena de jobs.

Criterio de aceptación (plan §6): correr el pipeline sobre 2 tomos, cortarlo
a la mitad, reanudarlo y terminar con el mismo resultado que una corrida
limpia.

Los handlers reales (`extraer` / `segmentar` / `estructurar` / `fragmentar`)
se prueban de punta a punta contra el recorte real `tomo348_cuerpo_p31-40.pdf`
(el mismo fixture de PR-08/09/10/11: 3 fallos por el fallback de
delimitadores —no tiene índice de partes, así que `segmentar` cae al plan B—,
uno con voto concurrente de Lorenzetti). La etapa `embeber` usa un
`EmbeddingModel` falso (`_ModeloFalso`, fixture `_modelo_falso` más abajo):
rápido, sin `[embed]` instalado y sin red — la calidad del embedding en sí ya
la prueban `test_embed.py` / `test_vectors.py`, acá lo que importa es que la
etapa mueva los datos donde corresponde.

El criterio de aceptación se prueba dos veces: una con handlers reales sobre
el fixture (compara fallos/secciones/chunks entre una corrida limpia y una
interrumpida) y otra con handlers falsos sobre varios tomos (prueba la
orquestación en sí — bloqueo por `requiere_ocr`, por etapa `fallida`, y la
reanudación — sin pagar el costo de volver a parsear PDFs en cada caso).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spectre.db import Repo, connect, migrate
from spectre.embed.base import EmbeddingModel
from spectre.jobs import Runner, pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "tomo348_cuerpo_p31-40.pdf"


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "spectre.db")
    migrate(c)
    yield c
    c.close()


class _ModeloFalso(EmbeddingModel):
    """Vectores deterministas y baratos: alcanza para que `embeber` /
    `indexar` tengan algo que mover, sin cargar sentence-transformers."""

    nombre = "falso-test"
    dimension = 4

    def embed(self, textos):
        return [[float(len(t) % 7), 0.0, 0.0, 1.0] for t in textos]


@pytest.fixture(autouse=True)
def _modelo_falso(monkeypatch):
    import spectre.embed as embed_pkg

    monkeypatch.setattr(embed_pkg, "cargar_modelo", lambda nombre=None: _ModeloFalso())


@pytest.fixture(autouse=True)
def _vectors_en_tmp(tmp_path, monkeypatch):
    """`embeber`/`indexar` resuelven `vectors_dir` desde la config; sin esto
    escribirían en `data/vectors/` del repo."""
    from spectre.config import get_settings

    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- progreso / siguiente_etapa: funciones puras ------------------------ #


def _tomo_falso(**over):
    from spectre.db.repo import Tomo

    base = dict(
        id=1,
        numero=1,
        volumen=None,
        anio=None,
        csjn_tomo_id=None,
        pdf_path=None,
        sha256=None,
        calidad="desconocida",
        paginas=None,
        offset_pagina=None,
        estado="registrado",
        indexado_at=None,
    )
    base.update(over)
    return Tomo(**base)


def test_progreso_por_estado():
    assert pipeline.progreso(_tomo_falso(estado="registrado")) == (0, 8)
    assert pipeline.progreso(_tomo_falso(estado="segmentado")) == (4, 8)
    assert pipeline.progreso(_tomo_falso(estado="indexado")) == (8, 8)


def test_siguiente_etapa_recorre_las_ocho():
    vistos = []
    tomo = _tomo_falso(estado="registrado")
    while (et := pipeline.siguiente_etapa(tomo)) is not None:
        nombre, destino = et
        vistos.append(nombre)
        tomo = _tomo_falso(estado=destino)
    assert vistos == [nombre for nombre, _ in pipeline.ETAPAS]
    assert pipeline.siguiente_etapa(tomo) is None  # indexado: terminado


def test_siguiente_etapa_se_frena_en_requiere_ocr():
    tomo = _tomo_falso(estado="extraido", calidad="requiere_ocr")
    assert pipeline.siguiente_etapa(tomo) is None


def test_siguiente_etapa_digital_sigue_de_largo():
    tomo = _tomo_falso(estado="extraido", calidad="digital")
    assert pipeline.siguiente_etapa(tomo) == ("limpiar", "limpio")


# --- iniciar_tomo --------------------------------------------------------- #


def test_iniciar_tomo_nuevo_sin_pdf_arranca_registrado(conn):
    tid = pipeline.iniciar_tomo(Repo(conn), numero=348)
    tomo = Repo(conn).get_tomo(tid)
    assert tomo.estado == "registrado"
    assert tomo.pdf_path is None


def test_iniciar_tomo_con_pdf_salta_la_descarga(conn):
    tid = pipeline.iniciar_tomo(Repo(conn), numero=348, pdf_path=str(FIXTURE))
    tomo = Repo(conn).get_tomo(tid)
    assert tomo.estado == "descargado"
    assert tomo.pdf_path == str(FIXTURE)


def test_iniciar_tomo_es_idempotente_y_no_pisa_progreso(conn):
    repo = Repo(conn)
    tid = pipeline.iniciar_tomo(repo, numero=348, csjn_tomo_id="447")
    repo.actualizar_tomo(tid, estado="segmentado")

    otra_vez = pipeline.iniciar_tomo(repo, numero=348, pdf_path=str(FIXTURE))
    assert otra_vez == tid
    tomo = repo.get_tomo(tid)
    assert tomo.estado == "segmentado"  # no lo pisa para atrás
    assert tomo.csjn_tomo_id == "447"  # lo que ya estaba, sigue


def test_iniciar_tomo_completa_pdf_path_si_faltaba_sin_tocar_estado_avanzado(conn):
    repo = Repo(conn)
    tid = pipeline.iniciar_tomo(repo, numero=348)
    repo.actualizar_tomo(tid, estado="descargado")  # como si ya se hubiera bajado
    pipeline.iniciar_tomo(repo, numero=348, pdf_path=str(FIXTURE))
    tomo = repo.get_tomo(tid)
    assert tomo.pdf_path == str(FIXTURE)
    assert tomo.estado == "descargado"  # no lo tocó: ya no estaba en 'registrado'


# --- el pipeline real, de punta a punta sobre el fixture ---------------- #


def _resumen(conn, tomo_id):
    repo = Repo(conn)
    tomo = repo.get_tomo(tomo_id)
    fallos = repo.list_fallos(tomo_id)
    secciones = sum(len(repo.list_secciones_de_fallo(f.id)) for f in fallos)
    return (
        tomo.estado,
        tomo.calidad,
        tuple(sorted(f.cita for f in fallos)),
        tuple(sorted((f.cita, f.fecha, f.jueces) for f in fallos)),
        secciones,
        len(repo.list_chunks_de_tomo(tomo_id)),
        repo.contar_citas_de_tomo(tomo_id),
    )


def test_pipeline_completo_sobre_el_fixture_real(conn):
    tid = pipeline.iniciar_tomo(Repo(conn), numero=348, pdf_path=str(FIXTURE))
    resultado = pipeline.correr_pipeline(conn, [tid])

    tomo = resultado[tid]
    assert tomo.estado == "indexado"
    assert tomo.calidad == "digital"
    assert tomo.indexado_at is not None

    fallos = Repo(conn).list_fallos(tid)
    assert [f.cita for f in fallos] == ["348:31", "348:34", "348:36"]
    # "348:34" (Gobierno de la Ciudad de Buenos Aires) trae el voto
    # concurrente de Lorenzetti (fixture de PR-09).
    voto34 = Repo(conn).list_secciones_de_fallo(fallos[1].id)
    assert {s.tipo for s in voto34} == {"mayoria", "voto"}
    assert Repo(conn).contar_chunks() > 0

    # PR-C1: la etapa `estructurar` volcó las citas salientes a la tabla.
    # El fixture p31-40 tiene 3 referencias `Fallos:` que expanden a 8 citas
    # fallo→fallo (medido con `spectre pdf citations`), repartidas en 2 de los
    # 3 fallos.
    assert Repo(conn).contar_citas_de_tomo(tid) == 8
    con_citas = [f for f in fallos if Repo(conn).list_citas_de_fallo(f.id)]
    assert len(con_citas) == 2

    # PR-C5: `estructurar` también persistió las partes y su tipo. "348:34" es
    # "Gobierno de la Ciudad de Buenos Aires c/ ..." → demandado o actor estado.
    gcba = fallos[1]
    assert gcba.actor or gcba.demandado
    assert "estado" in (gcba.actor_tipo, gcba.demandado_tipo)

    # los jobs de las 7 etapas que hicieron falta (sin "descargar": el tomo
    # ya tenía pdf_path) terminaron hechos.
    tipos_hechos = {
        r["tipo"] for r in conn.execute("SELECT tipo FROM jobs WHERE estado = 'hecho'")
    }
    assert tipos_hechos == {
        f"pipeline.{n}" for n, _ in pipeline.ETAPAS if n != "descargar"
    }


def test_correr_pipeline_es_idempotente(conn):
    tid = pipeline.iniciar_tomo(Repo(conn), numero=348, pdf_path=str(FIXTURE))
    pipeline.correr_pipeline(conn, [tid])
    esperado = _resumen(conn, tid)

    pipeline.correr_pipeline(conn, [tid])  # correrlo de nuevo no cambia nada
    assert _resumen(conn, tid) == esperado
    # y no encoló jobs nuevos: ya está en 'indexado'.
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 7


def test_cortar_a_la_mitad_y_reanudar_da_lo_mismo_que_una_corrida_limpia(tmp_path):
    NUMEROS = (348, 999)  # dos tomos, aunque compartan el mismo PDF de origen

    limpio = connect(tmp_path / "limpio.db")
    migrate(limpio)
    ids_limpio = [
        pipeline.iniciar_tomo(Repo(limpio), numero=n, pdf_path=str(FIXTURE))
        for n in NUMEROS
    ]
    pipeline.correr_pipeline(limpio, ids_limpio)
    esperado = [_resumen(limpio, tid) for tid in ids_limpio]
    limpio.close()

    cortado = connect(tmp_path / "cortado.db")
    migrate(cortado)
    ids = [
        pipeline.iniciar_tomo(Repo(cortado), numero=n, pdf_path=str(FIXTURE))
        for n in NUMEROS
    ]

    runner = Runner(cortado)
    pipeline.registrar_handlers(runner)
    # dos vueltas completas para los dos tomos en lockstep (extraer, limpiar)...
    for _ in range(2):
        for tid in ids:
            pipeline.encolar_siguiente_etapa(runner, tid)
        runner.run()
    # ...a la tercera (segmentar) se encolan los dos, pero el proceso "muere"
    # justo después de reclamar el del primero: sus efectos quedan sin
    # commitear y el segundo ni se llega a reclamar.
    for tid in ids:
        pipeline.encolar_siguiente_etapa(runner, tid)
    reclamado = runner._tomar()
    assert reclamado is not None
    assert reclamado.estado == "en_proceso"

    # proceso nuevo, misma base: retoma los dos tomos desde donde estaban.
    resultado = pipeline.correr_pipeline(cortado, ids)
    obtenido = [_resumen(cortado, tid) for tid in ids]

    assert obtenido == esperado
    assert all(t.estado == "indexado" for t in resultado.values())
    cortado.close()


# --- orquestación con handlers falsos: bloqueos y reanudación ----------- #


def _handler_avanza(estado_destino):
    def h(conn, job):
        Repo(conn, auto_commit=False).actualizar_tomo(
            int(job.payload["tomo_id"]), estado=estado_destino
        )

    return h


def _handlers_falsos():
    return {nombre: _handler_avanza(destino) for nombre, destino in pipeline.ETAPAS}


def test_correr_pipeline_no_reintenta_solo_una_etapa_fallida(conn, monkeypatch):
    def revienta(conn, job):
        raise RuntimeError("boom")

    handlers = _handlers_falsos()
    handlers["fragmentar"] = revienta
    monkeypatch.setattr(pipeline, "_HANDLERS", handlers)

    tid = pipeline.iniciar_tomo(Repo(conn), numero=1, pdf_path="/fake.pdf")
    pipeline.correr_pipeline(conn, [tid], max_intentos=1)

    tomo = Repo(conn).get_tomo(tid)
    assert tomo.estado == "estructurado"  # se frenó antes de fragmentar
    fallidos = conn.execute(
        "SELECT count(*) FROM jobs WHERE tipo = 'pipeline.fragmentar'"
        " AND estado = 'fallido'"
    ).fetchone()[0]
    assert fallidos == 1

    # correrlo de nuevo no reintenta la etapa fallida por su cuenta.
    pipeline.correr_pipeline(conn, [tid], max_intentos=1)
    assert (
        conn.execute(
            "SELECT count(*) FROM jobs WHERE tipo = 'pipeline.fragmentar'"
        ).fetchone()[0]
        == 1
    )
    assert Repo(conn).get_tomo(tid).estado == "estructurado"


def test_correr_pipeline_se_frena_en_requiere_ocr_y_no_sigue(conn, monkeypatch):
    handlers = _handlers_falsos()

    def extraer_como_escaneo(conn, job):
        repo = Repo(conn, auto_commit=False)
        repo.actualizar_tomo(
            int(job.payload["tomo_id"]), estado="extraido", calidad="requiere_ocr"
        )

    handlers["extraer"] = extraer_como_escaneo
    monkeypatch.setattr(pipeline, "_HANDLERS", handlers)

    tid = pipeline.iniciar_tomo(Repo(conn), numero=1, pdf_path="/fake.pdf")
    pipeline.correr_pipeline(conn, [tid])

    tomo = Repo(conn).get_tomo(tid)
    assert tomo.estado == "extraido"
    assert tomo.calidad == "requiere_ocr"
    # ninguna etapa después de extraer se encoló.
    tipos = {r["tipo"] for r in conn.execute("SELECT tipo FROM jobs")}
    assert tipos == {"pipeline.extraer"}


def test_correr_pipeline_varios_tomos_en_paralelo_con_handlers_falsos(
    conn, monkeypatch
):
    monkeypatch.setattr(pipeline, "_HANDLERS", _handlers_falsos())

    ids = [
        pipeline.iniciar_tomo(Repo(conn), numero=n, pdf_path="/fake.pdf")
        for n in (10, 20, 30)
    ]
    resultado = pipeline.correr_pipeline(conn, ids)
    assert all(t.estado == "indexado" for t in resultado.values())
    # siete etapas x tres tomos (sin "descargar": arrancan con pdf_path ya
    # puesto), todas hechas.
    assert (
        conn.execute("SELECT count(*) FROM jobs WHERE estado = 'hecho'").fetchone()[0]
        == 7 * 3
    )
