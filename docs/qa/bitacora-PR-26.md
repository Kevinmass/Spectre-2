# Bitácora PR-26 — Documentación de uso

## Qué pedía el plan

README real y una guía corta escrita para una abogada, no para un dev.
*Acepta:* alguien que no vio el proyecto puede instalarlo y buscar.

## Qué se hizo

- **`README.md`**: reemplaza el stub que decía "en reconstrucción... el
  README de uso llega en PR-26" (así quedó desde PR-00). Ahora tiene:
  qué es Spectre en dos párrafos, instalación real con los scripts de
  PR-24 (`scripts\arrancar.ps1` / `scripts/arrancar.sh`, que ya hacían todo
  el trabajo pero no estaban documentados fuera del propio script), uso
  diario (volver a abrir Spectre), desarrollo (venv, `pip install -e
  ".[dev]"`, `ruff`, `pytest`, y la mención de `[embed]` para que quede
  claro por qué existe la degradación a léxico puro), y enlaces a
  `docs/plan-spectre.md` y `docs/guia-uso.md`.
- **`docs/guia-uso.md`** (nuevo): la guía para quien no programa. Spectre
  se hizo originalmente para la hermana de Kevin, abogada (§0 del plan),
  así que el destinatario real de este documento no es hipotético. Cubre:
  cómo abrir Spectre (doble clic / correr el script, dejar la terminal
  abierta), cómo leer un resultado de búsqueda (cita, extracto resaltado,
  etiqueta de sección), cómo abrir el fallo completo y el PDF en la página
  exacta, cómo cargar tomos nuevos desde la pestaña Biblioteca (las dos
  formas: por número de tomo vía CSJN, o subiendo un PDF propio), qué
  significa que un tomo quede en `requiere_ocr`, y un bloque de preguntas
  frecuentes (¿necesito internet para buscar?, ¿mis datos salen de mi
  computadora?, ¿por qué no encontré nada?, ¿puedo dejarlo cargando toda
  la noche?).
- `docs/plan-spectre.md`: casilla de PR-26 marcada (§6) y §9 actualizada —
  los 27 PRs del plan están cerrados; se deja una nota de que lo que sigue
  es una decisión nueva (§8, o usar Spectre tal cual), no otro PR de esta
  lista.

## Qué decidí por mi cuenta

- No usé el nombre real de la hermana de Kevin en ningún lado del texto ni
  de la guía — la escribí para "una abogada" en general, sin datos
  personales, aunque la motivación (mencionada en el plan) sí sea ella.
- El número "un par de minutos" por tomo en la guía sale de la medición
  real de PR-25 (~106 s / ~107 s por tomo digital), no es una estimación
  inventada. Lo dejé redondeado a propósito porque la guía es para una
  persona no técnica, no para reproducir el número exacto.
- No agregué capturas de pantalla: la interfaz es simple (dos tabs, un
  campo de búsqueda, una tabla) y describirla en texto alcanza para el
  criterio de aceptación ("puede instalarlo y buscar"); meter imágenes acá
  hubiera significado mantenerlas sincronizadas con cada cambio de la UI
  sin que el plan lo pidiera.
- No documenté los subcomandos de `spectre pdf …` / `spectre cli` en la
  guía de uso: son herramientas de desarrollo (medir, no persistir, según
  `CLAUDE.md`), no algo que alguien sin instalar el proyecto para
  desarrollarlo necesite. Quedan donde ya estaban documentados
  (`CLAUDE.md`), y el README linkea ahí para quien va a tocar el código.

## Qué verifiqué

- Leí `spectre/web/index.html` para confirmar los nombres reales de las
  pestañas ("Buscar", "Biblioteca") y de los dos formularios de carga
  ("Indexar desde la CSJN", "Subir un PDF propio") — la guía usa esos
  mismos nombres, no paráfrasis.
- Leí `scripts/arrancar.ps1` y `scripts/arrancar.py` para confirmar el
  comportamiento exacto que describo en el README: crea el venv, instala
  `.[embed]`, baja el modelo, intenta indexar un tomo de muestra
  (best-effort, no aborta si falla) y levanta el servidor en
  `http://127.0.0.1:8000/`.
- Leí `pyproject.toml` para confirmar `requires-python = ">=3.11"` y los
  extras `dev` / `embed` tal como quedaron nombrados ahí.
- No corrí `scripts/arrancar.ps1` de punta a punta en esta sesión (reinstalar
  `.[embed]` completo no aporta nada nuevo a esta verificación — ya está
  cubierto por la bitácora de PR-24 y por `tests/test_arrancar.py`); esta PR
  es documentación, no cambia código de arranque.
- `ruff check .` sobre el repo: sin cambios de código en esta PR, no aplica
  ningún hallazgo nuevo.

## Dudas que quedaron abiertas

- Ninguna que bloquee el cierre. La única nota es que "un par de minutos"
  por tomo en la guía es válido para tomos digitales como 348/349; un tomo
  que caiga en `requiere_ocr` no llega a indexarse por ahora (R-1), y la
  guía lo menciona pero no promete un tiempo para ese caso porque no hay
  ninguno implementado todavía.
