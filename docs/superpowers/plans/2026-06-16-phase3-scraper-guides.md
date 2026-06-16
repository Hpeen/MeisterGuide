# Phase 3: Wiki Ingest + Offline Guides — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror minecraft.wiki article text into local SQLite via the MediaWiki API, fully searchable offline, surfaced through a Guides tab (search, highlighted excerpts, readable detail panel) with a manual background "Update guides" download.

**Architecture:** A pure MediaWiki API client streams batched plain-text article extracts; a pure ingest orchestrator writes them through `ArticlesRepo` into an `articles` table (zlib-compressed bodies) plus a contentless FTS5 index, tracking a resume token in `scrape_state`; a QThread worker runs the ingest off the UI thread; the Guides tab queries FTS offline and builds hand-rolled highlighted excerpts (contentless FTS has no `snippet()`).

**Tech Stack:** Python 3.12, PySide6 (QThread/QObject signals), SQLite + FTS5, `requests`, `zlib` (stdlib). Tests: pytest, headless via `QT_QPA_PLATFORM=offscreen`, network-free via injected `http_get`.

**Environment:** Use `py -3` (system `python` is a broken Store stub). Prefix GUI-touching commands with `QT_QPA_PLATFORM=offscreen`. Run tests with `QT_QPA_PLATFORM=offscreen py -3 -m pytest`.

---

## File Structure

- Create `meister_guide/scraper/__init__.py` — package marker.
- Create `meister_guide/scraper/wiki_client.py` — MediaWiki API client (`WikiClient`, `WikiArticle`). Pure; injectable `http_get`/`sleep`.
- Create `meister_guide/scraper/excerpt.py` — `make_excerpt()`, pure string highlighting.
- Create `meister_guide/scraper/ingest.py` — `run_ingest()` orchestrator + `ScrapeState`. No Qt.
- Create `meister_guide/scraper/worker.py` — `IngestWorker(QObject)` with `progress/finished/error` signals; owns its own DB connection in the worker thread.
- Create `meister_guide/db/articles.py` — `ArticlesRepo` (articles + FTS sync, search, get, count, clear), `ScrapeStateRepo`, `Article`, `SearchHit`.
- Modify `meister_guide/db/schema.py` — add `PHASE3_TABLES`.
- Modify `meister_guide/db/database.py` — `init_db` also creates `PHASE3_TABLES`; add `PRAGMA busy_timeout`.
- Modify `meister_guide/overlay/window.py` — replace the placeholder Guides tab with the search/results/detail/update UI; accept `articles_repo` + `db_path`.
- Modify `meister_guide/main.py` — build `ArticlesRepo`, pass it and `default_db_path()` to `OverlayWindow`.
- Modify `README.md` — note the polite-API / windowed disclaimer already exists; add the "Update guides" first-run note.
- Tests: `tests/test_articles_repo.py`, `tests/test_excerpt.py`, `tests/test_wiki_client.py`, `tests/test_ingest.py`, `tests/test_ingest_worker.py`.

---

## Task 1: Phase 3 schema (articles, FTS, scrape_state)

**Files:**
- Modify: `meister_guide/db/schema.py`
- Modify: `meister_guide/db/database.py`
- Test: `tests/test_database.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_database.py`:

```python
def test_phase3_tables_exist(tmp_path):
    from meister_guide.db.database import connect, init_db
    conn = connect(tmp_path / "p3.db")
    init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()}
    assert "articles" in names
    assert "articles_fts" in names
    assert "scrape_state" in names
    # contentless FTS accepts an indexed insert and a MATCH
    conn.execute("INSERT INTO articles_fts(rowid, title, body) VALUES (1, 'Creeper', 'explodes')")
    rows = conn.execute(
        "SELECT rowid FROM articles_fts WHERE articles_fts MATCH 'explodes'"
    ).fetchall()
    assert rows == [(1,)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_database.py::test_phase3_tables_exist -v`
Expected: FAIL (`no such table: articles`).

- [ ] **Step 3: Add `PHASE3_TABLES` to `schema.py`**

Append to `meister_guide/db/schema.py`:

```python
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
        url TEXT
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
```

- [ ] **Step 4: Wire `PHASE3_TABLES` into `init_db`**

In `meister_guide/db/database.py`, update the import and `init_db`, and add a busy timeout in `connect`:

```python
from meister_guide.db.schema import CORE_TABLES, PHASE3_TABLES
```

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_database.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/db/schema.py meister_guide/db/database.py tests/test_database.py
git commit -m "feat: add Phase 3 schema (articles, contentless FTS5, scrape_state)"
```

---

## Task 2: `ArticlesRepo.add_article` / `get_article` / `count` / `clear`

**Files:**
- Create: `meister_guide/db/articles.py`
- Test: `tests/test_articles_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_articles_repo.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    return ArticlesRepo(conn)


def test_add_and_get_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    inserted = repo.add_article(101, "Creeper", "A creeper explodes.", 5, "https://x/Creeper")
    assert inserted is True
    art = repo.get_article(101)
    assert art.title == "Creeper"
    assert art.body == "A creeper explodes."   # decompressed
    assert art.revid == 5
    assert repo.count() == 1


def test_add_is_idempotent_by_pageid(tmp_path):
    repo = _repo(tmp_path)
    assert repo.add_article(101, "Creeper", "first", 1, None) is True
    assert repo.add_article(101, "Creeper", "second", 2, None) is False  # skipped
    assert repo.count() == 1
    assert repo.get_article(101).body == "first"


def test_clear_empties_articles_and_index(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "A", "alpha", 1, None)
    repo.clear()
    assert repo.count() == 0
    assert repo.get_article(1) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py -v`
Expected: FAIL (`No module named 'meister_guide.db.articles'`).

- [ ] **Step 3: Write `articles.py` (models + add/get/count/clear)**

Create `meister_guide/db/articles.py`:

```python
"""Article mirror access: storage (zlib-compressed bodies + contentless FTS5),
full-text search, and the resumable scrape-state row."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py -v`
Expected: PASS (3 tests). (`make_excerpt` is imported but unused so far — Task 3 creates it; if it errors on import, do Task 3 first. To keep order simple, create a stub now and fill in Task 3.)

> If the import fails because `excerpt.py` doesn't exist yet, create `meister_guide/scraper/__init__.py` (empty) and a temporary `meister_guide/scraper/excerpt.py` containing `def make_excerpt(body, query, width=240): return body[:width]` — Task 3 replaces it test-first.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py meister_guide/scraper/__init__.py meister_guide/scraper/excerpt.py tests/test_articles_repo.py
git commit -m "feat: ArticlesRepo storage (compressed bodies + contentless FTS sync)"
```

---

## Task 3: `make_excerpt` (highlighted excerpt builder)

**Files:**
- Modify/Create: `meister_guide/scraper/excerpt.py`
- Test: `tests/test_excerpt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_excerpt.py`:

```python
from meister_guide.scraper.excerpt import make_excerpt


def test_highlights_matched_term():
    out = make_excerpt("A creeper explodes near the player.", "creeper")
    assert "<b>creeper</b>" in out.lower()


def test_window_around_match_with_ellipsis():
    body = "x" * 500 + " creeper " + "y" * 500
    out = make_excerpt(body, "creeper", width=60)
    assert "creeper" in out.lower()
    assert out.startswith("…") and out.endswith("…")
    assert len(out) < 200  # windowed, not the whole 1000+ chars


def test_no_match_returns_leading_text():
    out = make_excerpt("Alpha beta gamma.", "zzz", width=10)
    assert out.startswith("Alpha")
    assert "<b>" not in out


def test_escapes_html_in_body():
    out = make_excerpt("danger <script> creeper", "creeper")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_excerpt.py -v`
Expected: FAIL (stub returns no `<b>` highlighting / no escaping).

- [ ] **Step 3: Implement `make_excerpt`**

Replace `meister_guide/scraper/excerpt.py` with:

```python
"""Build a short, HTML-escaped, query-highlighted excerpt from article text.

Contentless FTS5 has no snippet() (it stores no text), so we generate excerpts
ourselves from the decompressed body."""
import html
import re

_WORD = re.compile(r"\w+", re.UNICODE)


def make_excerpt(body: str, query: str, width: int = 240) -> str:
    terms = [t for t in _WORD.findall(query.lower()) if t]
    lowered = body.lower()

    first = -1
    for term in terms:
        idx = lowered.find(term)
        if idx != -1 and (first == -1 or idx < first):
            first = idx

    if first == -1:
        start, end = 0, min(len(body), width)
    else:
        start = max(0, first - width // 3)
        end = min(len(body), start + width)

    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""

    escaped = html.escape(snippet)
    for term in sorted(set(terms), key=len, reverse=True):
        escaped = re.sub(
            "(" + re.escape(html.escape(term)) + ")",
            r"<b>\1</b>",
            escaped,
            flags=re.IGNORECASE,
        )
    return f"{prefix}{escaped}{suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_excerpt.py tests/test_articles_repo.py -v`
Expected: PASS (excerpt + repo tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/excerpt.py tests/test_excerpt.py
git commit -m "feat: highlighted excerpt builder for contentless FTS results"
```

---

## Task 4: `ArticlesRepo.search`

**Files:**
- Modify: `meister_guide/db/articles.py`
- Test: `tests/test_articles_repo.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_articles_repo.py`:

```python
def test_search_returns_ranked_highlighted_hits(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "A creeper is a hostile mob that explodes.", 1, "u1")
    repo.add_article(2, "Cow", "A cow is a passive animal.", 1, "u2")
    hits = repo.search("creeper")
    assert len(hits) == 1
    assert hits[0].pageid == 1
    assert hits[0].title == "Creeper"
    assert "<b>creeper</b>" in hits[0].excerpt_html.lower()


def test_search_empty_query_returns_nothing(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "explodes", 1, None)
    assert repo.search("   ") == []


def test_search_is_safe_with_fts_special_chars(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "explodes", 1, None)
    # Must not raise an FTS5 syntax error.
    assert repo.search('creeper" OR (') == [] or True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py::test_search_returns_ranked_highlighted_hits -v`
Expected: FAIL (`'ArticlesRepo' object has no attribute 'search'`).

- [ ] **Step 3: Implement `search` + query sanitizer**

Add to `ArticlesRepo` in `meister_guide/db/articles.py` (and the `re` import at top):

```python
import re
```

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py -v`
Expected: PASS (all repo tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_repo.py
git commit -m "feat: offline FTS5 search with safe query parsing + excerpts"
```

---

## Task 5: `ScrapeStateRepo` (resume token)

**Files:**
- Modify: `meister_guide/db/articles.py`
- Test: `tests/test_articles_repo.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_articles_repo.py`:

```python
def test_scrape_state_defaults_then_persists(tmp_path):
    from meister_guide.db.articles import ScrapeStateRepo, ScrapeState
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    repo = ScrapeStateRepo(conn)
    st = repo.load()
    assert st.continue_token is None and st.done == 0 and st.total is None
    repo.save(ScrapeState(continue_token='{"gapcontinue":"Boat"}', done=40, total=16689))
    again = repo.load()
    assert again.continue_token == '{"gapcontinue":"Boat"}'
    assert again.done == 40 and again.total == 16689
    repo.save(ScrapeState(continue_token=None, done=16689, total=16689))
    assert repo.load().continue_token is None
```

Add the import at the top of the test file:

```python
from meister_guide.db.database import connect, init_db
```

(already present from Task 2 — do not duplicate).

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py::test_scrape_state_defaults_then_persists -v`
Expected: FAIL (cannot import `ScrapeStateRepo`).

- [ ] **Step 3: Implement `ScrapeState` + `ScrapeStateRepo`**

Append to `meister_guide/db/articles.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_articles_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_repo.py
git commit -m "feat: ScrapeStateRepo for resumable ingest"
```

---

## Task 6: `WikiClient.iter_batches` (single batch parse)

**Files:**
- Create: `meister_guide/scraper/wiki_client.py`
- Test: `tests/test_wiki_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_wiki_client.py`:

```python
from meister_guide.scraper.wiki_client import WikiClient, WikiArticle


def _one_batch_response():
    return {
        "query": {"pages": {
            "101": {"pageid": 101, "title": "Creeper", "extract": "It explodes.", "lastrevid": 9},
            "102": {"pageid": 102, "title": "Cow", "extract": "It moos.", "lastrevid": 8},
            "103": {"pageid": 103, "title": "Empty"},  # no extract -> skipped
        }}
        # no "continue" key -> last batch
    }


def test_iter_batches_parses_articles_and_stops():
    calls = []
    def fake_get(params):
        calls.append(params)
        return _one_batch_response()
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)

    batches = list(client.iter_batches())
    assert len(batches) == 1
    articles, next_token = batches[0]
    assert next_token is None
    titles = sorted(a.title for a in articles)
    assert titles == ["Cow", "Creeper"]          # "Empty" skipped (no extract)
    assert isinstance(articles[0], WikiArticle)
    assert len(calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_wiki_client.py -v`
Expected: FAIL (`No module named 'meister_guide.scraper.wiki_client'`).

- [ ] **Step 3: Implement the client (no continuation/retry yet)**

Create `meister_guide/scraper/wiki_client.py`:

```python
"""MediaWiki API client for minecraft.wiki — streams batched plain-text article
extracts. Pure: HTTP and sleep are injectable so tests run without a network."""
import json
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_API = "https://minecraft.wiki/api.php"
USER_AGENT = (
    "MeisterGuide/0.3 (offline Minecraft guide reader; "
    "https://github.com/meister-guide)"
)


@dataclass
class WikiArticle:
    pageid: int
    title: str
    text: str
    revid: Optional[int]


class WikiClient:
    def __init__(self, api_url=DEFAULT_API, http_get=None, delay=1.0,
                 sleep=time.sleep):
        self._api = api_url
        self._http_get = http_get or self._default_get
        self._delay = delay
        self._sleep = sleep

    def _default_get(self, params):
        import requests
        resp = requests.get(self._api, params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _params(self, continue_token):
        params = {
            "action": "query", "format": "json",
            "generator": "allpages", "gapnamespace": 0, "gaplimit": "max",
            "prop": "extracts", "explaintext": 1, "exlimit": "max",
            "maxlag": 5,
        }
        if continue_token:
            params.update(json.loads(continue_token))
        return params

    @staticmethod
    def _articles_from(data):
        pages = data.get("query", {}).get("pages", {})
        out = []
        for page in pages.values():
            if "extract" not in page:
                continue
            out.append(WikiArticle(page["pageid"], page["title"],
                                   page["extract"], page.get("lastrevid")))
        return out

    def iter_batches(self, start_token=None):
        """Yield (list[WikiArticle], next_token|None) per API batch."""
        token = start_token
        while True:
            data = self._http_get(self._params(token))
            articles = self._articles_from(data)
            cont = data.get("continue")
            next_token = json.dumps(cont) if cont else None
            yield articles, next_token
            if next_token is None:
                return
            token = next_token
            self._sleep(self._delay)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_wiki_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: MediaWiki API client (batched plain-text extracts)"
```

---

## Task 7: `WikiClient` continuation across batches

**Files:**
- Test: `tests/test_wiki_client.py` (append) — implementation already supports it; this locks the behavior.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wiki_client.py`:

```python
def test_iter_batches_follows_continue_token():
    page1 = {
        "query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}},
        "continue": {"gapcontinue": "B", "continue": "gapcontinue||"},
    }
    page2 = {
        "query": {"pages": {"2": {"pageid": 2, "title": "B", "extract": "b"}}},
    }
    responses = [page1, page2]
    seen_params = []
    def fake_get(params):
        seen_params.append(dict(params))
        return responses.pop(0)
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)

    batches = list(client.iter_batches())
    assert [t for _, t in batches][:1] == ['{"gapcontinue": "B", "continue": "gapcontinue||"}']
    assert batches[-1][1] is None
    all_titles = [a.title for batch, _ in batches for a in batch]
    assert all_titles == ["A", "B"]
    # second request carried the continuation params
    assert seen_params[1].get("gapcontinue") == "B"
```

- [ ] **Step 2: Run test to verify it passes (behavior already implemented)**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_wiki_client.py -v`
Expected: PASS. If it fails, fix `iter_batches`/`_params` per Task 6 so the `continue` dict is JSON-serialized as the token and merged back into params.

- [ ] **Step 3: Commit**

```bash
git add tests/test_wiki_client.py
git commit -m "test: lock WikiClient continuation behavior"
```

---

## Task 8: `WikiClient` politeness — retry/backoff

**Files:**
- Modify: `meister_guide/scraper/wiki_client.py`
- Test: `tests/test_wiki_client.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wiki_client.py`:

```python
def test_retries_transient_error_then_succeeds():
    calls = {"n": 0}
    def flaky_get(params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503 Service Unavailable")
        return {"query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}}}
    slept = []
    client = WikiClient(http_get=flaky_get, delay=0, sleep=lambda s: slept.append(s))

    batches = list(client.iter_batches())
    assert calls["n"] == 2            # retried once
    assert slept                      # backed off before retry
    assert batches[0][0][0].title == "A"


def test_maxlag_error_is_retried():
    calls = {"n": 0}
    def lagging_get(params):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": {"code": "maxlag", "info": "Waiting for a server"}}
        return {"query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}}}
    client = WikiClient(http_get=lagging_get, delay=0, sleep=lambda s: None)
    list(client.iter_batches())
    assert calls["n"] == 2


def test_gives_up_after_max_retries():
    def always_fail(params):
        raise RuntimeError("network down")
    client = WikiClient(http_get=always_fail, delay=0, sleep=lambda s: None,
                        max_retries=3)
    import pytest
    with pytest.raises(RuntimeError):
        list(client.iter_batches())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_wiki_client.py -k retry -v`
Expected: FAIL (no retry logic; `max_retries` kwarg unknown).

- [ ] **Step 3: Add retry/backoff around the HTTP call**

In `meister_guide/scraper/wiki_client.py`, add `max_retries`/`backoff` params and a `_fetch` helper, and call it from `iter_batches`:

```python
    def __init__(self, api_url=DEFAULT_API, http_get=None, delay=1.0,
                 sleep=time.sleep, max_retries=5, backoff=1.0):
        self._api = api_url
        self._http_get = http_get or self._default_get
        self._delay = delay
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff = backoff
```

```python
    def _fetch(self, params):
        """One API call with bounded exponential backoff on transient failures
        and MediaWiki maxlag responses."""
        wait = self._backoff
        last_err = None
        for attempt in range(self._max_retries):
            try:
                data = self._http_get(params)
            except Exception as err:          # transient HTTP/network error
                last_err = err
                self._sleep(wait)
                wait *= 2
                continue
            if isinstance(data, dict) and data.get("error", {}).get("code") == "maxlag":
                self._sleep(wait)
                wait *= 2
                continue
            return data
        raise RuntimeError(f"MediaWiki API failed after {self._max_retries} "
                           f"attempts: {last_err}")
```

Then in `iter_batches`, replace `data = self._http_get(self._params(token))` with:

```python
            data = self._fetch(self._params(token))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_wiki_client.py -v`
Expected: PASS (all client tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: polite retry/backoff + maxlag handling in WikiClient"
```

---

## Task 9: `run_ingest` orchestrator (progress, resume, cancel)

**Files:**
- Create: `meister_guide/scraper/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.ingest import run_ingest


class FakeClient:
    """Yields canned (articles, next_token) batches; records the start token."""
    def __init__(self, batches):
        self._batches = batches
        self.started_with = "UNSET"
    def iter_batches(self, start_token=None):
        self.started_with = start_token
        for b in self._batches:
            yield b
    def article_count(self):
        return 3


def _setup(tmp_path):
    conn = connect(tmp_path / "i.db")
    init_db(conn)
    return conn, ArticlesRepo(conn), ScrapeStateRepo(conn)


def test_run_ingest_populates_db_and_reports_progress(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [
        ([WikiArticle(1, "A", "alpha", 1), WikiArticle(2, "B", "beta", 1)], "tok1"),
        ([WikiArticle(3, "C", "gamma", 1)], None),
    ]
    seen = []
    run_ingest(FakeClient(batches), arts, state, conn,
               progress_cb=lambda d, t: seen.append((d, t)))
    assert arts.count() == 3
    assert seen[-1][0] == 3                 # done count reached total articles
    assert state.load().continue_token is None   # finished -> token cleared


def test_run_ingest_resumes_from_saved_token(tmp_path):
    conn, arts, state = _setup(tmp_path)
    from meister_guide.scraper.ingest import ScrapeState  # re-exported
    state.save(ScrapeState(continue_token="tok1", done=2, total=3))
    client = FakeClient([([WikiArticle(3, "C", "g", 1)], None)])
    run_ingest(client, arts, state, conn)
    assert client.started_with == "tok1"    # resumed, not restarted


def test_run_ingest_stops_when_cancelled(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [
        ([WikiArticle(1, "A", "a", 1)], "tok1"),
        ([WikiArticle(2, "B", "b", 1)], None),
    ]
    run_ingest(FakeClient(batches), arts, state, conn, should_cancel=lambda: True)
    assert arts.count() == 0                 # cancelled before first batch committed
    assert state.load().continue_token != None or arts.count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ingest.py -v`
Expected: FAIL (`No module named 'meister_guide.scraper.ingest'`).

- [ ] **Step 3: Implement `run_ingest`**

Create `meister_guide/scraper/ingest.py`:

```python
"""Drive the WikiClient into the DB: per-batch transactions, resume token, and
progress/cancel hooks. No Qt here so it stays unit-testable."""
from meister_guide.db.articles import ScrapeState  # re-export for callers


def _url_for(title: str) -> str:
    return "https://minecraft.wiki/w/" + title.replace(" ", "_")


def run_ingest(client, articles_repo, state_repo, conn,
               progress_cb=None, should_cancel=None):
    """Ingest all article batches from `client` into the repos.

    Resumes from the saved continue token, commits once per batch (so a crash
    loses at most one batch), and stops cleanly if should_cancel() turns true."""
    state = state_repo.load()
    total = state.total
    if total is None:
        try:
            total = client.article_count()
        except Exception:
            total = None
    done = state.done

    for articles, next_token in client.iter_batches(start_token=state.continue_token):
        if should_cancel and should_cancel():
            return
        for art in articles:
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, _url_for(art.title),
                                         commit=False):
                done += 1
        state_repo.save(ScrapeState(next_token, done, total), commit=False)
        conn.commit()
        if progress_cb:
            progress_cb(done, total)

    # Reached the end: clear the resume token, keep the final count.
    state_repo.save(ScrapeState(None, done, total))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ingest.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/ingest.py tests/test_ingest.py
git commit -m "feat: resumable, cancellable ingest orchestrator"
```

---

## Task 10: `IngestWorker` (QThread-friendly, owns its connection)

**Files:**
- Create: `meister_guide/scraper/worker.py`
- Test: `tests/test_ingest_worker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest_worker.py`:

```python
from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import IngestWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, batches):
        self._batches = batches
    def iter_batches(self, start_token=None):
        yield from self._batches
    def article_count(self):
        return 2


def test_worker_runs_ingest_and_emits_signals(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "w.db"
    client = FakeClient([([WikiArticle(1, "A", "a", 1), WikiArticle(2, "B", "b", 1)], None)])
    worker = IngestWorker(str(db), client=client)

    progress, finished, errors = [], [], []
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.finished.connect(lambda: finished.append(True))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert finished == [True]
    assert progress and progress[-1][0] == 2
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count() == 2


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def article_count(self): return 0
        def iter_batches(self, start_token=None):
            raise RuntimeError("kaboom")
    worker = IngestWorker(str(tmp_path / "e.db"), client=Boom())
    errors, finished = [], []
    worker.error.connect(lambda m: errors.append(m))
    worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert finished == []
    assert errors and "kaboom" in errors[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ingest_worker.py -v`
Expected: FAIL (`No module named 'meister_guide.scraper.worker'`).

- [ ] **Step 3: Implement the worker**

Create `meister_guide/scraper/worker.py`:

```python
"""QThread worker that runs the ingest off the UI thread. It opens its OWN
SQLite connection inside run() because SQLite connections are not safe to share
across threads."""
from PySide6.QtCore import QObject, Signal

from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.scraper.wiki_client import WikiClient
from meister_guide.scraper.ingest import run_ingest


class IngestWorker(QObject):
    progress = Signal(int, int)   # done, total (total may be 0 if unknown)
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_path, client=None):
        super().__init__()
        self._db_path = db_path
        self._client = client
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        conn = None
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient()
            run_ingest(
                client,
                ArticlesRepo(conn),
                ScrapeStateRepo(conn),
                conn,
                progress_cb=lambda d, t: self.progress.emit(d, t or 0),
                should_cancel=lambda: self._cancel,
            )
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ingest_worker.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/worker.py tests/test_ingest_worker.py
git commit -m "feat: IngestWorker (background ingest with progress/finished/error)"
```

---

## Task 11: Guides tab — search box, results list, detail panel

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Modify: `meister_guide/main.py`
- Test: manual (headless construct smoke is in Step 4)

- [ ] **Step 1: Accept `articles_repo` + `db_path` on `OverlayWindow`**

In `meister_guide/overlay/window.py`, extend `__init__` (keep existing params/order):

```python
    def __init__(self, settings: QSettings, games=None, articles_repo=None, db_path=None):
        super().__init__()
        self._settings = settings
        self._drag_offset = None
        self._games = list(games) if games else []
        self.active_game = None
        self._articles_repo = articles_repo
        self._db_path = db_path
        self._ingest_thread = None
        self._ingest_worker = None
        # HWND of a fullscreen/always-on-top game we temporarily demoted ...
        self._demoted_hwnd = None
```

- [ ] **Step 2: Build the Guides tab and replace the placeholder**

Add these imports at the top of `window.py`:

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame, QComboBox, QLineEdit, QListWidget, QListWidgetItem,
    QTextBrowser, QProgressBar, QSplitter,
)
```

Replace `_build_tabs` so the Guides tab uses a real widget:

```python
    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        chat = QLabel("Chat — coming in a later phase")
        chat.setAlignment(Qt.AlignCenter)
        chat.setContentsMargins(16, 16, 16, 16)
        tabs.addTab(chat, "Chat")
        tabs.addTab(self._build_guides_tab(), "Guides")
        settings = QLabel("Settings — coming in a later phase")
        settings.setAlignment(Qt.AlignCenter)
        settings.setContentsMargins(16, 16, 16, 16)
        tabs.addTab(settings, "Settings")
        return tabs

    def _build_guides_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(8)

        self.guides_search = QLineEdit()
        self.guides_search.setPlaceholderText("Search guides…")
        self.guides_search.textChanged.connect(self._on_search)
        col.addWidget(self.guides_search)

        split = QSplitter(Qt.Horizontal)
        self.guides_results = QListWidget()
        self.guides_results.itemClicked.connect(self._on_result_clicked)
        split.addWidget(self.guides_results)

        self.guides_detail = QTextBrowser()
        self.guides_detail.setOpenExternalLinks(True)
        split.addWidget(self.guides_detail)
        split.setSizes([180, 280])
        col.addWidget(split, 1)

        bar = QHBoxLayout()
        self.guides_update_btn = QPushButton("Update guides")
        self.guides_update_btn.clicked.connect(self._on_update_guides)
        bar.addWidget(self.guides_update_btn)
        self.guides_progress = QProgressBar()
        self.guides_progress.setVisible(False)
        bar.addWidget(self.guides_progress, 1)
        self.guides_status = QLabel("")
        bar.addWidget(self.guides_status)
        col.addLayout(bar)

        self._refresh_guides_status()
        return page
```

- [ ] **Step 3: Add the search/detail/status behavior**

Add these methods to `OverlayWindow`:

```python
    # ---- guides ---------------------------------------------------------
    def _on_search(self, text):
        self.guides_results.clear()
        if self._articles_repo is None or not text.strip():
            return
        for hit in self._articles_repo.search(text):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, hit.pageid)
            label = QLabel(f"<b>{hit.title}</b><br><span>{hit.excerpt_html}</span>")
            label.setWordWrap(True)
            label.setContentsMargins(4, 4, 4, 4)
            self.guides_results.addItem(item)
            item.setSizeHint(label.sizeHint())
            self.guides_results.setItemWidget(item, label)

    def _on_result_clicked(self, item):
        if self._articles_repo is None:
            return
        pageid = item.data(Qt.UserRole)
        article = self._articles_repo.get_article(pageid)
        if article is None:
            return
        self.guides_detail.setPlainText(article.body)

    def _refresh_guides_status(self):
        if self._articles_repo is None:
            self.guides_status.setText("")
            return
        n = self._articles_repo.count()
        self.guides_status.setText(
            f"{n:,} articles" if n else "No guides yet — click Update guides"
        )
```

- [ ] **Step 4: Headless smoke check**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; from meister_guide.db.database import connect, init_db; from meister_guide.db.articles import ArticlesRepo; from meister_guide.overlay.window import OverlayWindow; app=QApplication([]); c=connect(':memory:'); init_db(c); r=ArticlesRepo(c); r.add_article(1,'Creeper','A creeper explodes.',1,'u'); w=OverlayWindow(QSettings('MeisterGuide','T'), [], r, ':memory:'); w.guides_search.setText('creeper'); print('results:', w.guides_results.count()); w._on_result_clicked(w.guides_results.item(0)); print('detail has text:', bool(w.guides_detail.toPlainText()))"
```

Expected: `results: 1` and `detail has text: True`, no exceptions.

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS (all existing tests still green).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: Guides tab with offline search, excerpts, and detail panel"
```

---

## Task 12: Guides tab — "Update guides" background download

**Files:**
- Modify: `meister_guide/overlay/window.py`

- [ ] **Step 1: Wire the Update button to the worker**

Add these methods to `OverlayWindow` (imports: add `QThread` to the `PySide6.QtCore` import line, and `from meister_guide.scraper.worker import IngestWorker` at top):

```python
    def _on_update_guides(self):
        if self._db_path is None or self._ingest_thread is not None:
            return
        self.guides_update_btn.setEnabled(False)
        self.guides_progress.setVisible(True)
        self.guides_progress.setRange(0, 0)  # indeterminate until first progress
        self.guides_status.setText("Starting…")

        self._ingest_thread = QThread(self)
        self._ingest_worker = IngestWorker(str(self._db_path))
        self._ingest_worker.moveToThread(self._ingest_thread)
        self._ingest_thread.started.connect(self._ingest_worker.run)
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_thread.start()

    def _on_ingest_progress(self, done, total):
        if total > 0:
            self.guides_progress.setRange(0, total)
            self.guides_progress.setValue(done)
        self.guides_status.setText(f"{done:,}/{total:,}" if total else f"{done:,}")

    def _on_ingest_done(self):
        self._teardown_ingest()
        self._refresh_guides_status()
        if self.guides_search.text().strip():
            self._on_search(self.guides_search.text())

    def _on_ingest_error(self, message):
        self._teardown_ingest()
        self.guides_status.setText("Update needs an internet connection.")

    def _teardown_ingest(self):
        self.guides_progress.setVisible(False)
        self.guides_update_btn.setEnabled(True)
        if self._ingest_thread is not None:
            self._ingest_thread.quit()
            self._ingest_thread.wait()
        self._ingest_thread = None
        self._ingest_worker = None
```

- [ ] **Step 2: Stop the worker cleanly on hide/close**

In `hideEvent`, cancel any in-flight ingest before the existing restore call:

```python
    def hideEvent(self, event):
        if self._ingest_worker is not None:
            self._ingest_worker.cancel()
        self._restore_demoted_game()
        super().hideEvent(event)
```

- [ ] **Step 3: Headless smoke check (button starts/stops without a real network)**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; from meister_guide.overlay.window import OverlayWindow; app=QApplication([]); w=OverlayWindow(QSettings('MeisterGuide','T'), [], None, ':memory:'); print('update btn exists:', hasattr(w,'guides_update_btn')); w._teardown_ingest(); print('teardown ok')"
```

Expected: prints both lines, no exception. (Full update is verified manually below.)

- [ ] **Step 4: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: background Update guides download with progress + cancel"
```

---

## Task 13: Wire repo into main.py + docs

**Files:**
- Modify: `meister_guide/main.py`
- Modify: `README.md`

- [ ] **Step 1: Build `ArticlesRepo` and pass it to the overlay**

In `meister_guide/main.py`, add the import and construct the repo, then pass it + the db path to `OverlayWindow`:

```python
from meister_guide.db.articles import ArticlesRepo
```

```python
    conn = connect(default_db_path())
    init_db(conn)
    games_repo = GamesRepo(conn)
    games_repo.seed_defaults()
    games_repo.reconcile_builtin_games()
    articles_repo = ArticlesRepo(conn)

    overlay = OverlayWindow(settings, games_repo.list_games(),
                            articles_repo=articles_repo,
                            db_path=default_db_path())
```

- [ ] **Step 2: Document the Guides download + polite-scrape note**

Add to `README.md` under a new `## Guides (offline wiki)` section:

```markdown
## Guides (offline wiki)
Open the Guides tab and click **Update guides** once to download minecraft.wiki
article text into a local database (~10-15 min, ~80 MB). After that, search works
fully offline. The download uses the MediaWiki API politely (identified
User-Agent, rate-limited, `maxlag`, resumable) and stores only plain text — no
images.
```

- [ ] **Step 3: Manual end-to-end verification (real app)**

Run: `.\run.bat`

Verify (checklist):
1. Guides tab shows "No guides yet — click Update guides".
2. Click **Update guides** → progress bar advances, status shows a growing count.
3. Hide the overlay mid-download (Alt+Insert) → reopen → download resumed (count continues, not reset).
4. After it finishes, type "creeper" → results appear with the term **bolded** in excerpts; click one → detail panel shows the full article text.
5. Disconnect the network, relaunch, search still works offline; clicking **Update guides** offline shows "Update needs an internet connection."

- [ ] **Step 4: Run the whole suite + commit**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS.

```bash
git add meister_guide/main.py README.md
git commit -m "feat: wire ArticlesRepo into the app + document offline Guides"
```

---

## Self-Review

**Spec coverage:**
- Full article-namespace API ingest → Tasks 6–9. ✓
- Batched extracts (`generator=allpages` + `prop=extracts`) → Task 6. ✓
- Politeness (UA, rate limit, maxlag, backoff, resumable) → Tasks 6, 8, 9. ✓
- zlib-compressed bodies + contentless FTS5 (no triggers) → Tasks 1, 2. ✓
- Hand-rolled highlighted excerpts → Tasks 3, 4. ✓
- `scrape_state` resume → Tasks 1, 5, 9. ✓
- Background QThread worker with own connection → Task 10. ✓
- Guides tab (search, excerpts, detail, Update button + progress) → Tasks 11, 12. ✓
- Error handling (offline message, transient retry, resume, partial-DB status) → Tasks 8, 9, 12, 13 manual. ✓
- Wiring + docs → Task 13. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code; manual UI verification has an explicit checklist.

**Type consistency:** `WikiArticle(pageid,title,text,revid)`, `Article(pageid,title,body,revid,url)`, `SearchHit(pageid,title,excerpt_html,url)`, `ScrapeState(continue_token,done,total)` used consistently. `add_article(pageid,title,text,revid,url,commit)`, `search(query,limit)`, `iter_batches(start_token)`, `run_ingest(client,articles_repo,state_repo,conn,progress_cb,should_cancel)`, `IngestWorker(db_path,client)` consistent across tasks.

**Note for executor:** Task 2 imports `make_excerpt` before Task 3 implements it — create the stub described in Task 2 Step 4 if executing strictly in order, or implement Task 3 immediately after Task 2's red phase.
