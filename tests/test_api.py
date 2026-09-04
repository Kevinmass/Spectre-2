"""PR-20 — servidor FastAPI: estático + `/api/estado` honesto (D-05 aplicado
a la UI: nunca mostrar datos que no estén de verdad en la base)."""

from fastapi.testclient import TestClient

from spectre.api import crear_app
from spectre.config import get_settings


def _cliente() -> TestClient:
    return TestClient(crear_app())


def test_estado_sin_base_da_todo_vacio(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    try:
        r = _cliente().get("/api/estado")
        assert r.status_code == 200
        assert r.json() == {"tomos": [], "chunks": 0}
    finally:
        get_settings.cache_clear()


def test_estado_con_base_vacia_da_cero(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    try:
        from spectre.db import connect, migrate

        s = get_settings()
        s.ensure_dirs()
        conn = connect(s.db_path)
        migrate(conn)
        conn.close()

        r = _cliente().get("/api/estado")
        assert r.status_code == 200
        assert r.json() == {"tomos": [], "chunks": 0}
    finally:
        get_settings.cache_clear()


def test_estado_refleja_tomos_y_chunks_reales(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    get_settings.cache_clear()
    try:
        from spectre.db import Repo, connect, migrate

        s = get_settings()
        s.ensure_dirs()
        conn = connect(s.db_path)
        migrate(conn)
        repo = Repo(conn)
        tomo_id = repo.insert_tomo(348)
        repo.actualizar_tomo(tomo_id, estado="indexado", calidad="digital")
        fallo_id = repo.insert_fallo(tomo_id, "A c/ B", cita="348:1")
        repo.insert_chunks(fallo_id, [(None, i, f"t{i}", None) for i in range(3)])
        conn.close()

        r = _cliente().get("/api/estado")
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["chunks"] == 3
        assert cuerpo["tomos"] == [
            {"numero": 348, "estado": "indexado", "calidad": "digital"}
        ]
    finally:
        get_settings.cache_clear()


def test_index_sirve_el_layout():
    r = _cliente().get("/")
    assert r.status_code == 200
    assert "Spectre" in r.text
    assert "Buscar" in r.text
    assert "Biblioteca" in r.text


def test_sirve_los_estaticos():
    cliente = _cliente()
    assert cliente.get("/style.css").status_code == 200
    assert cliente.get("/app.js").status_code == 200


def test_on_startup_corre_una_vez_el_servidor_esta_listo():
    llamadas = []
    app = crear_app(on_startup=lambda: llamadas.append(True))
    with TestClient(app):
        pass
    assert llamadas == [True]
