# tests/test_painters.py
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QPixmap, QPainter
from meister_guide.theme import painters


def _app():
    return QApplication.instance() or QApplication([])


def test_paint_spine_does_not_raise():
    _app()
    pm = QPixmap(30, 600)
    pm.fill()
    p = QPainter(pm)
    try:
        painters.paint_spine(p, 30, 600, edge="right")
        painters.paint_spine(p, 30, 600, edge="left")
    finally:
        p.end()
