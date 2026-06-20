from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    for gid in (1, 2):
        conn.execute("INSERT INTO games (id, name, process_names) VALUES (?, ?, '[]')",
                     (gid, f"G{gid}"))
    conn.commit()
    return ArticlesRepo(conn)


def test_deletes_only_target_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "boom", 1, "u", game_id=1)
    repo.add_article(2, "Leviathan", "big", 2, "u", game_id=2)
    n = repo.delete_by_game(1)
    assert n == 1
    assert repo.count(game_id=1) == 0
    assert repo.count(game_id=2) == 1          # other game untouched


def test_fts_index_consistent_after_delete(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "it explodes", 1, "u", game_id=1)
    repo.add_article(2, "Creeper", "it explodes", 2, "u", game_id=2)
    repo.delete_by_game(1)
    # game 1's row is gone from the index; game 2's identical-title row remains
    hits = repo.search_ranked("creeper", limit=5, game_id=1)
    assert hits == []
    assert any(h.title == "Creeper" for h in repo.search_ranked("creeper", limit=5, game_id=2))


def test_idempotent_when_empty(tmp_path):
    repo = _repo(tmp_path)
    assert repo.delete_by_game(1) == 0
