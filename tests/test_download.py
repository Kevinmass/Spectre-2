"""PR-17 — descargador de tomos CSJN (D-9 del plan).

Criterio de aceptación (plan §6): descargar 3 tomos, verificar hashes,
reanudar una descarga cortada.

`test_descargar_tomo_*` y `test_descargar_varios_*` inyectan `descargar_a`
(sin red, instantáneos): prueban caché, reintentos/backoff y el descarte del
`.partial` viejo. `test_aceptacion` (marca `red`) hace las tres cosas del
criterio de aceptación de verdad, contra el sitio real de la CSJN.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from spectre.corpus.csjn.download import Descarga, descargar_tomo, descargar_varios


def _fake_ok(contenido: bytes):
    def _f(_url: str, destino_parcial: Path) -> None:
        destino_parcial.write_bytes(contenido)

    return _f


def test_descargar_tomo_baja_y_calcula_hash(tmp_path):
    contenido = b"%PDF-1.4 contenido de prueba"
    destino = tmp_path / "1.pdf"

    r = descargar_tomo("1", destino, descargar_a=_fake_ok(contenido))

    assert isinstance(r, Descarga)
    assert r.ruta == destino
    assert destino.read_bytes() == contenido
    assert r.bytes == len(contenido)
    assert r.sha256 == hashlib.sha256(contenido).hexdigest()
    assert r.reutilizada is False
    assert not destino.with_name(destino.name + ".partial").exists()


def test_descargar_tomo_usa_cache_si_ya_existe(tmp_path):
    destino = tmp_path / "1.pdf"
    destino.write_bytes(b"ya estaba aca")

    def _no_deberia_llamarse(_url, _destino_parcial):
        raise AssertionError("no debería pedir nada: el destino ya existe")

    r = descargar_tomo("1", destino, descargar_a=_no_deberia_llamarse)

    assert r.reutilizada is True
    assert r.sha256 == hashlib.sha256(b"ya estaba aca").hexdigest()


def test_descargar_tomo_forzar_ignora_cache(tmp_path):
    destino = tmp_path / "1.pdf"
    destino.write_bytes(b"viejo")

    r = descargar_tomo("1", destino, forzar=True, descargar_a=_fake_ok(b"nuevo"))

    assert r.reutilizada is False
    assert destino.read_bytes() == b"nuevo"


def test_descargar_tomo_reintenta_y_se_recupera(tmp_path):
    destino = tmp_path / "1.pdf"
    llamadas = []

    def _falla_dos_veces(_url, destino_parcial):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise OSError("simulando un corte de red")
        destino_parcial.write_bytes(b"al final llego")

    r = descargar_tomo("1", destino, intentos=3, espera=0, descargar_a=_falla_dos_veces)

    assert len(llamadas) == 3
    assert r.reutilizada is False
    assert destino.read_bytes() == b"al final llego"


def test_descargar_tomo_agota_intentos_revienta_sin_dejar_basura(tmp_path):
    destino = tmp_path / "1.pdf"

    def _siempre_falla(_url, _destino_parcial):
        raise OSError("la red no anda")

    with pytest.raises(ConnectionError):
        descargar_tomo("1", destino, intentos=3, espera=0, descargar_a=_siempre_falla)

    assert not destino.exists()
    assert not destino.with_name(destino.name + ".partial").exists()


def test_descargar_tomo_descarta_un_parcial_viejo_de_una_corrida_anterior(tmp_path):
    # simula el proceso cortado a mitad: quedó un .partial con basura de una
    # corrida anterior, y el destino final nunca se completó.
    destino = tmp_path / "1.pdf"
    parcial = destino.with_name(destino.name + ".partial")
    parcial.write_bytes(b"esto quedo a medio bajar y esta corrupto")

    r = descargar_tomo("1", destino, descargar_a=_fake_ok(b"descarga completa"))

    assert destino.read_bytes() == b"descarga completa"
    assert not parcial.exists()
    assert r.sha256 == hashlib.sha256(b"descarga completa").hexdigest()


def test_descargar_varios_pausa_entre_tomos_pero_no_al_final(tmp_path, monkeypatch):
    pausas: list[float] = []
    monkeypatch.setattr(
        "spectre.corpus.csjn.download.time.sleep", lambda s: pausas.append(s)
    )

    pedidos = [
        ("1", tmp_path / "1.pdf"),
        ("2", tmp_path / "2.pdf"),
        ("3", tmp_path / "3.pdf"),
    ]
    resultados = descargar_varios(
        pedidos, pausa_entre_tomos=2.5, descargar_a=_fake_ok(b"x")
    )

    assert len(resultados) == 3
    assert all(not r.reutilizada for r in resultados)
    assert pausas == [2.5, 2.5]  # entre 1-2 y 2-3, no después del último


# --- aceptación: contra el sitio real de la CSJN ------------------------- #

# 347-I, 349-I, 346-I: tomos modernos y chicos (~3 MB), rápidos de bajar.
_TOMO_IDS_ACEPTACION = ["443", "447", "441"]


@pytest.mark.red
def test_aceptacion(tmp_path):
    pedidos = [(tid, tmp_path / f"{tid}.pdf") for tid in _TOMO_IDS_ACEPTACION]

    # 1. descargar 3 tomos
    resultados = descargar_varios(pedidos, pausa_entre_tomos=0.5)
    assert len(resultados) == 3
    assert all(not r.reutilizada for r in resultados)

    # 2. verificar hashes: el sha256 devuelto es el del contenido real en
    # disco, y cada uno arranca con la cabecera de un PDF de verdad.
    for r in resultados:
        assert r.bytes > 0
        assert r.ruta.read_bytes()[:5] == b"%PDF-"
        assert r.sha256 == hashlib.sha256(r.ruta.read_bytes()).hexdigest()

    # una segunda corrida sobre los mismos destinos no vuelve a pedir nada
    repetido = descargar_varios(pedidos, pausa_entre_tomos=0.5)
    assert all(r.reutilizada for r in repetido)
    assert [r.sha256 for r in repetido] == [r.sha256 for r in resultados]

    # 3. reanudar una descarga cortada: se borra el destino final de uno de
    # los tres y se deja un .partial con basura, simulando el proceso
    # cortado a mitad de esa descarga puntual.
    tid, destino = pedidos[0]
    destino.unlink()
    parcial = destino.with_name(destino.name + ".partial")
    parcial.write_bytes(b"esto es basura de una descarga cortada a mitad")

    reanudado = descargar_tomo(tid, destino)

    assert not parcial.exists()
    assert destino.read_bytes()[:5] == b"%PDF-"
    assert reanudado.sha256 == resultados[0].sha256  # el mismo tomo de antes
