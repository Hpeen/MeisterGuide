from meister_guide.theme.palette import PALETTE


def test_new_design_tokens_present():
    # A representative slice of the handoff token set.
    for key in (
        "walnut_base", "walnut_mid", "walnut_light",
        "spine_top", "spine_mid", "spine_bottom",
        "brass_bright", "brass_mid", "brass_dark", "brass_deep",
        "parchment", "parchment_mid", "parchment_dim", "parchment_muted",
        "parchment_ghost", "ink_dim",
        "user_bubble_bg", "user_bubble_border",
        "ai_bubble_bg", "ai_bubble_border",
        "green_online", "warning_text",
    ):
        assert key in PALETTE, f"missing token {key}"
        assert PALETTE[key]


def test_legacy_keys_still_resolve():
    # Old code (stylesheet.py, woodgrain) references these — keep them working.
    for key in ("background", "panel", "surface_raised", "accent_primary",
                "accent_warm", "accent_gold", "text_primary", "text_muted",
                "border", "success", "error"):
        assert key in PALETTE and PALETTE[key]
