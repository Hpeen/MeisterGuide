from meister_guide.theme.palette import PALETTE

def test_palette_has_all_roles_with_hex_values():
    expected = {
        "background": "#1C1208",
        "panel": "#2A1C0E",
        "surface_raised": "#3B2512",
        "accent_primary": "#C1440E",
        "accent_warm": "#E07B39",
        "accent_gold": "#D4A843",
        "text_primary": "#F0E2C8",
        "text_muted": "#8C7355",
        "border": "#5C3D1E",
        "success": "#7A9E4E",
        "error": "#C0392B",
    }
    assert PALETTE == expected
