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
