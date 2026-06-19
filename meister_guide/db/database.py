"""SQLite connection and schema initialisation."""
import os
import sqlite3
from pathlib import Path

from meister_guide.db.schema import CORE_TABLES, PHASE3_TABLES, PHASE6_TABLES


def default_db_path() -> Path:
    """%APPDATA%\\MeisterGuide\\meister.db (falls back to home if APPDATA unset)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MeisterGuide" / "meister.db"


def connect(db_path) -> sqlite3.Connection:
    """Open (creating parent dirs as needed) a SQLite connection."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")  # tolerate the ingest writer
    return conn


def _ensure_column(conn, table, column, decl):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def migrate_game_ids(conn: sqlite3.Connection) -> None:
    """Backfill NULL game_id rows to the seeded Minecraft game. Runs AFTER games
    are seeded (needs Minecraft's id). Idempotent — only touches NULL rows."""
    row = conn.execute("SELECT id FROM games WHERE name = 'Minecraft' "
                       "ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return
    mc_id = row[0]
    conn.execute("UPDATE articles SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    conn.execute("UPDATE redirects SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Create the core + Phase 3 + Phase 6 tables if they don't exist, then add
    any columns missing from an older DB. Idempotent."""
    for statement in CORE_TABLES + PHASE3_TABLES + PHASE6_TABLES:
        conn.execute(statement)
    # Migrations for DBs created before a column existed (CREATE IF NOT EXISTS
    # won't add columns to an existing table).
    _ensure_column(conn, "articles", "game_id", "INTEGER REFERENCES games(id)")
    _ensure_column(conn, "redirects", "game_id", "INTEGER REFERENCES games(id)")
    conn.commit()
