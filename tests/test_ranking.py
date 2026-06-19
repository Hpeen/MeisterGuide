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


def test_plural_query_term_matches_singular_title():
    # De-inflection: a plural cleaned term must still score the singular title as
    # an exact match, so "creepers" promotes the "Creeper" article to #1.
    assert title_boost("Creeper", ["creepers"]) == title_boost("Creeper", ["creeper"])
    assert title_boost("Creeper", ["creepers"]) > title_boost("Creeper Head", ["creepers"])


# rerank tests (Task 4)
from collections import namedtuple
from meister_guide.ai.ranking import rerank

Hit = namedtuple("Hit", "pageid title excerpt_html url")


def _hit(title):
    return Hit(1, title, "", None)


def test_rerank_surfaces_creeper_over_noise():
    # (bm25 rank, hit). More-negative rank = better keyword score in FTS5.
    # The changelogs even have *better* bm25 here, but must still lose.
    candidates = [
        (-9.0, _hit("Bedrock Edition beta 1.16.0.57")),
        (-8.5, _hit("Creeper (disambiguation)")),
        (-3.0, _hit("Creeper")),
        (-2.0, _hit("Creeper Head")),
    ]
    titles = [h.title for h in rerank(candidates, ["creeper"], limit=3)]
    # The two clean Creeper articles must outrank both noise pages, and the
    # disambiguation page (penalised hardest) must drop out of the top 3.
    assert titles[:2] == ["Creeper", "Creeper Head"]
    assert "Creeper (disambiguation)" not in titles


def test_rerank_respects_limit():
    candidates = [(-1.0, _hit(f"Article {i}")) for i in range(10)]
    assert len(rerank(candidates, ["article"], limit=3)) == 3


def test_rerank_empty_returns_empty():
    assert rerank([], ["creeper"], limit=3) == []


# coverage boost tests (Task 5)
def _covhit(pageid, title):
    return Hit(pageid, title, "", None)


def test_coverage_boost_lifts_specific_over_generic():
    terms = ["spider", "spawn", "potion", "effect"]
    # Generic "Effect" has the better bm25 rank (more negative) but low coverage;
    # the specific article covers more distinct query terms.
    candidates = [(-9.0, _covhit(1, "Effect")), (-3.0, _covhit(2, "Cave Spider"))]
    coverage = {1: 2, 2: 3}
    ordered = rerank(candidates, terms, limit=2, coverage=coverage)
    assert ordered[0].pageid == 2   # Cave Spider wins on coverage

def test_rerank_without_coverage_is_unchanged():
    terms = ["spider", "spawn", "potion", "effect"]
    candidates = [(-9.0, _covhit(1, "Effect")), (-3.0, _covhit(2, "Cave Spider"))]
    ordered = rerank(candidates, terms, limit=2)   # no coverage arg
    assert ordered[0].pageid == 1   # bm25 (more negative) wins the title tie
