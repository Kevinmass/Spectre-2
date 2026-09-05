# Spectre

Motor de búsqueda semántica sobre jurisprudencia argentina (colección Fallos
de la Corte Suprema de Justicia de la Nación). Monousuario, local, corre en
tu propia máquina — nada se sube a internet salvo para bajar los tomos desde
el sitio de la CSJN.

Buscá por significado, no solo por palabra exacta: "despido sin causa" también
encuentra fallos que hablan de "cesantía injustificada". Cada resultado trae
la cita (`Fallos: 348:113`), un extracto con el término resaltado, y un enlace
que abre el PDF oficial en la página exacta.

**¿Buscás cómo usarlo, sin instalar nada técnico?** Mirá la
[guía de uso](docs/guia-uso.md) — está escrita para alguien que nunca vio el
proyecto, sin jerga de programador.

## Instalación

Necesitás **Python 3.11 o más nuevo** instalado y en el PATH. El resto lo hace
el script de arranque: crea el entorno virtual, instala todo (incluido el
modelo de embeddings, que pesa varios cientos de MB), intenta indexar un tomo
de muestra desde la CSJN si hay conexión, y abre el navegador con Spectre ya
levantado.

**Windows** (PowerShell):

```
scripts\arrancar.ps1
```

**macOS / Linux**:

```bash
scripts/arrancar.sh
```

La primera vez tarda unos minutos (bajar dependencias y el modelo). Las
siguientes veces que corras el mismo comando arranca directo, sin reinstalar
nada.

Si el sitio de la CSJN no responde en el momento del arranque, Spectre igual
levanta, vacío — indexás el primer tomo a mano desde la pestaña **Biblioteca**
en cuanto quieras (ver la guía de uso).

## Uso diario

Una vez instalado, para volver a abrir Spectre alcanza con correr de nuevo el
mismo script (`scripts\arrancar.ps1` o `scripts/arrancar.sh`). Se abre en
`http://127.0.0.1:8000/`.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11
pip install -e ".[dev]"
ruff check .
pytest
```

`pip install -e ".[embed]"` agrega los embeddings reales (necesario para
`spectre search buscar` y para que la pestaña Buscar de la web funcione más
allá de texto exacto); sin ese extra, Spectre degrada solo a búsqueda léxica
y lo dice en la respuesta, nunca simula un resultado semántico que no calculó.

El plan de desarrollo, las decisiones de diseño y el estado de cada PR están
en [`docs/plan-spectre.md`](docs/plan-spectre.md). `CLAUDE.md` documenta la
arquitectura del código para quien vaya a tocarlo.

El intento anterior quedó en [`legacy/`](legacy/) como referencia histórica;
no se importa ni se reutiliza.
