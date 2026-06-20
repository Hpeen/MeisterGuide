from meister_guide.db.database import connect, init_db
from meister_guide.db.redirects import RedirectsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    for gid in (1, 2):
        conn.execute("INSERT INTO games (id, name, process_names) VALUES (?, ?, '[]')",
                     (gid, f"G{gid}"))
    conn.commit()
    return RedirectsRepo(conn)


def test_count_by_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.add_redirect("Doggo", 10, game_id=1)
    repo.add_redirect("Reaper", 20, game_id=2)
    assert repo.count_by_game(1) == 2
    assert repo.count_by_game(2) == 1


def test_deletes_only_target_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.add_redirect("Reaper", 20, game_id=2)
    n = repo.delete_by_game(1)
    assert n == 1
    assert repo.count_by_game(1) == 0
    assert repo.count_by_game(2) == 1


def test_fts_index_consistent_after_delete(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.delete_by_game(1)
    rows = repo._conn.execute(
        "SELECT COUNT(*) FROM redirects_fts WHERE redirects_fts MATCH ?", ("Wolf",)
    ).fetchone()[0]
    assert rows == 0


def test_idempotent_when_empty(tmp_path):
    repo = _repo(tmp_path)
    assert repo.delete_by_game(1) == 0
