# Spectre

Motor de búsqueda semántica sobre jurisprudencia argentina (colección Fallos de
la Corte Suprema de Justicia de la Nación). Monousuario, local, Python.

**Estado:** en reconstrucción. El plan y el estado de avance están en
[`docs/plan-spectre.md`](docs/plan-spectre.md). El README de uso llega en PR-26.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11
pip install -e ".[dev]"
ruff check .
pytest
```

El intento anterior quedó en [`legacy/`](legacy/) como referencia histórica; no
se importa ni se reutiliza.
