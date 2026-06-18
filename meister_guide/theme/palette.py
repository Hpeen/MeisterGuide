"""Rustic carpenter's-journal palette. Source of truth for all UI colors.

New design tokens come from the Phase-10 design handoff. Legacy keys
(background, panel, …) are kept as aliases so existing QSS keeps working."""

PALETTE = {
    # --- walnut panel ---
    "walnut_base": "#1a110b",
    "walnut_mid": "#251810",
    "walnut_light": "#1f150d",
    # --- leather spine ---
    "spine_top": "#8a4423",
    "spine_mid": "#6e3318",
    "spine_bottom": "#7a3a1e",
    # --- brass ramp ---
    "brass_bright": "#e0bd66",
    "brass_mid": "#c8a14a",
    "brass_dark": "#b8923f",
    "brass_deep": "#6b4f1d",
    # --- parchment text ---
    "parchment": "#e8dcc6",
    "parchment_mid": "#d8cbb0",
    "parchment_dim": "#b8a988",
    "parchment_muted": "#a89878",
    "parchment_ghost": "#9c8a66",
    "ink_dim": "#7a6a4f",
    # --- chat bubbles (used in Phase 11, defined now) ---
    "user_bubble_bg": "rgba(122,58,30,0.32)",
    "user_bubble_border": "rgba(200,110,70,0.35)",
    "ai_bubble_bg": "rgba(0,0,0,0.26)",
    "ai_bubble_border": "rgba(200,161,74,0.18)",
    # --- status ---
    "green_online": "#8fd058",
    "warning_text": "#b06a4a",

    # --- legacy aliases (do not remove; referenced by older code) ---
    "background": "#1a110b",      # -> walnut_base
    "panel": "#251810",           # -> walnut_mid
    "surface_raised": "#3B2512",
    "accent_primary": "#8a4423",  # -> spine_top
    "accent_warm": "#E07B39",
    "accent_gold": "#e0bd66",     # -> brass_bright
    "text_primary": "#e8dcc6",    # -> parchment
    "text_muted": "#9c8a66",      # -> parchment_ghost
    "border": "#5C3D1E",
    "success": "#8fd058",
    "error": "#C0392B",
}
