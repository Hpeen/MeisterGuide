"""Resolve paths to bundled resources, in both dev and a PyInstaller bundle.

Single source of truth for the bundle layout so no other module hardcodes
frozen-vs-dev path logic."""
import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    """Absolute path to a bundled resource. Uses PyInstaller's sys._MEIPASS when
    frozen, else the repo root. `rel` is a forward-slash relative path like
    "assets/fonts". (resources.py lives at meister_guide/resources.py, so the
    repo root is parents[1].)"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[1]
    return Path(base) / rel
