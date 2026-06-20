"""Article mirror access: storage (zlib-compressed bodies + contentless FTS5),
full-text search, and the resumable scrape-state row."""
import re
import zlib
from dataclasses import dataclass
from typing import Optional

from meister_guide.scraper.excerpt import make_excerpt, deinflect, best_window
from meister_guide.ai.query import clean_query
from meister_guide.ai.ranking import rerank


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

    def add_article(self, pageid, title, text, revid, url, game_id=None, commit=True) -> bool:
        """Insert one article + its FTS row. Skips (returns False) if the pageid
        is already stored, so a resumed/re-run ingest is idempotent.
        Pass commit=False to batch many inserts under one transaction."""
        body = zlib.compress(text.encode("utf-8"))
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO articles "
            "(pageid, title, body_zlib, revid, url, game_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pageid, title, body, revid, url, game_id),
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

    def pageid_by_title(self, title) -> Optional[int]:
        """Exact-title lookup used by redirect ingestion to map a redirect's
        target title onto a stored article's pageid."""
        row = self._conn.execute(
            "SELECT pageid FROM articles WHERE title = ?", (title,)
        ).fetchone()
        return row[0] if row else None

    def count(self, game_id=None) -> int:
        if game_id is None:
            return self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM articles WHERE game_id = ?", (game_id,)
        ).fetchone()[0]

    def clear(self) -> None:
        # 'delete-all' is the supported way to empty a contentless FTS5 index.
        self._conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('delete-all')")
        self._conn.execute("DELETE FROM articles")
        self._conn.commit()

    def prune_noise(self, is_noise) -> int:
        """Delete stored articles whose title matches `is_noise(title)` plus their
        contentless-FTS rows; return the number pruned. One-time cleanup for a
        corpus downloaded before noise filtering existed. Contentless FTS5 needs
        the original column values supplied to delete an index row, so the body is
        decompressed and passed to the 'delete' command."""
        rows = self._conn.execute(
            "SELECT id, title, body_zlib FROM articles"
        ).fetchall()
        pruned = 0
        for id_, title, body_zlib in rows:
            if not is_noise(title):
                continue
            body = zlib.decompress(body_zlib).decode("utf-8")
            self._conn.execute(
                "INSERT INTO articles_fts(articles_fts, rowid, title, body) "
                "VALUES('delete', ?, ?, ?)",
                (id_, title, body),
            )
            self._conn.execute("DELETE FROM articles WHERE id = ?", (id_,))
            pruned += 1
        self._conn.commit()
        return pruned

    def delete_by_game(self, game_id) -> int:
        """Delete all articles for one game plus their contentless-FTS rows;
        return the number deleted. Contentless FTS5 needs the original column
        values supplied to delete an index row, so the body is decompressed and
        passed to the 'delete' command (same pattern as prune_noise)."""
        rows = self._conn.execute(
            "SELECT id, title, body_zlib FROM articles WHERE game_id = ?",
            (game_id,),
        ).fetchall()
        for id_, title, body_zlib in rows:
            body = zlib.decompress(body_zlib).decode("utf-8")
            self._conn.execute(
                "INSERT INTO articles_fts(articles_fts, rowid, title, body) "
                "VALUES('delete', ?, ?, ?)",
                (id_, title, body),
            )
            self._conn.execute("DELETE FROM articles WHERE id = ?", (id_,))
        self._conn.commit()
        return len(rows)

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

    def search_ranked(self, raw_query, limit=3, candidate_pool=15, game_id=None):
        """Chat retrieval: clean the query to content terms, pull a pool of FTS
        candidates with their bm25 rank, then re-rank so the canonical article
        wins over changelog/disambiguation noise. Returns up to `limit` SearchHits.
        The Guides-tab `search()` is intentionally separate and unchanged."""
        terms = clean_query(raw_query)
        if not terms:
            return []
        # Two passes, always merged: a strict AND query (precise when the terms
        # are already the indexed root) and a de-inflected OR query (recall — so
        # a plural question like "creepers" still reaches the singular "creeper"
        # article). FTS5 doesn't stem, so without the recall pass a multi-term
        # plural query whose AND form happens to match some other page would
        # never pull the canonical article into the pool. Dedupe by rowid,
        # keeping the best (most-negative) bm25 rank, then re-rank.
        best_rank = {}
        for fts in (self._to_fts_query(" ".join(terms)),
                    self._terms_to_or_query(terms)):
            if not fts:
                continue
            if game_id is None:
                pass_rows = self._conn.execute(
                    "SELECT rowid, rank FROM articles_fts WHERE articles_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (fts, candidate_pool),
                ).fetchall()
            else:
                # FTS5 MATCH must name the virtual table itself (`articles_fts`),
                # not the alias `f` — the aliased form raises a syntax error here.
                pass_rows = self._conn.execute(
                    "SELECT f.rowid, f.rank FROM articles_fts f "
                    "JOIN articles a ON a.id = f.rowid "
                    "WHERE articles_fts MATCH ? AND a.game_id = ? "
                    "ORDER BY f.rank LIMIT ?",
                    (fts, game_id, candidate_pool),
                ).fetchall()
            for rowid, rank in pass_rows:
                if rowid not in best_rank or rank < best_rank[rowid]:
                    best_rank[rowid] = rank
            # Redirect aliases: match the same query against alias titles and
            # resolve each to its target article's rowid, folding it into the
            # same pool. This is the only way a redirect-only topic (e.g. "Wolf",
            # which has no article of its own) reaches retrieval at all.
            if game_id is None:
                redir_rows = self._conn.execute(
                    "SELECT a.id, rf.rank FROM redirects_fts rf "
                    "JOIN redirects r ON r.id = rf.rowid "
                    "JOIN articles a ON a.pageid = r.target_pageid "
                    "WHERE redirects_fts MATCH ? ORDER BY rf.rank LIMIT ?",
                    (fts, candidate_pool),
                ).fetchall()
            else:
                redir_rows = self._conn.execute(
                    "SELECT a.id, rf.rank FROM redirects_fts rf "
                    "JOIN redirects r ON r.id = rf.rowid "
                    "JOIN articles a ON a.pageid = r.target_pageid "
                    "WHERE redirects_fts MATCH ? AND a.game_id = ? "
                    "ORDER BY rf.rank LIMIT ?",
                    (fts, game_id, candidate_pool),
                ).fetchall()
            for rowid, rank in redir_rows:
                if rowid not in best_rank or rank < best_rank[rowid]:
                    best_rank[rowid] = rank
        candidates = []
        coverage = {}
        for rowid, rank in best_rank.items():
            row = self._conn.execute(
                "SELECT pageid, title, body_zlib, url FROM articles WHERE id = ?",
                (rowid,),
            ).fetchone()
            if row is None:
                continue
            body = zlib.decompress(row[2]).decode("utf-8")
            hit = SearchHit(row[0], row[1], make_excerpt(body, raw_query), row[3])
            # Topic coverage = distinct query terms inside the best passage window
            # (same width as the RAG passage), reused by rerank to favor specifics.
            _, _, cov = best_window(body, terms, 2000)
            coverage[hit.pageid] = cov
            candidates.append((rank, hit))
        return rerank(candidates, terms, limit, coverage=coverage)

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

    @staticmethod
    def _terms_to_or_query(terms) -> str:
        """Build a broad OR query for `search_ranked` fallback. Each term is
        prefix-matched; inflected forms (e.g. 'creepers') also try a stripped
        root ('creeper') so un-stemmed FTS5 indexes still return candidates."""
        parts = []
        seen = set()
        for t in terms:
            candidates_t = [t]
            root = deinflect(t)
            if root != t:
                candidates_t.append(root)
            for candidate in candidates_t:
                if candidate not in seen:
                    seen.add(candidate)
                    parts.append(f'"{candidate}"*')
        return " OR ".join(parts)


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
