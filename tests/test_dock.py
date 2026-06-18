# tests/test_dock.py
from PySide6.QtCore import QRect
from meister_guide.config.dock import dock_rect, nearest_edge, PANEL_WIDTH, MARGIN


def test_dock_rect_right_edge():
    screen = QRect(0, 0, 1920, 1080)
    r = dock_rect(screen, "right")
    assert r.width() == PANEL_WIDTH
    assert r.height() == 1080 - 2 * MARGIN
    assert r.top() == MARGIN
    assert r.right() == 1920 - 1 - MARGIN  # MARGIN gap from screen's right edge


def test_dock_rect_left_edge():
    screen = QRect(0, 0, 1920, 1080)
    r = dock_rect(screen, "left")
    assert r.left() == MARGIN
    assert r.width() == PANEL_WIDTH


def test_dock_rect_respects_screen_offset():
    screen = QRect(1920, 0, 1280, 1024)  # second monitor to the right
    r = dock_rect(screen, "left")
    assert r.left() == 1920 + MARGIN


def test_nearest_edge_picks_by_midpoint():
    screen = QRect(0, 0, 1920, 1080)
    assert nearest_edge(100, screen) == "left"
    assert nearest_edge(1800, screen) == "right"
    assert nearest_edge(960, screen) == "right"  # exact midpoint -> right (tie)
