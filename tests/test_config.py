"""PR-01 — la config no depende del CWD (defecto D-02)."""

from spectre.config import PROJECT_ROOT, Settings, get_settings


def test_data_dir_es_absoluta_y_cuelga_del_root():
    s = Settings()
    assert s.data_dir.is_absolute()
    assert s.data_dir == PROJECT_ROOT / "data"


def test_config_identica_desde_cualquier_cwd(tmp_path, monkeypatch):
    # D-02: `base_path: "."` creaba las carpetas de datos donde estuvieras parado.
    monkeypatch.chdir(PROJECT_ROOT)
    desde_root = Settings().data_dir

    sub = tmp_path / "un" / "lado" / "cualquiera"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    desde_otro_lado = Settings().data_dir

    assert desde_root == desde_otro_lado == PROJECT_ROOT / "data"


def test_rutas_derivadas():
    s = Settings()
    assert s.tomos_dir == PROJECT_ROOT / "data" / "tomos"
    assert s.db_path == PROJECT_ROOT / "data" / "spectre.db"
    assert s.vectors_dir == PROJECT_ROOT / "data" / "vectors"


def test_data_dir_relativa_por_env_se_ancla_al_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECTRE_DATA_DIR", "datos_alternativos")
    monkeypatch.chdir(tmp_path)
    assert Settings().data_dir == (PROJECT_ROOT / "datos_alternativos").resolve()


def test_data_dir_absoluta_por_env_se_respeta(monkeypatch, tmp_path):
    destino = tmp_path / "datos"
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(destino))
    assert Settings().data_dir == destino


def test_ensure_dirs_crea_bajo_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(tmp_path / "datos"))
    s = Settings()
    assert not s.tomos_dir.exists()
    s.ensure_dirs()
    assert s.data_dir.is_dir()
    assert s.tomos_dir.is_dir()
    assert s.vectors_dir.is_dir()


def test_get_settings_es_cacheado():
    assert get_settings() is get_settings()
