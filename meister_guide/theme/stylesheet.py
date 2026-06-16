"""Builds the global QSS stylesheet from the palette."""
from meister_guide.theme.palette import PALETTE


def build_stylesheet() -> str:
    p = PALETTE
    return f"""
    QWidget {{
        color: {p['text_primary']};
        font-family: 'Segoe UI';
        font-size: 13px;
    }}
    #OverlayRoot {{
        background-color: {p['background']};
        border: 1px solid {p['border']};
        border-radius: 4px;
    }}
    #Spine {{
        background-color: {p['accent_primary']};
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }}
    #Header {{
        background-color: {p['panel']};
    }}
    #HeaderTitle {{
        font-family: 'Palatino Linotype', 'Book Antiqua', Georgia, serif;
        font-size: 16px;
        font-weight: 700;
        color: {p['accent_gold']};
    }}
    #GameIndicator {{
        color: {p['text_muted']};
    }}
    #Disclaimer {{
        background-color: {p['surface_raised']};
        color: {p['text_muted']};
        font-size: 11px;
        border-bottom: 1px solid {p['border']};
    }}
    QPushButton {{
        background-color: {p['surface_raised']};
        border: 1px solid {p['accent_primary']};
        border-radius: 4px;
        padding: 4px 10px;
        color: {p['text_primary']};
    }}
    QPushButton:hover {{
        background-color: {p['accent_primary']};
        color: {p['background']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p['text_muted']};
        padding: 6px 14px;
        font-family: 'Segoe UI';
    }}
    QTabBar::tab:selected {{
        color: {p['accent_gold']};
        border-bottom: 3px solid {p['accent_warm']};
    }}
    QTabWidget::pane {{
        border: none;
    }}
    #Footer {{
        background-color: {p['panel']};
        color: {p['text_muted']};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p['border']};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """
