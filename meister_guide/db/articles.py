"""Article mirror access: storage (zlib-compressed bodies + contentless FTS5),
full-text search, and the resumable scrape-state row."""
import re
import zlib
from dataclasses import dataclass
from typing import Optional

from meister_guide.scraper.excerpt import make_excerpt


@dataclass
class Article:
    pageid: int
    title: str
    body: str
    revid: Optional[int]
    url: Optional[str]


@dataclass
class SearchHit:
    pageid: int
    title: str
    excerpt_html: str
    url: Optional[str]


class ArticlesRepo:
    def __init__(self, conn):
        self._conn = conn

    def add_article(self, pageid, title, text, revid, url, commit=True) -> bool:
        """Insert one article + its FTS row. Skips (returns False) if the pageid
        is already stored, so a resumed/re-run ingest is idempotent.
        Pass commit=False to batch many inserts under one transaction."""
        body = zlib.compress(text.encode("utf-8"))
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO articles (pageid, title, body_zlib, revid, url) "
            "VALUES (?, ?, ?, ?, ?)",
            (pageid, title, body, revid, url),
        )
        if cur.rowcount == 0:
            return False
        self._conn.execute(
            "INSERT INTO articles_fts (rowid, title, body) VALUES (?, ?, ?)",
            (cur.lastrowid, title, text),
        )
        if commit:
            self._conn.commit()
        return True

    def get_article(self, pageid) -> Optional[Article]:
        row = self._conn.execute(
            "SELECT pageid, title, body_zlib, revid, url FROM articles WHERE pageid = ?",
            (pageid,),
        ).fetchone()
        if row is None:
            return None
        return Article(row[0], row[1], zlib.decompress(row[2]).decode("utf-8"),
                       row[3], row[4])

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def clear(self) -> None:
        # 'delete-all' is the supported way to empty a contentless FTS5 index.
        self._conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('delete-all')")
        self._conn.execute("DELETE FROM articles")
        self._conn.commit()

    def search(self, query, limit=50):
        fts_query = self._to_fts_query(query)
        if not fts_query:
            return []
        rows = self._conn.execute(
            "SELECT rowid FROM articles_fts WHERE articles_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        hits = []
        for (rowid,) in rows:
            row = self._conn.execute(
                "SELECT pageid, title, body_zlib, url FROM articles WHERE id = ?",
                (rowid,),
            ).fetchone()
            if row is None:
                continue
            body = zlib.decompress(row[2]).decode("utf-8")
            hits.append(SearchHit(row[0], row[1], make_excerpt(body, query), row[3]))
        return hits

    @staticmethod
    def _to_fts_query(query) -> str:
        """Turn free text into a safe FTS5 query: each word quoted (so special
        characters can't inject FTS syntax), ANDed, last word prefix-matched."""
        terms = re.findall(r"\w+", query or "", re.UNICODE)
        if not terms:
            return ""
        quoted = [f'"{t}"' for t in terms[:-1]]
        quoted.append(f'"{terms[-1]}"*')  # prefix match the word being typed
        return " ".join(quoted)


@dataclass
class ScrapeState:
    continue_token: Optional[str]
    done: int
    total: Optional[int]


class ScrapeStateRepo:
    """Single-row (id=1) ingest progress, so an interrupted download resumes."""

    def __init__(self, conn):
        self._conn = conn

    def load(self) -> ScrapeState:
        row = self._conn.execute(
            "SELECT continue_token, done, total FROM scrape_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return ScrapeState(None, 0, None)
        return ScrapeState(row[0], row[1], row[2])

    def save(self, state: ScrapeState, commit=True) -> None:
        self._conn.execute(
            "INSERT INTO scrape_state (id, continue_token, done, total, updated_at) "
            "VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET "
            "continue_token=excluded.continue_token, done=excluded.done, "
            "total=excluded.total, updated_at=CURRENT_TIMESTAMP",
            (state.continue_token, state.done, state.total),
        )
        if commit:
            self._conn.commit()
