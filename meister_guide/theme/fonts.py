"""Registers the bundled OFL fonts with Qt and maps UI roles to family names.

Roles: display (Pirata One headings), body (Archivo copy), mono (Spline Sans
Mono labels). If a file is missing or fails to register, the role falls back to
a sensible system family so the app never hard-fails on a font."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from meister_guide.resources import resource_path

_DEFAULT_ASSETS = resource_path("assets/fonts")

# role -> (filename, fallback family)
_FONTS = {
    "display": ("PirataOne-Regular.ttf", "Georgia"),
    "body": ("Archivo.ttf", "Segoe UI"),
    "mono": ("SplineSansMono.ttf", "Consolas"),
}

_resolved: dict[str, str] = {}


def load_fonts(assets_dir=None) -> dict:
    """Register bundled fonts; return {role: family}. Idempotent-safe to call
    once at startup."""
    base = Path(assets_dir) if assets_dir is not None else _DEFAULT_ASSETS
    resolved = {}
    for role, (filename, fallback) in _FONTS.items():
        family = fallback
        path = base / filename
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(fid) if fid != -1 else []
            if families:
                family = families[0]
        resolved[role] = family
    _resolved.clear()
    _resolved.update(resolved)
    return resolved


def family(role: str) -> str:
    """Family for a role; falls back to the declared system family if fonts were
    never loaded."""
    if role in _resolved:
        return _resolved[role]
    return _FONTS.get(role, ("", "Segoe UI"))[1]
