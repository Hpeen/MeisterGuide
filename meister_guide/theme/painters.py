"""Custom QPainter routines for the woodgrain body panel and leather spine.
Values mirror the Phase-10 design handoff CSS. `edge` is which screen edge the
panel is docked to; when docked left the layout mirrors so the spine always
faces inward."""
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPainter, QBrush

CORNER = 13.0
SPINE_W = 30


def _c(r, g, b, a=255):
    return QColor(r, g, b, a)


def paint_spine(painter: QPainter, w: int, h: int, edge: str = "right"):
    """Draw the leather spine into a w×h region whose top-left is (0,0).
    Rounded corners sit on the OUTER side (screen edge); for edge='right' the
    spine is on the panel's left so its rounded corners are on the left."""
    painter.setRenderHint(QPainter.Antialiasing, True)
    rounded_left = (edge == "right")  # spine on left -> round left corners

    # Leather vertical gradient.
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, _c(0x8a, 0x44, 0x23))
    grad.setColorAt(0.5, _c(0x6e, 0x33, 0x18))
    grad.setColorAt(1.0, _c(0x7a, 0x3a, 0x1e))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRect(0, 0, w, h)

    # Centred dotted stitching: 7px dash, 8px gap.
    painter.setBrush(_c(0xf7, 0xe0, 0xbe, 115))
    x = w / 2 - 1
    y = 0
    while y < h:
        painter.drawRect(QRectF(x, y, 2, 7))
        y += 15

    # Two brass studs, inset 18px top and bottom.
    for cy in (18, h - 18):
        rg = QRadialGradient(QPointF(w / 2 - 1, cy - 1), 5)
        rg.setColorAt(0.0, _c(0xff, 0xe7, 0xa6))
        rg.setColorAt(0.55, _c(0xb8, 0x92, 0x3f))
        rg.setColorAt(1.0, _c(0x6b, 0x4f, 0x1d))
        painter.setBrush(QBrush(rg))
        painter.drawEllipse(QPointF(w / 2, cy), 4, 4)

    # Inner edge shadow on the inward side.
    shade = QLinearGradient(0, 0, w, 0)
    if rounded_left:
        shade.setColorAt(0.85, _c(0, 0, 0, 0))
        shade.setColorAt(1.0, _c(0, 0, 0, 115))
    else:
        shade.setColorAt(0.0, _c(0, 0, 0, 115))
        shade.setColorAt(0.15, _c(0, 0, 0, 0))
    painter.setBrush(QBrush(shade))
    painter.drawRect(0, 0, w, h)
