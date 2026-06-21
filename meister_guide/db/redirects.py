"""Redirect-alias access: maps a redirect title (e.g. "Wolf") to the pageid of
the canonical article it points to, plus a contentless FTS index over the alias
titles so chat retrieval can match an alias and resolve it to the real article.
Mirrors the storage/idempotency style of ArticlesRepo."""
from dataclasses import dataclass
from typing import Optional


class RedirectsRepo:
    def __init__(self, conn):
        self._conn = conn

    def add_redirect(self, title, target_pageid, game_id=None, commit=True) -> bool:
        """Insert one alias title -> target pageid + its FTS row. Skips (returns
        False) if the title is already stored, so a resumed/re-run walk is
        idempotent. Pass commit=False to batch many inserts under one txn."""
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO redirects (title, target_pageid, game_id) VALUES (?, ?, ?)",
            (title, target_pageid, game_id),
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

    def count_by_game(self, game_id) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM redirects WHERE game_id = ?", (game_id,)
        ).fetchone()[0]

    def delete_by_game(self, game_id) -> int:
        """Delete all redirect aliases for one game plus their contentless-FTS
        rows; return the number deleted. Contentless FTS5 needs the original
        title supplied to delete an index row."""
        rows = self._conn.execute(
            "SELECT id, title FROM redirects WHERE game_id = ?", (game_id,)
        ).fetchall()
        for id_, title in rows:
            self._conn.execute(
                "INSERT INTO redirects_fts(redirects_fts, rowid, title) "
                "VALUES('delete', ?, ?)",
                (id_, title),
            )
            self._conn.execute("DELETE FROM redirects WHERE id = ?", (id_,))
        self._conn.commit()
        return len(rows)

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
    """Per-game redirect-walk progress (keyed by game_id) so an interrupted walk
    resumes. No `total`: the redirect count isn't a cheap statistic, so progress
    is a running count only."""

    def __init__(self, conn):
        self._conn = conn

    def load(self, game_id) -> RedirectState:
        row = self._conn.execute(
            "SELECT continue_token, done FROM redirect_state WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return RedirectState(None, 0)
        return RedirectState(row[0], row[1])

    def save(self, state: RedirectState, game_id, commit=True) -> None:
        self._conn.execute(
            "INSERT INTO redirect_state (game_id, continue_token, done, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(game_id) DO UPDATE SET "
            "continue_token=excluded.continue_token, done=excluded.done, "
            "updated_at=CURRENT_TIMESTAMP",
            (game_id, state.continue_token, state.done),
        )
        if commit:
            self._conn.commit()
