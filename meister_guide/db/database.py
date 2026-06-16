"""SQLite connection and schema initialisation."""
import os
import sqlite3
from pathlib import Path

from meister_guide.db.schema import CORE_TABLES, PHASE3_TABLES


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


def init_db(conn: sqlite3.Connection) -> None:
    """Create the core + Phase 3 tables if they don't exist. Idempotent."""
    for statement in CORE_TABLES + PHASE3_TABLES:
        conn.execute(statement)
    conn.commit()
