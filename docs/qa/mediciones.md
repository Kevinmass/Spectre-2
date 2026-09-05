# Mediciones end-to-end (PR-25)

Números medidos con `scripts/medir_ingesta.py` (subproceso real de `spectre
ingest`, contra un `data_dir` temporal y vacío, uno de los dos tomos de
referencia atrás del otro). Nada de esto está estimado a mano; el método está
documentado en el docstring del propio script. Máquina: la de desarrollo
(Windows, `.venv` con `sentence-transformers` 6.0.1 / torch 2.14.0).

## Por tomo

| | Tomo 348 | Tomo 349 |
|---|---|---|
| páginas | 968 | 913 |
| fallos | 133 | 153 |
| chunks | 1.112 | 1.087 |
| **tiempo total** | **106,0 s** | **106,9 s** |
| **memoria pico** | **5.300 MB** | **5.032 MB** |

### Tiempo por etapa (segundos)

| etapa | Tomo 348 | Tomo 349 |
|---|---|---|
| descargar | — (`--pdf`, no corrió) | — (`--pdf`, no corrió) |
| extraer | 59 | 60 |
| limpiar | 0 | 1 |
| segmentar | 2 | 2 |
| estructurar | 1 | 0 |
| fragmentar | 1 | 1 |
| embeber | 38 | 38 |
| indexar | 0 | 0 |

`extraer` (pdfplumber, texto por página) y `embeber` (el modelo de
embeddings sobre ~1.100 chunks) son las dos etapas caras — juntas son ~92%
del tiempo total. El resto (limpiar/segmentar/estructurar/fragmentar/indexar)
es ruido de segundos.

## Tamaño del índice

Los dos tomos juntos, en el mismo `data_dir` (2.199 chunks en total):

| | tamaño |
|---|---|
| `spectre.db` | 31,2 MB |
| `data/vectors/` | 3,4 MB |
| **total** | **34,6 MB** |

`vectors/` cuadra exacto con la aritmética (2.199 × 384 dim × 4 bytes ≈
3,38 MB): LanceDB no le agrega overhead visible al vector crudo. `spectre.db`
es más grande porque además de los chunks guarda el texto crudo y limpio de
cada página (1.881 páginas entre los dos tomos) y el texto completo de cada
sección — la materia prima para poder reconstruir la vista de fallo (PR-22)
sin volver a abrir el PDF.

## Memoria: de dónde sale el número

Cargar el modelo de embeddings solo (sin ingesta) ya pesa **~966 MB** (torch
+ sentence-transformers, medido aparte con el mismo método). Los ~4,3 GB
restantes del pico son la ingesta en sí — la sospecha, no verificada en esta
sesión porque no es su objetivo, es que pdfplumber acumula estado por página
(fuentes, objetos de layout) a lo largo de un PDF de ~950 páginas y no lo
libera hasta terminar `extraer`. No se optimiza acá: PR-25 mide, no arregla.

**El pico no depende de cuántos tomos tenga la colección.** `spectre ingest`
es un proceso por invocación (D-06: sin threads, un proceso): indexar el
tomo 1 de 349 o el 349 de 349 tiene el mismo techo de memoria, porque cada
uno arranca y termina su propio proceso. Esto es tranquilizador para R-4
(riesgo abierto del plan): la colección completa **no** multiplica la
memoria pico, solo el tiempo total y el espacio en disco.

Esto vale para `spectre ingest` desde la CLI. La Biblioteca (PR-23) corre el
pipeline en el proceso ya vivo del servidor (`BackgroundTasks`); si alguien
encola muchos tomos seguidos ahí, el modelo queda cacheado entre tomos (más
liviano) pero no se remidió ese camino en esta sesión — queda como duda
abierta, no como número inventado.

## Extrapolación a la colección completa

El catálogo de la CSJN (PR-16) tiene **349 números de tomo** (421 filas
contando los 44 con más de un volumen). Con el promedio medido de los dos
tomos de referencia (106,5 s, 17,3 MB combinado por tomo):

| | valor |
|---|---|
| tiempo total (sequencial, un proceso a la vez) | 349 × 106,5 s ≈ **10,3 h** |
| espacio en disco | 349 × 17,3 MB ≈ **6,0 GB** |
| memoria pico | **~5,3 GB**, no escala con la cantidad de tomos (ver arriba) |

**Esto es un techo, no una predicción real de la colección**, por una razón
concreta y ya conocida (R-1 del plan): 348 y 349 son tomos modernos,
clasificados `digital` (PR-18). Un tomo `requiere_ocr` se frena después de
`extraer` (D-10) — no llega a `embeber` ni a `fragmentar`, así que le
corresponde solo la fracción de tiempo de esa primera etapa (~60 s), no los
106,5 s completos, y tampoco le suma chunks al espacio en disco. No hay
forma de saber, sin bajar y medir un tomo antiguo real, qué fracción de los
349 es `digital` contra `requiere_ocr` — la red a `sjservicios.csjn.gov.ar`
no respondió en las sesiones de PR-18 ni de PR-24, así que ese número sigue
sin poder medirse. La tabla de arriba es el caso "si todo el catálogo fuera
como el 348/349", útil como cota superior de tiempo y disco, no como
estimación de la colección real.

## Cómo reproducir

```
python scripts/medir_ingesta.py
```

(usa `data/tomos/348.pdf` y `data/tomos/349.pdf` por defecto; con otros
tomos: `python scripts/medir_ingesta.py ruta1.pdf:numero1 ruta2.pdf:numero2`).
