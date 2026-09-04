# Bitácora PR-17 — Descargador

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **reintentos, caché en disco por sha256,
ritmo respetuoso con el servidor. Acepta: descargar 3 tomos, verificar
hashes, reanudar una descarga cortada.**

## Resultado en una línea

`spectre/corpus/csjn/download.py` — `descargar_tomo` baja el PDF de un
`csjn_tomo_id` (los que da `catalog.listar_catalogo`, PR-16) con reintentos y
backoff, cacheado por archivo (si el destino ya existe, no pide nada).
**Spike de este PR**: el servidor de la CSJN ignora el header `Range` (probado
con un tomo de 58 MB), así que no hay resume por bytes — "reanudar" es a
nivel de archivo completo, vía un `.partial` que se descarta si algo sale
mal, nunca se le pegan bytes. Verificado contra el sitio real: 3 tomos
descargados con hash verificado, una segunda corrida no vuelve a pedir nada,
y una descarga cortada simulada (`.partial` con basura) se descarta y se
vuelve a bajar entera.

## Qué hice

### El spike (antes de escribir el resto)

Con `curl -r 0-1023` (pedir los primeros 1024 bytes) contra `verTomo?
tomoId=2` (un tomo de 1866, 58 MB — viejo y grande, probablemente escaneado,
D-10): el servidor devolvió `200 OK` con el **archivo completo** en vez de
`206 Partial Content` con solo el rango pedido. Conclusión: no hay soporte de
`Range`, y por lo tanto no hay resume real "reanudar donde quedó" a nivel de
bytes. Documentado en el módulo; el diseño de abajo es la consecuencia
directa.

De paso: un `HEAD` no devuelve `Content-Length` real en este servidor
(siempre `0`), pero un `GET` de verdad sí lo trae correcto — no sirve para
estimar tamaño sin pedir el archivo entero.

### `spectre/corpus/csjn/download.py`

- **`Descarga(ruta, sha256, bytes, reutilizada)`** — el resultado de bajar (o
  reusar) un tomo.
- **`descargar_tomo(csjn_tomo_id, destino, *, intentos=3, espera=1.0,
  forzar=False, descargar_a=_descargar_a)`**:
  - Si `destino` ya existe y no se pide `forzar`, no hace ningún pedido:
    devuelve `Descarga` con `reutilizada=True` y el sha256 de lo que hay en
    disco. Esta es la caché "por sha256" del criterio de aceptación — el
    archivo en disco *es* la caché, identificado por su propio hash.
  - Si no, descarga siempre a `<destino>.partial`; solo si la descarga
    completa sin error lo renombra (`Path.replace`, atómico) a `destino`. Si
    falla, borra el `.partial` — nunca se pega a un parcial de un intento
    anterior — y reintenta con backoff simple (`espera * intento` segundos)
    hasta `intentos` veces antes de `ConnectionError` (D-05: no hay
    "descarga a medias" que se reporte como éxito).
  - `descargar_a` es un punto de inyección (mismo patrón que `pedir_pagina`
    en `catalog.py`, PR-16): los tests pasan una función falsa sin tocar la
    red real.
- **`descargar_varios(pedidos, *, ..., pausa_entre_tomos=1.0)`** — descarga
  una lista de `(csjn_tomo_id, destino)` en secuencia, con una pausa entre
  cada uno (no después del último). Esto es el "ritmo respetuoso con el
  servidor" del criterio: sin la pausa, bajar muchos tomos seguidos sería una
  ráfaga de pedidos.
- `urllib.request` de la librería estándar — no se agregó `requests`: es un
  solo `GET` con headers, no se justifica una dependencia nueva.

### `spectre/cli.py`

- **`spectre csjn download <tomo_id> <destino> [--forzar]`** — corre
  `descargar_tomo` y muestra ruta, bytes, sha256 y si vino de caché.

### Tests

- **`tests/test_download.py`** (nuevo, 8 casos; 1 `red`):
  - Con `descargar_a` inyectado (sin red, instantáneos): baja y calcula el
    hash correcto; usa la caché si el destino ya existe (y **no** llama al
    descargador — lo prueba con una función que revienta si se la invoca);
    `forzar=True` ignora la caché; se recupera de 2 fallas seguidas antes de
    tener éxito (reintentos); agota los intentos y revienta con
    `ConnectionError` sin dejar ni el destino ni un `.partial`; **descarta un
    `.partial` con basura de una corrida anterior** antes de reintentar (la
    prueba de "reanudar" a nivel unitario); `descargar_varios` pausa entre
    tomos pero no después del último (con `time.sleep` interceptado).
  - **`test_aceptacion`** (`red`): las tres partes del criterio de aceptación
    contra el sitio real — descarga 3 tomos modernos y chicos (347-I, 349-I,
    346-I, ~3 MB cada uno), verifica que cada hash sea el sha256 real del
    archivo y que empiece con la cabecera `%PDF-`; una segunda corrida
    reutiliza los tres sin pedir nada; y una "descarga cortada" simulada
    (se borra el destino final de uno, se deja un `.partial` con basura) se
    recupera con el mismo hash que la primera vez.
- **`tests/test_cli.py`** (+1, `red`): `csjn download` baja un tomo real y
  una segunda invocación reporta que lo reutilizó.

### Docs

- `docs/plan-spectre.md`: casilla PR-17 (§6) con el resultado medido; §9 →
  "Próximo: PR-18".
- `CLAUDE.md`: "Estado del código" → PR-17; `## Comandos` + `spectre csjn
  download`.

## Qué decidí por mi cuenta

- **Sin resume por HTTP Range.** No fue una decisión de diseño sino un hecho
  del servidor real (spike). La alternativa que sí queda disponible —
  descargar siempre completo pero de forma atómica (temporal + rename) — es
  la que implementé: "reanudar una descarga cortada" pasa a significar "un
  proceso que se corta no deja un archivo corrupto en el lugar del bueno, y
  la próxima corrida lo completa desde cero sin intervención manual", que es
  lo que el criterio de aceptación necesita en la práctica (D-9: la
  descarga es parte de un pipeline reanudable, PR-19).
- **Caché por existencia de archivo, no por un registro de sha256 aparte.**
  El plan dice "caché en disco por sha256"; la lectura más simple y
  consistente con D-04 (el estado no se duplica en un JSON a mano) es que el
  archivo mismo, identificado por su contenido, sea la caché — no hace falta
  una tabla o índice separado para esto en PR-17. Cuando PR-19 persista
  `tomos.sha256` en SQLite, esa columna sirve para decidir *qué* descargar,
  no *cómo* — `download.py` sigue sin saber de la base.
- **Sin tocar `db/repo.py` ni `tomos`.** Igual que `catalog.py` (PR-16),
  `download.py` no persiste nada: mide/hace su trabajo (bajar un archivo) y
  devuelve el resultado. Insertar en `tomos` (con los dos hallazgos de PR-16
  todavía sin resolver: multi-volumen, año-rango) es explícitamente PR-19.
- **Reintentos + backoff en `descargar_tomo`, pausa entre tomos en
  `descargar_varios`.** Son dos ritmos distintos: el primero es "esta
  descarga puntual falló, probemos de nuevo pronto"; el segundo es "no
  mandar 300 pedidos seguidos". Separarlos permite que `descargar_varios`
  no pause después de una descarga que ya vino de caché en un futuro caso de
  uso que lo necesite (hoy pausa siempre entre ítems, ver "dudas").
- **3 tomos modernos y chicos para el test `red`**, no al azar. Un tomo
  viejo puede pesar 58 MB (medido en el spike) — usar uno de esos en un test
  que corre en segundos habría sido lento y ruidoso; los libros de 2023-2026
  (~3 MB) alcanzan para probar hash + caché + resume sin ese costo.

## En qué me desvié del plan

- Ninguna desviación de fondo.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11).

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> todos formateados
./.venv/Scripts/python.exe -m pytest -q                # -> 280 passed, 3 skipped, 22 deselected
./.venv/Scripts/python.exe -m pytest -m red -q         # -> 5 passed (~55 s; incluye PR-16 + PR-17)
```

`spectre csjn download 447 <tmp>/349.pdf` a mano: primera vez "no (se
descargó ahora)", segunda vez "sí" (caché), mismo sha256 las dos veces.

Spike, repro exacto de la falta de soporte de `Range`:

```
curl -s -D - -o /tmp/x.pdf -A "Mozilla/5.0" -r 0-1023 \
  "https://sjservicios.csjn.gov.ar/sj/verTomo?tomoId=2"
# -> HTTP/1.1 200 OK, content-length: 58177964 (el archivo entero, no 1024 bytes)
```

## Dudas que quedaron

- **`descargar_varios` pausa incluso entre tomos que ya estaban cacheados.**
  Es lo más simple de razonar (pausa fija entre ítems de la lista, sin
  distinguir si el anterior pidió red de verdad) a costa de esperas
  innecesarias si la mayoría ya está en disco. Si PR-19 nota que esto
  importa (p. ej. reanudar un lote grande donde casi todo ya se bajó), es un
  cambio chico: solo pausar cuando el anterior no vino de caché.
- **Sin medir el ritmo "respetuoso" real.** `pausa_entre_tomos=1.0` por
  default es una elección razonable, no una medida — no se probó bajar
  decenas de tomos seguidos para ver si el servidor empieza a bloquear o
  responder distinto.
- **Tomos viejos/escaneados pueden pesar decenas de MB** (58 MB medido). El
  descargador no distingue por tamaño ni por calidad (`digital` vs
  `requiere_ocr`, D-10) — eso es la sonda de calidad, PR-18.
- **User-Agent que se anuncia como bot** (heredado del mismo criterio que
  PR-16): no pareció afectar la descarga; si el sitio empezara a bloquearlo,
  revisar esto primero.
