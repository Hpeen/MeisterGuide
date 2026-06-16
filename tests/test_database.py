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
