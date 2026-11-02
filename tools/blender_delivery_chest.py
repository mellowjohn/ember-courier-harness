"""Compatibility entry point for the packaged Blender generator."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1] / "ember_harness/blender/delivery_chest.py"), run_name="__main__")
