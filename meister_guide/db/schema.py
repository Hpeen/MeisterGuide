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

# Phase 3: article mirror + full-text search.
# articles_fts is CONTENTLESS (content='') so it stores only the index, not the
# text — the readable body lives zlib-compressed in articles.body_zlib. There are
# no FTS triggers: the stored body is compressed, so ArticlesRepo keeps articles
# and articles_fts in sync explicitly inside one transaction.
PHASE3_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY,
        pageid INTEGER UNIQUE NOT NULL,
        title TEXT NOT NULL,
        body_zlib BLOB NOT NULL,
        revid INTEGER,
        url TEXT,
        game_id INTEGER REFERENCES games(id)
    )
    """,
    "CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(title, body, content='')",
    """
    CREATE TABLE IF NOT EXISTS scrape_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        continue_token TEXT,
        done INTEGER NOT NULL DEFAULT 0,
        total INTEGER,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

# Phase 6: redirect aliases. minecraft.wiki has many popular topics (e.g. "Wolf",
# "Redstone") that exist only as redirects to a canonical article; Phase 3's
# allpages ingest stored real pages only, so those queries returned nothing.
# `redirects` maps a redirect title -> the target article's pageid, and
# redirects_fts (contentless, rowid = redirects.id) lets search match the alias
# title and resolve to the target article. redirect_state mirrors scrape_state so
# the redirect walk resumes after an interruption.
PHASE6_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS redirects (
        id INTEGER PRIMARY KEY,
        title TEXT UNIQUE NOT NULL,
        target_pageid INTEGER NOT NULL,
        game_id INTEGER REFERENCES games(id)
    )
    """,
    "CREATE VIRTUAL TABLE IF NOT EXISTS redirects_fts USING fts5(title, content='')",
    """
    CREATE TABLE IF NOT EXISTS redirect_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        continue_token TEXT,
        done INTEGER NOT NULL DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]
