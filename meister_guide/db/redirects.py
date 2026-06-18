"""Redirect-alias access: maps a redirect title (e.g. "Wolf") to the pageid of
the canonical article it points to, plus a contentless FTS index over the alias
titles so chat retrieval can match an alias and resolve it to the real article.
Mirrors the storage/idempotency style of ArticlesRepo."""
from dataclasses import dataclass
from typing import Optional


class RedirectsRepo:
    def __init__(self, conn):
        self._conn = conn

    def add_redirect(self, title, target_pageid, commit=True) -> bool:
        """Insert one alias title -> target pageid + its FTS row. Skips (returns
        False) if the title is already stored, so a resumed/re-run walk is
        idempotent. Pass commit=False to batch many inserts under one txn."""
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO redirects (title, target_pageid) VALUES (?, ?)",
            (title, target_pageid),
        )
        if cur.rowcount == 0:
            return False
        self._conn.execute(
            "INSERT INTO redirects_fts (rowid, title) VALUES (?, ?)",
            (cur.lastrowid, title),
        )
        if commit:
            self._conn.commit()
        return True

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM redirects").fetchone()[0]

    def clear(self) -> None:
        # 'delete-all' is the supported way to empty a contentless FTS5 index.
        self._conn.execute("INSERT INTO redirects_fts(redirects_fts) VALUES('delete-all')")
        self._conn.execute("DELETE FROM redirects")
        self._conn.commit()


@dataclass
class RedirectState:
    continue_token: Optional[str]
    done: int


class RedirectStateRepo:
    """Single-row (id=1) redirect-walk progress, so an interrupted walk resumes.
    No `total` field: the redirect count isn't exposed as a cheap statistic the
    way the article count is, so progress is reported as a running count only."""

    def __init__(self, conn):
        self._conn = conn

    def load(self) -> RedirectState:
        row = self._conn.execute(
            "SELECT continue_token, done FROM redirect_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return RedirectState(None, 0)
        return RedirectState(row[0], row[1])

    def save(self, state: RedirectState, commit=True) -> None:
        self._conn.execute(
            "INSERT INTO redirect_state (id, continue_token, done, updated_at) "
            "VALUES (1, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET "
            "continue_token=excluded.continue_token, done=excluded.done, "
            "updated_at=CURRENT_TIMESTAMP",
            (state.continue_token, state.done),
        )
        if commit:
            self._conn.commit()
