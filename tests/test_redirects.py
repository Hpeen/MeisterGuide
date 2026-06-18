from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.redirects import (
    RedirectsRepo, RedirectState, RedirectStateRepo,
)


def _conn(tmp_path, name="r.db"):
    conn = connect(tmp_path / name)
    init_db(conn)
    return conn


def test_add_redirect_roundtrip_and_count(tmp_path):
    repo = RedirectsRepo(_conn(tmp_path))
    assert repo.add_redirect("Wolf", 42) is True
    assert repo.count() == 1


def test_add_redirect_is_idempotent_by_title(tmp_path):
    repo = RedirectsRepo(_conn(tmp_path))
    assert repo.add_redirect("Wolf", 42) is True
    assert repo.add_redirect("Wolf", 99) is False   # same alias title -> skipped
    assert repo.count() == 1


def test_clear_empties_redirects_and_index(tmp_path):
    repo = RedirectsRepo(_conn(tmp_path))
    repo.add_redirect("Wolf", 42)
    repo.clear()
    assert repo.count() == 0


def test_pageid_by_title(tmp_path):
    conn = _conn(tmp_path)
    arts = ArticlesRepo(conn)
    arts.add_article(7, "Wolf (mob)", "Wolves are tameable.", 1, "u")
    assert arts.pageid_by_title("Wolf (mob)") == 7
    assert arts.pageid_by_title("Nonexistent") is None


def test_search_ranked_resolves_redirect_alias_to_target_article(tmp_path):
    # The canonical content lives under a title/body that never mention "wolf";
    # "Wolf" exists only as a redirect. A query for "wolf" has no direct FTS hit
    # and can reach the target purely through the redirect alias.
    conn = _conn(tmp_path)
    arts = ArticlesRepo(conn)
    reds = RedirectsRepo(conn)
    arts.add_article(7, "Canine Companion",
                     "A tameable neutral mob that can be bred with bones.", 1, "u7")
    arts.add_article(8, "Cow", "A cow is a passive animal.", 1, "u8")
    reds.add_redirect("Wolf", 7)

    # Sanity: with no redirect resolution this query would find nothing.
    titles = [h.title for h in arts.search_ranked("what is a wolf?", limit=3)]
    assert "Canine Companion" in titles


def test_redirect_state_defaults_then_persists(tmp_path):
    repo = RedirectStateRepo(_conn(tmp_path))
    st = repo.load()
    assert st.continue_token is None and st.done == 0
    repo.save(RedirectState(continue_token='{"apcontinue":"Boat"}', done=12))
    again = repo.load()
    assert again.continue_token == '{"apcontinue":"Boat"}' and again.done == 12
    repo.save(RedirectState(continue_token=None, done=50))
    assert repo.load().continue_token is None and repo.load().done == 50
