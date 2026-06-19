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
