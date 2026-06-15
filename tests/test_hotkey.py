from meister_guide.input.hotkey import parse_hotkey, MOD_ALT, MOD_CONTROL, MOD_SHIFT

def test_parse_alt_insert():
    mods, vk = parse_hotkey("Alt+Insert")
    assert mods == MOD_ALT
    assert vk == 0x2D  # VK_INSERT

def test_parse_ctrl_shift_g():
    mods, vk = parse_hotkey("Ctrl+Shift+G")
    assert mods == (MOD_CONTROL | MOD_SHIFT)
    assert vk == ord("G")

def test_parse_is_case_insensitive_on_modifiers():
    mods, vk = parse_hotkey("alt+insert")
    assert mods == MOD_ALT
    assert vk == 0x2D
