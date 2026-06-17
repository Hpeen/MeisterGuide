from meister_guide.ai.ranking import noise_penalty


def test_real_article_titles_score_zero():
    for title in ["Creeper", "Nether", "Crafting Table", "Elytra", "Redstone"]:
        assert noise_penalty(title) == 0.0


def test_disambiguation_is_penalised_hardest():
    assert noise_penalty("Creeper (disambiguation)") > noise_penalty("Bedrock Edition 1.16.0")


def test_version_and_changelog_pages_penalised():
    assert noise_penalty("Bedrock Edition 1.16.0") > 0
    assert noise_penalty("Bedrock Edition beta 1.16.0.57") > 0
    assert noise_penalty("Java Edition 1.20") > 0
    assert noise_penalty("Bedrock Edition 1.2.0/Development versions") > 0


def test_history_and_movie_pages_penalised():
    assert noise_penalty("Bedrock Edition mob render history") > 0
    assert noise_penalty("A Minecraft Movie") > 0
    assert noise_penalty("A Minecraft Movie Live Event") > 0


# title_boost tests (Task 3)
from meister_guide.ai.ranking import title_boost


def test_exact_title_match_beats_partial_beats_none():
    exact = title_boost("Creeper", ["creeper"])
    partial = title_boost("Creeper Head", ["creeper"])
    none = title_boost("Wither", ["creeper"])
    assert exact > partial > none == 0.0


def test_all_terms_present_scores_high():
    assert title_boost("Nether Portal", ["nether", "portal"]) > \
        title_boost("Broken Nether Portal", ["nether", "portal"])


def test_no_terms_scores_zero():
    assert title_boost("Creeper", []) == 0.0
