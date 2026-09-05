# Bitácora PR-25 — Medición end-to-end

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **Tiempos reales de indexación por tomo,
tamaño del índice, memoria pico. Extrapolación honesta a la colección
completa. Acepta: una tabla de números medidos en `docs/qa/mediciones.md`.**

## Resultado en una línea

`scripts/medir_ingesta.py` corre `spectre ingest` de verdad (subproceso,
contra un `data_dir` temporal) sobre los tomos 348 y 349, y mide tiempo por
etapa (de `jobs.iniciado_at`/`terminado_at`, ya los escribía el runner desde
PR-03/19), memoria pico (el propio subproceso se mide a sí mismo antes de
salir) y tamaño de índice (`spectre.db` + `data/vectors/` reales después de
ingestar). Los números están en `docs/qa/mediciones.md`, con la
extrapolación y sus límites explicados ahí, no acá.

## Qué hice

### La decisión de fondo: el hijo se mide a sí mismo, no el padre al hijo

Mi primer diseño era el obvio: un proceso padre que sondea la memoria del
subproceso de ingesta con `psutil.Process(pid).memory_info()` cada cierto
intervalo, quedándose con el máximo (en Windows, `peak_wset` es un contador
que mantiene el propio sistema operativo, así que ni hace falta sondear
rápido). Lo probé contra un caso trivial —un subproceso que reserva 500 MB y
duerme— **antes** de gastar minutos corriendo una ingesta real, y el
resultado fue claramente roto: `rss`/`peak_wset` del hijo se quedaban
congelados en ~4 MB sin importar cuánta memoria reservara. Medí lo mismo
pidiéndole a un proceso su **propia** memoria (`psutil.Process(os.getpid())`
desde adentro) y ahí sí reflejaba la reserva real (542 MB con un `bytearray`
de 500 MB + el intérprete). La diferencia es consistente con que el entorno
donde corrí esto restringe la consulta de memoria de un proceso *ajeno* (no
pude confirmar la causa exacta — permisos del token, un job object, algo del
sandbox de esta sesión), pero no la de uno mismo.

Con esa evidencia medida (no una sospecha), cambié el diseño: el subproceso
de ingesta se mide a sí mismo justo antes de salir
(`_pico_propio_mb`/`_entrypoint_subproceso`) y lo imprime por stdout con un
marcador (`__SPECTRE_PICO_MB__=`) que el proceso padre parsea. Es además
**más simple y más portable** que sondear desde afuera: en Linux
`resource.getrusage(RUSAGE_SELF).ru_maxrss` da el pico exacto sin sondeo (lo
mantiene el kernel), y en Windows cae a `psutil...peak_wset` del propio
proceso — mismo patrón, sin la parte que resultó no ser confiable.

### `scripts/medir_ingesta.py`

- **Un subproceso real por tomo** (`python -m scripts.medir_ingesta
  --subproceso <numero> <pdf>`), no `correr_pipeline` llamado en este mismo
  proceso: la memoria que importa es la de `spectre ingest` tal como corre
  en producción, con `torch` + `sentence-transformers` + `lancedb` cargados
  desde cero — mezclarla con lo que ya tiene cargado el script de medición
  (o una sesión de pytest) daría un número que no es el de nadie.
- **Los dos tomos, uno atrás del otro, en el mismo `data_dir` temporal**: así
  el tamaño de índice final es el de "2 tomos juntos" (comparable a lo que
  ya hay en el `data/` real del repo, que también tiene esos dos), no la
  suma de dos mediciones aisladas con overhead de esquema duplicado.
- **`_duraciones_por_etapa` lee `jobs` directo con SQL**, sin importar
  `spectre.jobs.pipeline`: la lista de etapas está copiada como constante
  (`ETAPAS`) para que el script de medición pueda leer los resultados de una
  corrida aunque, por lo que sea, el import del paquete fallara en el
  entorno de medición — no depende de que `spectre` estuviera en buen estado,
  solo de que la corrida ya haya dejado sus filas en la base.
- **`medir_tomo` revienta si el tomo no terminó `indexado`** o si el
  subproceso no imprimió el marcador de memoria — ningún número a medias
  para una ingesta que no cerró (D-05 aplicado a la medición: no hay
  "medición parcial" silenciosa).

### Verificación de que el número de memoria tiene sentido

No me quedé con el número solo porque el mecanismo ya no estaba roto: medí
aparte cuánto pesa **solo** cargar el modelo de embeddings (sin ingesta),
con el mismo `_pico_propio_mb`, y dio ~966 MB. Contra los ~5,0–5,3 GB de la
ingesta completa, eso deja ~4,3 GB para el resto del pipeline — coherente
con que la etapa cara además de `embeber` es `extraer` (pdfplumber sobre un
PDF de ~950 páginas), no con un número que "parece cualquier cosa". El
detalle completo, con la hipótesis de por qué tanto, está en
`docs/qa/mediciones.md` (no se optimiza acá — este PR mide, PR-25 no incluye
arreglar nada).

## Qué decidí por mi cuenta

- **`psutil` como dependencia `dev`, no de producto.** Ninguna ruta del
  paquete `spectre/` la importa; solo `scripts/medir_ingesta.py`. Va al
  lado de `pytest`/`ruff`/`httpx` en `pyproject.toml`, con el comentario que
  dice por qué.
- **Medir con `--pdf` (subida manual, D-9), no con `--csjn-tomo-id`.** El
  objetivo es medir el pipeline, no la descarga (que ya tiene su propia
  medición en PR-17: reintentos, caché, ritmo). Los PDFs de 348 y 349 ya
  están en `data/tomos/` del repo (no versionados, pero presentes en esta
  máquina desde sesiones anteriores) — usarlos directo evita depender de que
  la CSJN responda, que ya falló dos veces en este proyecto (PR-18, PR-24).
- **Reportar el pico como "no escala con la colección" en vez de solo dar
  un número.** Es información real que cambia cómo se lee R-4 (el riesgo
  abierto del plan sobre el tiempo/memoria de la colección completa): con la
  arquitectura actual (un proceso por invocación de `spectre ingest`), la
  memoria pico es la de **un** tomo, no la de 349. Vale la pena decirlo
  explícito, no dejar que se infiera solo.
- **No medí el camino de la Biblioteca** (pipeline corriendo dentro del
  proceso del servidor, PR-23). Es un patrón de uso distinto —el modelo
  queda cacheado entre tomos en vez de recargarse cada vez— y remedirlo ahí
  es otra sesión, no una nota al pie de esta. Quedó como duda abierta en
  `docs/qa/mediciones.md`, no como número inventado.

## En qué me desvié del plan

Nada que valga la pena marcar como desvío: el plan pide "tiempos reales de
indexación por tomo, tamaño del índice, memoria pico" y una "extrapolación
honesta" — los tres números están, y la extrapolación explicita su propio
límite (no se sabe qué fracción de los 349 tomos es `digital` contra
`requiere_ocr`, R-1) en vez de forzar un total de colección con más
precisión de la que da la evidencia.

## Qué verifiqué y con qué comandos

```
./.venv/Scripts/python.exe scripts/medir_ingesta.py
# -> 106,0s / 106,9s totales, ~5,3 / 5,0 GB pico, 1.112 / 1.087 chunks;
#    spectre.db 31,2 MB, vectors/ 3,4 MB para los dos tomos juntos.

./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 92 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 378 passed, 3 skipped, 23 deselected
```

Tests nuevos (`tests/test_medir_ingesta.py`): las piezas puras
(`_tamano_dir`, `_duraciones_por_etapa`) contra datos armados a mano, más
`_pico_propio_mb` medido de verdad (reservar 200 MB y comprobar que el pico
sube — no mockeado, mismo criterio que las mediciones de calidad de PR-18),
y `_entrypoint_subproceso`/`medir_tomo` con el CLI y `subprocess.run`
mockeados para los caminos de error. La corrida real de dos tomos (arriba)
no entra en la suite — igual que `arrancar.py` en PR-24, un subproceso de
minutos no es un test de todos los días.

## Dudas que quedaron

- **Por qué la consulta de memoria de un proceso ajeno da un valor congelado
  en esta sesión.** No perseguí la causa exacta (permisos del token, un job
  object, algo del sandbox donde corre esta sesión de Claude Code) porque el
  rediseño (medirse a uno mismo) la vuelve irrelevante para este script —
  pero si algún día hace falta sondear un proceso ajeno desde Windows en
  este entorno, vale la pena saber que no anduvo acá.
- **La fracción `digital`/`requiere_ocr` de los 349 tomos reales**, ya
  anotada en R-1 del plan y repetida en `docs/qa/mediciones.md`: sigue sin
  poder medirse sin red a la CSJN.
- **El camino de la Biblioteca** (pipeline dentro del proceso del servidor)
  no se remidió acá; ver "qué decidí por mi cuenta".
