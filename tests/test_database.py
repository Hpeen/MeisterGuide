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
