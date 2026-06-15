"""SQLite schema for Meister Guide. Phase 2 creates the 5 core tables.
The FTS5 search table is added in Phase 3."""

CORE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        process_names TEXT NOT NULL,  -- JSON array of strings
        wiki_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guides (
        id INTEGER PRIMARY KEY,
        game_id INTEGER REFERENCES games(id),
        title TEXT NOT NULL,
        url TEXT,
        content TEXT NOT NULL,
        scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY,
        game_id INTEGER REFERENCES games(id),
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        title TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY,
        session_id INTEGER REFERENCES chat_sessions(id),
        role TEXT NOT NULL,  -- 'user' or 'assistant'
        content TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
]
