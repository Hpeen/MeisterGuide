from meister_guide.scraper.excerpt import make_excerpt


def test_highlights_matched_term():
    out = make_excerpt("A creeper explodes near the player.", "creeper")
    assert "<b>creeper</b>" in out.lower()


def test_window_around_match_with_ellipsis():
    body = "x" * 500 + " creeper " + "y" * 500
    out = make_excerpt(body, "creeper", width=60)
    assert "creeper" in out.lower()
    assert out.startswith("…") and out.endswith("…")
    assert len(out) < 200  # windowed, not the whole 1000+ chars


def test_no_match_returns_leading_text():
    out = make_excerpt("Alpha beta gamma.", "zzz", width=10)
    assert out.startswith("Alpha")
    assert "<b>" not in out


def test_escapes_html_in_body():
    out = make_excerpt("danger <script> creeper", "creeper")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
