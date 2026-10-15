"""Compatibilidad: el pipeline de figuras vive ahora en scripts/generate_figures.py."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parent / "scripts" / "generate_figures.py"), run_name="__main__")
