"""Compatibility import of the canonical Blender construction helpers."""
from pathlib import Path
import runpy
PropScene=runpy.run_path(str(Path(__file__).resolve().parents[1]/"ember_harness/blender/blender_prop_support.py"))['PropScene']
