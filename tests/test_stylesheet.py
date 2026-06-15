from meister_guide.theme.stylesheet import build_stylesheet
from meister_guide.theme.palette import PALETTE

def test_stylesheet_includes_core_colors_and_widgets():
    qss = build_stylesheet()
    assert PALETTE["background"] in qss
    assert PALETTE["accent_primary"] in qss
    assert PALETTE["accent_warm"] in qss
    assert "QPushButton" in qss
    assert "QScrollBar:vertical" in qss
    assert "width: 6px" in qss
