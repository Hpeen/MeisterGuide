import sqlite3
from meister_guide.db.database import connect, init_db


def test_init_creates_all_core_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"games", "guides", "chat_sessions", "chat_messages", "settings"} <= names


def test_init_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    init_db(conn)  # must not raise
    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 0


def test_phase3_tables_exist(tmp_path):
    from meister_guide.db.database import connect, init_db
    conn = connect(tmp_path / "p3.db")
    init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()}
    assert "articles" in names
    assert "articles_fts" in names
    assert "scrape_state" in names
    # contentless FTS accepts an indexed insert and a MATCH
    conn.execute("INSERT INTO articles_fts(rowid, title, body) VALUES (1, 'Creeper', 'explodes')")
    rows = conn.execute(
        "SELECT rowid FROM articles_fts WHERE articles_fts MATCH 'explodes'"
    ).fetchall()
    assert rows == [(1,)]


def test_init_db_adds_game_id_to_existing_old_shape_db(tmp_path):
    import sqlite3
    from meister_guide.db.database import connect, init_db
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    # Simulate a pre-migration DB: articles/redirects WITHOUT game_id.
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, pageid INTEGER "
                 "UNIQUE NOT NULL, title TEXT NOT NULL, body_zlib BLOB NOT NULL, "
                 "revid INTEGER, url TEXT)")
    conn.execute("CREATE TABLE redirects (id INTEGER PRIMARY KEY, title TEXT "
                 "UNIQUE NOT NULL, target_pageid INTEGER NOT NULL)")
    conn.commit(); conn.close()

    conn = connect(path)
    init_db(conn)                      # must ALTER in the missing column
    cols_a = [r[1] for r in conn.execute("PRAGMA table_info(articles)")]
    cols_r = [r[1] for r in conn.execute("PRAGMA table_info(redirects)")]
    assert "game_id" in cols_a
    assert "game_id" in cols_r
    init_db(conn)                      # idempotent: re-run must not raise


def test_migrate_game_ids_backfills_null_rows_to_minecraft(tmp_path):
    import zlib
    from meister_guide.db.database import connect, init_db, migrate_game_ids
    from meister_guide.db.games import GamesRepo
    conn = connect(tmp_path / "m.db"); init_db(conn)
    games = GamesRepo(conn); games.seed_defaults()
    mc = next(g for g in games.list_games() if g.name == "Minecraft")
    # Add a second game to use as the "already-set" sentinel (FK constraint is ON).
    other = games.add("OtherGame", [], None)
    other_id = other.id
    # Insert rows with NULL game_id (pre-migration shape) + one already-set row.
    conn.execute("INSERT INTO articles (pageid, title, body_zlib, game_id) "
                 "VALUES (1, 'A', ?, NULL)", (zlib.compress(b'x'),))
    conn.execute("INSERT INTO articles (pageid, title, body_zlib, game_id) "
                 "VALUES (2, 'B', ?, ?)", (zlib.compress(b'y'), other_id))
    conn.execute("INSERT INTO redirects (title, target_pageid, game_id) "
                 "VALUES ('R', 1, NULL)")
    conn.commit()

    migrate_game_ids(conn)

    rows = dict(conn.execute("SELECT pageid, game_id FROM articles"))
    assert rows[1] == mc.id          # NULL backfilled to Minecraft
    assert rows[2] == other_id       # already-set row untouched
    assert conn.execute("SELECT game_id FROM redirects WHERE title='R'").fetchone()[0] == mc.id
    migrate_game_ids(conn)           # idempotent: no error, no change
    assert dict(conn.execute("SELECT pageid, game_id FROM articles"))[1] == mc.id
