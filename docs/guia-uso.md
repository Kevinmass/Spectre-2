# Guía de uso de Spectre

Spectre busca en los fallos de la Corte Suprema por lo que **significan**, no
solo por las palabras exactas. Si buscás "despido sin causa", también te va a
mostrar fallos que hablan de "cesantía injustificada" aunque no usen esas
palabras. Esta guía no da por sabido nada de programación.

## Abrir Spectre

Cada vez que quieras usarlo, abrí una terminal en la carpeta del proyecto y
corré el script de arranque:

- Windows: hacé doble clic en `scripts\arrancar.ps1`, o corrélo desde
  PowerShell.
- Mac: corré `scripts/arrancar.sh` desde la Terminal.

A los pocos segundos se abre solo una pestaña del navegador en
`http://127.0.0.1:8000/`. Dejá la ventana de la terminal abierta mientras
usás Spectre — si la cerrás, Spectre se apaga.

## Buscar un fallo

En la pestaña **Buscar**, escribí lo que estás buscando en lenguaje normal
(no hace falta poner comillas ni operadores) y apretá **Buscar** o Enter.

Cada resultado muestra:

- **La cita** (por ejemplo `Fallos: 348:113`), que es como se referencia ese
  fallo en cualquier escrito.
- **Un extracto** del texto, con la palabra o el concepto que coincide
  resaltado.
- **Una etiqueta** que dice de qué parte del fallo viene ese extracto:
  dictamen, mayoría, voto o disidencia.

Hacé clic en cualquier resultado para abrir el fallo completo: ahí ves el
texto entero organizado por esas mismas partes, los datos del caso (fecha,
jueces, tribunal de origen, partes), y los otros fallos que cita. Hay también
un enlace para **ver en el PDF**, que abre el PDF oficial del tomo directo en
la página donde está ese fragmento — no hace falta buscarla a mano.

Si todavía no cargaste ningún tomo, o el que buscás no está cargado, la
búsqueda no va a encontrar nada. Eso se soluciona indexando tomos, que es el
paso siguiente.

## Cargar tomos (pestaña Biblioteca)

Spectre solo puede buscar en los tomos que ya "leyó" (indexó). La pestaña
**Biblioteca** lista los tomos cargados y su progreso, y tiene dos formas de
agregar uno nuevo:

1. **Indexar desde la CSJN**: poné el número de tomo y apretá **Indexar**.
   Spectre lo baja del sitio oficial y lo procesa solo. Esto puede tardar
   varios minutos por tomo — no hace falta esperar mirando la pantalla, el
   progreso se actualiza solo mientras la pestaña está abierta.
2. **Subir un PDF propio**: si ya tenés el PDF de un tomo en tu computadora
   (por ejemplo porque lo bajaste vos o te lo pasaron), elegí el archivo y
   apretá **Subir e indexar**.

Mientras un tomo se está procesando vas a ver su estado cambiar (bajando,
extrayendo texto, armando los fallos, etc.) hasta llegar a **indexado**, que
es cuando ya aparece en los resultados de búsqueda. Si un tomo queda marcado
como **requiere OCR**, quiere decir que es un escaneo viejo que Spectre
todavía no puede leer automáticamente (los tomos digitales más recientes no
tienen este problema).

## Preguntas frecuentes

**¿Necesito internet para buscar?**
No, una vez que un tomo está indexado, la búsqueda es 100% local. Internet
solo hace falta para bajar tomos nuevos desde la CSJN.

**¿Mis búsquedas o los PDFs que subo salen de mi computadora?**
No. Todo lo que indexás y buscás queda guardado localmente, en la carpeta
`data/` del proyecto. Spectre no manda nada a ningún servidor propio.

**Busqué algo y no encontré nada, ¿está roto?**
Lo más probable es que el tomo donde está ese fallo todavía no esté indexado.
Fijate en la pestaña Biblioteca si aparece, y si no, cargalo.

**¿Puedo dejarlo cargando tomos toda la noche?**
Sí, cada tomo tarda del orden de un par de minutos en indexarse. Podés cargar
varios seguidos desde la Biblioteca y dejarlos procesando.
