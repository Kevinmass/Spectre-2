# Bitácora PR-24 — Arranque de un comando

Fecha: 04/09/2026
Criterio de aceptación (plan §6): **Script que crea el entorno, instala, baja
el modelo y levanta Spectre. Acepta: en una máquina limpia, del clone a la
primera búsqueda sin leer documentación.**

## Resultado en una línea

`scripts/arrancar.ps1` (Windows) y `scripts/arrancar.sh` (macOS/Linux) crean
`.venv`, instalan `spectre[embed]` y llaman a `scripts/arrancar.py`, que baja
el modelo de embeddings real, intenta indexar el Tomo 348 de muestra desde la
CSJN (best-effort: si el sitio no responde, no aborta) y levanta `spectre
serve`. **Verificado de punta a punta dos veces** en una copia del repo sin
`.venv` ni `data/` (máquina limpia simulada): las dos corridas terminaron con
`spectre serve` real respondiendo en `http://127.0.0.1:8000/` — la primera
con el paso de la CSJN fallando de verdad (el sitio no respondió, confirmado
con un chequeo de red aparte antes de diseñar nada), la segunda igual.

## Qué hice

### La decisión de fondo: intentar indexar un tomo de muestra, pero sin apostar el arranque a que la red funcione

El plan describe PR-24 en cuatro verbos ("crea el entorno, instala, baja el
modelo y levanta Spectre"), pero el criterio de aceptación habla de "la
primera **búsqueda**" — y buscar sobre una base vacía es una experiencia
pobre para juzgar si el producto funciona. Antes de decidir cómo resolver
esto, comprobé si el sitio de la CSJN respondía **ahora mismo**, no lo di por
sentado:

```
python -c "from spectre.corpus.csjn import listar_catalogo; listar_catalogo()"
# TimeoutError: [WinError 10060] ... connected host has failed to respond
```

No respondió — lo mismo que ya había documentado la bitácora de PR-18 en una
sesión anterior. Esto no es un caso límite hipotético: es una condición real
que este mismo proyecto ya pisó dos veces. Con esa evidencia, el diseño tenía
que asumir que la CSJN puede no estar disponible **en el momento exacto en
que alguien corre el script por primera vez**, y no bloquear el arranque por
eso.

**Alternativa descartada: bundlear un PDF de muestra fijo (sin depender de la
CSJN) para garantizar resultados de búsqueda siempre.** La tentación era usar
`tests/fixtures/tomo348_cuerpo_p31-40.pdf` (10 páginas reales, ya validado en
una decena de tests) como demo, ingestándolo con `numero=348` en el arranque.
La descarté por un motivo concreto, no por gusto: `tomos.numero` es
**único** en el esquema. Si el usuario más tarde indexa el Tomo 348 real
completo (desde Biblioteca, PR-23, con su propio `csjn_tomo_id`),
`iniciar_tomo` encontraría el tomo 348 **ya existente** (el demo de 10
páginas, ya `indexado`) y no haría nada — el usuario creería que indexó el
tomo completo y en realidad seguiría teniendo el recorte de muestra. Usar un
número inventado (`numero=0`, por ejemplo) tampoco resuelve nada: el texto de
las páginas dice "348" en su propio encabezado (`pagina_oficial`), así que
las citas mostradas (`Fallos: 348:X`) quedarían desincronizadas del `tomo.
numero` real registrado — confuso de una forma distinta. Indexar el **tomo
real** por `csjn_tomo_id`, con reintento gracioso si falla, evita las dos
trampas: no hay colisión de identidad ni cita mal etiquetada, al costo de que
a veces (como hoy) no hay demo.

### `scripts/arrancar.py` — lo que corre ya con `spectre` importable

- **`_tomo_de_muestra(entradas)`**: pura, sin red — elige la fila del
  catálogo con `numero == 348` (la referencia de todo el proyecto, ver
  CLAUDE.md) si está, si no la primera que haya. `[]` -> `None`.
- **`indexar_tomo_de_muestra()`**: envuelve `listar_catalogo` +
  `iniciar_tomo` + `correr_pipeline` (los mismos tres que ya usa `spectre
  ingest` y `/api/tomos/.../indexar`, PR-23 — no hay lógica de ingesta
  nueva) en un `try/except` **por separado** para el catálogo y para el
  pipeline: si cualquiera de los dos falla, imprime por qué y devuelve
  `False` sin relanzar. Nunca dice "indexado" si `tomo.estado != "indexado"`
  al final — D-05 aplicado al bootstrap.
- **`bajar_modelo()`**: `cargar_modelo().dimension` fuerza la carga real
  (perezosa hasta ese punto). Hacerlo acá, no en la primera búsqueda de
  quien sea, es la diferencia entre "el setup tarda un rato" (esperado,
  con aviso) y "la primera búsqueda de alguien tarda 20 segundos sin aviso"
  (el número que midió la bitácora de PR-21).
- **`levantar_servidor()`**: `spectre.cli.main(["serve"])` — reusa el CLI
  entero (migración de la base, apertura del navegador, todo lo de PR-20),
  no reimplementa nada.
- **`sys.stdout.reconfigure(line_buffering=True)`** en el `if __name__ ==
  "__main__"`: lo agregué después de encontrarlo en la verificación (ver
  abajo), no lo anticipé. Sin esto, cuando la salida no va a una consola de
  verdad (redirigida a un archivo, como hace `Start-Process` de PowerShell,
  o como haría un instalador gráfico más adelante), Python bufferea por
  bloque: el archivo de log se veía congelado en "Descargando el modelo..."
  varios minutos mientras el proceso ya iba mucho más adelante — no es un
  bug de lógica, pero sí de honestidad con quien está mirando el progreso.

### `scripts/arrancar.sh` / `scripts/arrancar.ps1`

Idénticos en estructura, cada uno con la sintaxis de su plataforma: verifican
que `python`/`python3` esté en el `PATH` (no lo instalan — instalar Python
mismo queda fuera de este PR, es una asunción de base razonable, como la
tiene casi cualquier herramienta en Python), crean `.venv` si no existe,
`pip install --upgrade pip` + `pip install -e ".[embed]"` (no `[dev]`: quien
corre esto quiere *usar* Spectre, no desarrollarlo — `pytest`/`ruff` no le
sirven), y ejecutan `scripts/arrancar.py` con el intérprete del venv nuevo.

## Qué decidí por mi cuenta

- **`[embed]`, no `[dev]`, en el install del script.** Ver arriba. El README
  ya documenta `pip install -e ".[dev]"` para quien va a *desarrollar*
  Spectre — son dos audiencias distintas y el script es para la segunda.
- **Reintento gracioso de la CSJN, nunca un intento silencioso de tabla
  vacía.** Ver "la decisión de fondo".
- **Tomo de muestra real vía CSJN, no un fixture embebido con `numero`
  falso.** Ver "la decisión de fondo" — el riesgo de colisión de identidad
  con una futura ingesta real del mismo tomo fue lo que decidió esto, no
  una preferencia estética.
- **`scripts/arrancar.py` como paquete Python separado, no un subcomando de
  `spectre.cli`.** No podía serlo: `spectre` todavía no es importable
  cuando hace falta crear el venv e instalar — ese primer tramo tiene que
  vivir fuera de cualquier cosa que dependa del propio paquete. Una vez que
  `spectre` sí es importable, el resto (bajar el modelo, indexar de
  muestra, levantar) reusa sus primitivas tal cual, no las duplica.
- **Un solo README.md tocado con una sección mínima**, no el README de uso
  completo (eso es PR-26, explícito en el propio archivo: "El README de uso
  llega en PR-26"). Agregué solo el comando para correr el script y qué
  hace en tres líneas — sin eso, el script existiría pero nadie que clone
  el repo lo encontraría sin leer el árbol de archivos, lo cual violaría el
  propio criterio de "sin leer documentación" de una forma tonta (ni
  siquiera hay documentación que decir "no leas").

## En qué me desvié del plan

El plan describe PR-24 con cuatro verbos que no incluyen "indexar un tomo de
muestra" explícitamente. Lo agregué igual, justificado arriba: el criterio
de aceptación habla de "la primera **búsqueda**", y sin datos reales esa
frase se cumple de una forma técnica pero vacía de sentido. Es una extensión
razonada del criterio, no una desviación de él.

## Qué verifiqué y con qué comandos

venv del repo (Python 3.13.7; CI cubre 3.11). Sin dependencias nuevas: el
script instala `.[embed]` en un venv **aparte**, no toca el `.venv` de este
repo.

```
./.venv/Scripts/ruff.exe check .                       # -> All checks passed!
./.venv/Scripts/ruff.exe format --check .              # -> 89 files already formatted
./.venv/Scripts/python.exe -m pytest -q                # -> 366 passed, 3 skipped, 23 deselected
bash -n scripts/arrancar.sh                            # -> sintaxis OK (no se pudo correr de
                                                        #    verdad: sin macOS/Linux en esta sesión)
```

**De punta a punta, en una copia limpia del repo** (sin `.venv` ni `data/`,
robocopy de la working tree con estos cambios a un directorio aparte —
simula un clon fresco): corrí `scripts\arrancar.ps1` en background y sondeé
el log.

- **Primera corrida** (venv desde cero): creación de `.venv` + `pip install
  -e ".[embed]"` tardó ~9 minutos (instalar `torch` en Windows es lento —
  medido, no estimado: el proceso acumulaba CPU real todo el tiempo, no
  estaba colgado). Confirmé antes de esto que el sitio de la CSJN no
  respondía (ver arriba); la corrida lo probó en carne propia: el paso de
  indexar demoró, falló con el mismo `TimeoutError`, y el script **siguió**
  — `spectre serve` quedó escuchando en `127.0.0.1:8000` y respondiendo
  `GET /api/estado` -> `{"tomos":[],"chunks":0}` y `GET /` -> 200.
- Encontré ahí el problema del buffer de stdout (ver "qué hice"), lo arreglé,
  y una **segunda corrida** (mismo `.venv` ya armado, solo
  `scripts/arrancar.py` actualizado, `data/` borrada de nuevo) confirmó que
  las líneas de progreso aparecen en el momento: "Descargando el modelo...",
  "No se pudo consultar el catálogo de la CSJN (...)", "Levantando
  Spectre...", "spectre serve: http://127.0.0.1:8000/" — las cuatro, en
  orden, sin que ninguna quedara pantalla. Esta corrida completa (con el
  venv y el modelo ya con caché del sistema tibios) tardó ~35 segundos.
- Verificado también con `curl`/`Invoke-WebRequest` que el servidor
  responde de verdad en las dos corridas, no solo que el proceso sigue
  vivo. Se limpiaron el directorio temporal y los procesos al terminar.

## Dudas que quedaron

- **`scripts/arrancar.sh` no se corrió de verdad.** Solo `bash -n` (sintaxis)
  en esta máquina Windows — no hay un macOS/Linux disponible en esta sesión
  para probarlo con un venv real. Espeja la estructura de `arrancar.ps1`
  (ya verificado dos veces) línea por línea, adaptada a sintaxis POSIX, así
  que el riesgo es bajo, pero no es lo mismo que haberlo corrido.
- **No se pudo medir el camino feliz del paso de indexar de muestra** (con
  la CSJN respondiendo). El sitio no respondió en ninguna de las dos
  corridas de esta sesión — coherente con PR-18, no aislado. El camino de
  éxito de `indexar_tomo_de_muestra` sí está cubierto por
  `tests/test_arrancar.py` (con `descargar_tomo` y el modelo mockeados,
  mismo patrón que PR-23), pero no por una corrida real contra la CSJN.
- **~9 minutos para el primer `pip install -e ".[embed]"` en una máquina
  limpia** (torch es el grueso). No es un problema de este PR — el
  criterio no pone un tope de tiempo, y PR-25 (medición end-to-end) es
  donde corresponde un número con más rigor —, pero vale la pena que quede
  anotado como referencia real, no una sensación.
