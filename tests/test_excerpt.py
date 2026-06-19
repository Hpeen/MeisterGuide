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


def test_overlapping_terms_do_not_nest_bold_tags():
    out = make_excerpt("creepers creep slowly", "creep creepers")
    assert "<b><b>" not in out
    assert "</b></b>" not in out
    assert "<b>creepers</b>" in out


def test_window_bounds_centers_on_match():
    from meister_guide.scraper.excerpt import window_bounds
    body = "x" * 100 + "creeper" + "y" * 100
    start, end = window_bounds(body, "creeper", 60)
    assert start <= 100 < end          # the match (at index 100) is inside
    assert end - start <= 60


def test_window_bounds_no_match_is_leading_window():
    from meister_guide.scraper.excerpt import window_bounds
    assert window_bounds("alpha beta", "zzz", 5) == (0, 5)


def test_deinflect_strips_plurals():
    from meister_guide.scraper.excerpt import deinflect
    assert deinflect("spiders") == "spider"
    assert deinflect("effects") == "effect"
    assert deinflect("torches") == "torch"   # 'es' rule
    assert deinflect("ash") == "ash"          # too short to strip
    assert deinflect("redstone") == "redstone"


def test_best_window_picks_densest_cluster_not_intro():
    from meister_guide.scraper.excerpt import best_window
    intro = "A spider is a mob. "                 # only 'spider' near index 0
    filler = "filler " * 300                       # ~2100 chars
    answer = "In Hard difficulty spiders spawn with a status effect."
    body = intro + filler + answer
    terms = ["spiders", "spawn", "potion", "effects"]
    start, end, distinct = best_window(body, terms, 2000)
    assert body[start:end].find("Hard difficulty") != -1   # answer is inside
    assert distinct >= 3                                    # spider+spawn+effect


def test_best_window_single_term_centers_on_match():
    from meister_guide.scraper.excerpt import best_window
    body = "x" * 100 + "creeper" + "y" * 100
    start, end, distinct = best_window(body, ["creeper"], 60)
    assert start <= 100 < end
    assert distinct == 1
    assert end - start <= 60


def test_best_window_no_match_is_leading_window():
    from meister_guide.scraper.excerpt import best_window
    assert best_window("alpha beta", ["zzz"], 5) == (0, 5, 0)
