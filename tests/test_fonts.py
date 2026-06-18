# tests/test_fonts.py
from PySide6.QtWidgets import QApplication
from meister_guide.theme import fonts


def _app():
    return QApplication.instance() or QApplication([])


def test_roles_have_families_after_load():
    _app()
    resolved = fonts.load_fonts()  # registers bundled ttf, returns role->family
    for role in ("display", "body", "mono"):
        assert role in resolved
        assert isinstance(resolved[role], str) and resolved[role]


def test_missing_font_file_falls_back(tmp_path):
    _app()
    # Point the loader at an empty dir so nothing registers; must still return
    # sane fallback families, never raise.
    resolved = fonts.load_fonts(assets_dir=tmp_path)
    assert resolved["display"]  # some serif fallback
    assert resolved["body"]
    assert resolved["mono"]
