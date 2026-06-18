"""Pure geometry helpers for the docked overlay panel. No Qt widgets here so
these stay unit-testable without a display."""
from PySide6.QtCore import QRect

PANEL_WIDTH = 432   # 30px spine + 402px body
MARGIN = 18         # gap from screen edges (top/bottom and the docked side)

VALID_EDGES = ("left", "right")


def normalize_edge(edge) -> str:
    return edge if edge in VALID_EDGES else "right"


def dock_rect(screen: QRect, edge: str) -> QRect:
    """Panel rectangle for the given screen geometry + edge."""
    edge = normalize_edge(edge)
    height = screen.height() - 2 * MARGIN
    top = screen.top() + MARGIN
    if edge == "left":
        left = screen.left() + MARGIN
    else:
        left = screen.right() + 1 - MARGIN - PANEL_WIDTH
    return QRect(left, top, PANEL_WIDTH, height)


def nearest_edge(window_center_x: int, screen: QRect) -> str:
    """Which edge a window centred at window_center_x should snap to."""
    midpoint = screen.left() + screen.width() / 2
    return "left" if window_center_x < midpoint else "right"
