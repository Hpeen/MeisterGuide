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


def test_passage_includes_answer_below_intro():
    from meister_guide.ai.passage import relevant_passage
    intro = "A spider is a common mob. "
    filler = "filler " * 300                 # ~2100 chars, pushes answer past 1500
    answer = "In Hard difficulty, spiders spawn with a random status effect."
    body = intro + filler + answer
    # The raw question's stopwords (when/do/with) must not drag the window to 0.
    passage = relevant_passage(body, "when do spiders spawn with potion effects")
    assert "Hard difficulty" in passage
    assert "status effect" in passage


def test_passage_default_width_is_2000():
    from meister_guide.ai.passage import relevant_passage
    body = "creeper " * 1000
    passage = relevant_passage(body, "creeper")
    # ~2000-char window, not the old 1500.
    assert 1800 <= len(passage.strip("…")) <= 2000
