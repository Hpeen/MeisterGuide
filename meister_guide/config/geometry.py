"""Persist the overlay window's size and position via QSettings."""
from PySide6.QtCore import QSettings, QRect

_KEY = "overlay/geometry"


def save_geometry(settings: QSettings, rect: QRect) -> None:
    settings.setValue(
        _KEY, [rect.x(), rect.y(), rect.width(), rect.height()]
    )
    settings.sync()


def restore_geometry(settings: QSettings):
    """Return a QRect, or None if nothing has been saved yet."""
    raw = settings.value(_KEY)
    if not raw:
        return None
    x, y, w, h = (int(v) for v in raw)
    return QRect(x, y, w, h)
