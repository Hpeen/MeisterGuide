from meister_guide.ai.passage import relevant_passage


def test_passage_is_plain_text_window_around_match():
    body = "alpha " * 100 + "creeper explodes " + "omega " * 100
    out = relevant_passage(body, "creeper", width=80)
    assert "creeper" in out
    assert "<b>" not in out               # plain text, not HTML
    assert out.startswith("…") and out.endswith("…")
    assert len(out) <= 82                  # width + the two ellipses


def test_passage_no_match_returns_leading_text():
    out = relevant_passage("Redstone basics here.", "zzz", width=9)
    assert out.startswith("Redstone")
