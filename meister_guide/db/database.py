"""SQLite connection and schema initialisation."""
import os
import shutil
import sqlite3
from pathlib import Path

from meister_guide.db.schema import (CORE_TABLES, PHASE3_TABLES, PHASE6_TABLES,
                                      SCRAPE_STATE_DDL, REDIRECT_STATE_DDL)


def default_db_path() -> Path:
    """%APPDATA%\\MeisterGuide\\meister.db (falls back to home if APPDATA unset)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MeisterGuide" / "meister.db"


def seed_db_if_missing(target, seed) -> bool:
    """Copy a bundled seed DB to `target` on first run. Copies only when `target`
    does not exist and `seed` does; returns whether a copy happened. Never
    overwrites an existing user DB, so upgrades keep the user's data."""
    target, seed = Path(target), Path(seed)
    if target.exists() or not seed.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed, target)
    return True


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


def _rebuild_state_table_if_legacy(conn, table, create_sql, cols, mc_id):
    """Old state tables were single-row (CHECK id=1). Rebuild to the game-keyed
    schema, moving the existing row to Minecraft. No-op once game_id exists."""
    existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if not existing:            # table doesn't exist yet — nothing to migrate
        return
    if "game_id" in existing:
        return
    conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
    conn.execute(create_sql)
    conn.execute(
        f"INSERT INTO {table} (game_id, {cols}) "
        f"SELECT ?, {cols} FROM {table}_legacy WHERE id = 1",
        (mc_id,),
    )
    conn.execute(f"DROP TABLE {table}_legacy")


def migrate_game_ids(conn: sqlite3.Connection) -> None:
    """Backfill NULL game_id rows to the seeded Minecraft game. Runs AFTER games
    are seeded (needs Minecraft's id). Idempotent — only touches NULL rows."""
    row = conn.execute("SELECT id FROM games WHERE name = 'Minecraft' "
                       "ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return
    mc_id = row[0]
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "articles" in tables:
        conn.execute("UPDATE articles SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    if "redirects" in tables:
        conn.execute("UPDATE redirects SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    _rebuild_state_table_if_legacy(conn, "scrape_state", SCRAPE_STATE_DDL,
                                   "continue_token, done, total, updated_at", mc_id)
    _rebuild_state_table_if_legacy(conn, "redirect_state", REDIRECT_STATE_DDL,
                                   "continue_token, done, updated_at", mc_id)
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
