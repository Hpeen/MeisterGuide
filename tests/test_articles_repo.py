from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    return ArticlesRepo(conn)


def test_add_and_get_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    inserted = repo.add_article(101, "Creeper", "A creeper explodes.", 5, "https://x/Creeper")
    assert inserted is True
    art = repo.get_article(101)
    assert art.title == "Creeper"
    assert art.body == "A creeper explodes."   # decompressed
    assert art.revid == 5
    assert repo.count() == 1


def test_add_is_idempotent_by_pageid(tmp_path):
    repo = _repo(tmp_path)
    assert repo.add_article(101, "Creeper", "first", 1, None) is True
    assert repo.add_article(101, "Creeper", "second", 2, None) is False  # skipped
    assert repo.count() == 1
    assert repo.get_article(101).body == "first"


def test_clear_empties_articles_and_index(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "A", "alpha", 1, None)
    repo.clear()
    assert repo.count() == 0
    assert repo.get_article(1) is None


def test_search_returns_ranked_highlighted_hits(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "A creeper is a hostile mob that explodes.", 1, "u1")
    repo.add_article(2, "Cow", "A cow is a passive animal.", 1, "u2")
    hits = repo.search("creeper")
    assert len(hits) == 1
    assert hits[0].pageid == 1
    assert hits[0].title == "Creeper"
    assert "<b>creeper</b>" in hits[0].excerpt_html.lower()


def test_search_empty_query_returns_nothing(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "explodes", 1, None)
    assert repo.search("   ") == []


def test_search_is_safe_with_fts_special_chars(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "explodes", 1, None)
    # Must not raise an FTS5 syntax error; returns a (possibly empty) list.
    assert isinstance(repo.search('creeper" OR ('), list)


def test_scrape_state_defaults_then_persists(tmp_path):
    from meister_guide.db.articles import ScrapeStateRepo, ScrapeState
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    repo = ScrapeStateRepo(conn)
    st = repo.load()
    assert st.continue_token is None and st.done == 0 and st.total is None
    repo.save(ScrapeState(continue_token='{"gapcontinue":"Boat"}', done=40, total=16689))
    again = repo.load()
    assert again.continue_token == '{"gapcontinue":"Boat"}'
    assert again.done == 40 and again.total == 16689
    repo.save(ScrapeState(continue_token=None, done=16689, total=16689))
    assert repo.load().continue_token is None


def test_search_ranked_surfaces_canonical_article_over_noise(tmp_path):
    from meister_guide.db.database import connect, init_db
    from meister_guide.db.articles import ArticlesRepo
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    repo = ArticlesRepo(conn)
    # canonical article + decoys that mention "creeper" a lot
    repo.add_article(1, "Creeper",
                     "A creeper is a hostile mob that creeps up and explodes. "
                     "Creeper creeper creeper.", 1, "u1")
    repo.add_article(2, "Creeper (disambiguation)",
                     "Creeper may refer to: creeper, creeper, creeper.", 1, "u2")
    repo.add_article(3, "Bedrock Edition beta 1.16.0.57",
                     "Changelog. Creeper creeper creeper creeper creeper.", 1, "u3")

    hits = repo.search_ranked("how do creepers work?", limit=3)
    assert hits, "expected at least one hit"
    assert hits[0].title == "Creeper"


def test_search_ranked_recovers_singular_article_for_plural_multiterm(tmp_path):
    # FTS5 doesn't stem: the AND query for "creepers explosion" matches the
    # decoy (which contains the literal plural) but not the singular "Creeper"
    # article. The always-merged de-inflected recall pass must still pull the
    # canonical article into the candidate pool.
    from meister_guide.db.database import connect, init_db
    from meister_guide.db.articles import ArticlesRepo
    conn = connect(tmp_path / "p.db")
    init_db(conn)
    repo = ArticlesRepo(conn)
    repo.add_article(1, "Creeper", "A creeper explodes in an explosion.", 1, "u1")
    repo.add_article(2, "Explosion",
                     "Creepers cause an explosion. explosion explosion creepers.",
                     1, "u2")
    titles = [h.title for h in repo.search_ranked("creepers explosion", limit=3)]
    assert "Creeper" in titles


def test_search_ranked_passes_computed_coverage_to_rerank(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    repo.add_article(2, "Spider",
                     "A spider is a mob. " + ("filler " * 200) +
                     "In Hard difficulty spiders spawn with a random status effect.",
                     None, "u2")
    import meister_guide.db.articles as articles_mod
    captured = {}
    real_rerank = articles_mod.rerank

    def spy(candidates, terms, limit, coverage=None):
        captured["coverage"] = coverage
        return real_rerank(candidates, terms, limit, coverage=coverage)

    monkeypatch.setattr(articles_mod, "rerank", spy)
    repo.search_ranked("when do spiders spawn with potion effects", limit=2)
    # search_ranked must compute a coverage dict and pass it (not None).
    assert captured["coverage"] is not None
    # Spider's clustered answer covers spider+spawn+effect (3 distinct), not potion.
    assert captured["coverage"].get(2, 0) >= 3


def test_search_ranked_prefers_topic_specific_article(tmp_path):
    repo = _repo(tmp_path)
    # Generic page: dense in the effect/potion words (strong bm25) but no spider.
    repo.add_article(1, "Effect",
                     "Effect potion effect effect potion brewing effect potion. " * 20,
                     None, "u1")
    # Specific page: contains the actual answer cluster below an intro.
    repo.add_article(2, "Spider",
                     "A spider is a mob. " + ("filler " * 200) +
                     "In Hard difficulty spiders spawn with a random status effect.",
                     None, "u2")
    hits = repo.search_ranked("when do spiders spawn with potion effects", limit=2)
    assert hits[0].title == "Spider"
