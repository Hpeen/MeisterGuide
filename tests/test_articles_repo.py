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
