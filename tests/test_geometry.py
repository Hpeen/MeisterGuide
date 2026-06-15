from PySide6.QtCore import QSettings, QRect
from meister_guide.config.geometry import save_geometry, restore_geometry

def _settings(tmp_path):
    return QSettings(str(tmp_path / "t.ini"), QSettings.IniFormat)

def test_restore_returns_none_when_unset(tmp_path):
    s = _settings(tmp_path)
    assert restore_geometry(s) is None

def test_save_then_restore_roundtrips(tmp_path):
    s = _settings(tmp_path)
    save_geometry(s, QRect(100, 120, 480, 640))
    rect = restore_geometry(s)
    assert rect == QRect(100, 120, 480, 640)
