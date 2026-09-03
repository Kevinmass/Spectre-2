"""Humo mínimo: el paquete importa y expone su versión.

No es un placeholder de funcionalidad futura; es el test que hace que la suite
y el CI existan desde PR-00 (defecto D-01 del proyecto anterior).
"""

import spectre


def test_paquete_importa_con_version():
    assert isinstance(spectre.__version__, str)
    assert spectre.__version__
