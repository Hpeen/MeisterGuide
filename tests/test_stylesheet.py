from meister_guide.theme.stylesheet import build_stylesheet
from meister_guide.theme.palette import PALETTE

def test_stylesheet_includes_core_colors_and_widgets():
    qss = build_stylesheet()
    # New journal-theme palette tokens
    assert PALETTE["parchment"] in qss        # #e8dcc6 — primary text
    assert PALETTE["brass_bright"] in qss     # #e0bd66 — wordmark / selected tab
    assert PALETTE["parchment_dim"] in qss    # muted text
    assert "QPushButton" in qss
    assert "QScrollBar:vertical" in qss
    assert "width: 8px" in qss
    assert "QComboBox" in qss
    assert "QMenu" in qss
