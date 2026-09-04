"""Arranque de un comando (PR-24): lo que corre después de crear el venv e
instalar el paquete. Baja el modelo de embeddings, intenta indexar un tomo
real de muestra desde la CSJN (para que la primera búsqueda tenga resultados
de verdad, no una base vacía) y levanta el servidor.

Lo invocan `scripts/arrancar.sh` (macOS/Linux) y `scripts/arrancar.ps1`
(Windows) — esos dos solo crean el entorno virtual e instalan el paquete
(`pip install -e ".[embed]"`); todo lo que necesita que `spectre` ya esté
importable vive acá, en Python, para poder testearlo (D-05: nada de esto es
un stub que finja que "arrancó bien" si en realidad falló).

**El paso de indexar un tomo de muestra es best-effort.** El sitio de la
CSJN puede no responder (ya pasó en una sesión anterior, ver bitácora
PR-18) — si falla, no aborta el arranque: Spectre igual levanta, vacío, y
la Biblioteca (PR-23) deja indexar desde ahí en cuanto haya red. Lo que
nunca hace es fingir que el tomo de muestra quedó indexado si no quedó.
"""

from __future__ import annotations

#: El tomo de referencia de todo el proyecto (ver CLAUDE.md, "Fixture de
#: referencia"): 968 páginas, ~126 fallos, números ya verificados contra él
#: en una decena de PRs. Si no está en el catálogo (poco probable, pero el
#: catálogo es un sitio real que puede cambiar), se usa el primero que haya.
_TOMO_PREFERIDO = 348


def _tomo_de_muestra(entradas):
    """Elige qué fila del catálogo de la CSJN indexar de muestra. Ninguna
    entrada -> `None` (catálogo vacío o filtrado a nada, no debería pasar
    con el sitio real, pero no se asume)."""
    for e in entradas:
        if e.numero == _TOMO_PREFERIDO:
            return e
    return entradas[0] if entradas else None


def indexar_tomo_de_muestra() -> bool:
    """Intenta indexar un tomo real de muestra. Devuelve si terminó
    `indexado` de verdad — nunca miente sobre el resultado."""
    try:
        from spectre.corpus.csjn import listar_catalogo

        entradas = listar_catalogo()
    except Exception as e:  # de red: no hay un tipo más específico que atrapar
        print(
            f"No se pudo consultar el catálogo de la CSJN ({e}); "
            "Spectre va a levantar sin tomos indexados. Podés indexar uno "
            "desde la pestaña Biblioteca cuando haya conexión."
        )
        return False

    elegido = _tomo_de_muestra(entradas)
    if elegido is None:
        print(
            "El catálogo de la CSJN no devolvió ningún tomo; Spectre va a "
            "levantar sin tomos indexados."
        )
        return False

    print(
        f"Indexando el Tomo {elegido.numero} de muestra (puede tardar unos minutos)..."
    )
    try:
        from spectre.config import get_settings
        from spectre.db import Repo, connect, migrate
        from spectre.jobs import correr_pipeline, iniciar_tomo

        s = get_settings()
        s.ensure_dirs()
        conn = connect(s.db_path)
        try:
            migrate(conn)
            repo = Repo(conn)
            tomo_id = iniciar_tomo(
                repo, numero=elegido.numero, csjn_tomo_id=elegido.csjn_tomo_id
            )
            resultado = correr_pipeline(conn, [tomo_id])
        finally:
            conn.close()
    except Exception as e:  # de red o de datos: se avisa y se sigue igual
        print(
            f"No se pudo indexar el tomo de muestra ({e}); Spectre igual va "
            "a levantar. Podés indexarlo desde la pestaña Biblioteca."
        )
        return False

    tomo = resultado[tomo_id]
    if tomo.estado == "indexado":
        print(f"Tomo {tomo.numero} indexado: ya hay algo para buscar.")
        return True

    print(
        f"El tomo de muestra quedó en '{tomo.estado}' (no llegó a indexado); "
        "Spectre igual va a levantar. Revisá la pestaña Biblioteca para el detalle."
    )
    return False


def bajar_modelo() -> None:
    """Fuerza la carga real del modelo de embeddings (D-7): la primera vez,
    `sentence-transformers` lo descarga. Hacerlo acá, no en la primera
    búsqueda, es la diferencia entre "el setup tarda un rato" (esperado) y
    "la primera búsqueda de alguien tarda 20 segundos sin aviso" (medido en
    la bitácora de PR-21)."""
    print("Descargando el modelo de embeddings (la primera vez tarda más)...")
    from spectre.embed import cargar_modelo

    _ = cargar_modelo().dimension  # dispara la carga perezosa


def levantar_servidor() -> None:
    print("Levantando Spectre...")
    from spectre.cli import main

    main(["serve"])


def main() -> None:
    bajar_modelo()
    indexar_tomo_de_muestra()
    levantar_servidor()


if __name__ == "__main__":
    import sys

    # Sin esto, stdout queda con buffer de bloque en vez de línea cuando no
    # hay una consola de verdad atrás (medido en la verificación de PR-24:
    # con la salida redirigida a un archivo, "Descargando el modelo..." se
    # quedaba pantalla varios minutos aunque el proceso ya iba mucho más
    # adelante) — cada `print` se ve en el momento, no todos juntos al final.
    sys.stdout.reconfigure(line_buffering=True)
    main()
