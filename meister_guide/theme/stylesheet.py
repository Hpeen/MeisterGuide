"""Builds the global QSS from the palette + loaded font families."""
from meister_guide.theme.palette import PALETTE
from meister_guide.theme import fonts


def build_stylesheet() -> str:
    p = PALETTE
    body = fonts.family("body")
    mono = fonts.family("mono")
    display = fonts.family("display")
    return f"""
    QWidget {{
        color: {p['parchment']};
        font-family: '{body}';
        font-size: 13px;
        background: transparent;
    }}
    #OverlayRoot {{ background: transparent; }}
    #Header {{ background: transparent; }}
    #Wordmark {{
        font-family: '{display}';
        font-size: 30px;
        color: {p['brass_bright']};
    }}
    #WordmarkSub {{
        font-family: '{mono}';
        font-size: 11px;
        letter-spacing: 4px;
        color: {p['parchment_ghost']};
    }}
    #HotkeyChip {{
        font-family: '{mono}';
        font-size: 10px;
        color: {p['parchment_ghost']};
        border: 1px solid rgba(200,161,74,0.22);
        border-radius: 6px;
        padding: 4px 8px;
    }}
    #CloseBtn {{
        border-radius: 7px;
        border: 1px solid rgba(200,161,74,0.25);
        background: rgba(0,0,0,0.25);
        color: {p['parchment_dim']};
    }}
    #CloseBtn:hover {{
        background: rgba(122,58,30,0.5);
        color: {p['parchment']};
        border-color: rgba(200,110,70,0.5);
    }}
    QToolButton#GamePill {{
        font-family: '{mono}';
        font-size: 10px;
        padding: 4px 9px;
        border-radius: 6px;
        border: 1px solid rgba(200,161,74,0.25);
        background: rgba(0,0,0,0.2);
        color: {p['parchment_dim']};
    }}
    QToolButton#GamePill[detected="true"] {{
        border: 1px solid rgba(120,170,90,0.4);
        background: rgba(80,130,60,0.14);
        color: {p['green_online']};
    }}
    QToolButton#GamePill::menu-indicator {{ image: none; width: 0; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        font-family: '{body}';
        font-size: 13px;
        font-weight: 600;
        background: transparent;
        color: {p['parchment_dim']};
        padding: 10px 14px;
        border: none;
    }}
    QTabBar::tab:selected {{
        color: {p['parchment']};
        border-bottom: 2px solid {p['brass_bright']};
    }}
    QPushButton {{
        background: rgba(0,0,0,0.2);
        border: 1px solid rgba(200,161,74,0.25);
        border-radius: 7px;
        padding: 6px 12px;
        color: {p['parchment']};
    }}
    QPushButton:hover {{
        background: rgba(200,161,74,0.12);
        border-color: rgba(200,161,74,0.45);
    }}
    QLineEdit {{
        background: rgba(0,0,0,0.28);
        border: 1px solid rgba(200,161,74,0.28);
        border-radius: 9px;
        padding: 8px 11px;
        color: {p['parchment']};
        font-family: '{body}';
    }}
    QTextBrowser, QListWidget {{
        background: rgba(0,0,0,0.2);
        border: 1px solid rgba(200,161,74,0.14);
        border-radius: 10px;
        color: {p['parchment_mid']};
    }}
    #Disclaimer {{
        color: {p['ink_dim']};
        font-family: '{mono}';
        font-size: 10px;
        background: transparent;
        border: none;
    }}
    #Footer {{ background: rgba(0,0,0,0.22); border-top: 1px solid rgba(200,161,74,0.16); }}
    #FooterNote, #FooterStack {{
        font-family: '{mono}';
        font-size: 10px;
        color: {p['ink_dim']};
    }}
    #FooterStack {{ color: {p['parchment_ghost']}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #4a3320; border-radius: 6px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
