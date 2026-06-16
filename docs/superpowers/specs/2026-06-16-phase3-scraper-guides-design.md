# Design — Phase 3: Wiki Ingest + Offline Guides

**Date:** 2026-06-16
**Status:** Approved (design), ready to plan
**Builds on:** Phase 2 SQLite layer (`db/`), the overlay shell, and the games/detector wiring.

## Goal

Mirror minecraft.wiki article text into local SQLite, fully searchable offline,
and surface it through a Guides tab: search box, highlighted result excerpts, and
a readable detail panel. A one-time background "Update guides" download makes the
app fully offline thereafter.

## Locked decisions (from brainstorming)

- **Source:** the full article namespace — all ~16,689 content articles
  (namespace 0 only; talk/user/file/template excluded).
- **Method:** the **MediaWiki API**, not HTML scraping. Batched via
  `generator=allpages` + `prop=extracts&explaintext=1&exlimit=max` (~20 articles
  per request, ~835 requests total). Verified live: `extracts` returns clean
  plain text on minecraft.wiki.
- **Politeness:** honest `User-Agent` identifying Meister Guide; serial requests
  with a small delay; `maxlag` parameter; exponential backoff on 429/503. Note:
  `robots.txt` disallows `action=` for generic crawlers — we proceed as a
  low-rate, clearly-identified, run-once-per-user offline-mirror client. This is
  a conscious project-owner decision, documented here and in the README.
- **Size:** **zlib-compress each article body** (~50 MB plain text → ~20 MB).
  Total DB ≈ ~80 MB including the FTS index.
- **Images:** none (text-only) for the beta.
- **Trigger:** a manual "Update guides" button, not auto-ingest on launch
  (~10–15 min first run). Existing data stays searchable offline meanwhile.

## Realistic envelope

~835 requests, ~10–15 min one-time download, ~80 MB DB. (The earlier
"hours / multiple GB" fear was tied to the rejected HTML-scrape + image storage.)

## Components

Each unit has one job, a clear interface, and is testable in isolation.

### 1. `meister_guide/scraper/wiki_client.py` — MediaWiki API client (pure, no Qt)
- `iter_articles(http_get=...) -> Iterator[Article]` where `Article` is
  `(pageid, title, text, revid)`.
- Builds `action=query&generator=allpages&gapnamespace=0&gaplimit=max
  &prop=extracts|info&explaintext=1&exlimit=max&inprop=` requests; follows the
  `continue` token until exhausted.
- Injectable `http_get` (defaults to a `requests.Session` with the project
  `User-Agent`) so tests feed canned JSON — **no network in tests**.
- Politeness: configurable inter-request delay, `maxlag=5`, retry with backoff on
  429/503/network errors (bounded retries, then raise).

### 2. `meister_guide/db/schema.py` — add article tables
- `articles(id INTEGER PRIMARY KEY, pageid INTEGER UNIQUE, title TEXT NOT NULL,
  body_zlib BLOB NOT NULL, revid INTEGER, url TEXT)`.
- `articles_fts` — `CREATE VIRTUAL TABLE articles_fts USING fts5(title, body,
  content='')` (**contentless**: indexes tokens, stores no text — keeps the DB
  small and pairs with the compressed body).
- `scrape_state(id INTEGER PRIMARY KEY CHECK (id=1), continue_token TEXT,
  done INTEGER, total INTEGER, updated_at TEXT)` — single-row ingest progress for
  resumability.
- No FTS triggers: the stored body is compressed, so triggers can't derive the
  index text. `ArticlesRepo` keeps `articles` and `articles_fts` in sync inside
  one transaction instead. (Deviation from the original Phase-3 note, which
  assumed triggers; documented here because the body is compressed.)

### 3. `meister_guide/db/articles.py` — `ArticlesRepo`
- `add_article(pageid, title, text, revid, url, commit=True) -> bool`:
  - `INSERT OR IGNORE` into `articles` storing `zlib.compress(text.encode())`;
    returns `False` (skip) if the `pageid` is already stored, `True` on insert.
  - on insert, also add `(rowid=articles.id, title, body=text)` to `articles_fts`,
    in the same transaction.
  - **Add-if-absent, not update-in-place.** A re-run/resume therefore fills gaps
    and never duplicates, so it is safely idempotent — but it does **not refresh**
    an article whose wiki content changed upstream. That matches the beta scope:
    "Update guides" completes/resumes the one-time mirror; incremental
    "what-changed" refresh is out of scope (see below). A full content refresh is
    `clear()` followed by a fresh ingest.
  - (This replaces an earlier `upsert_article`/`ON CONFLICT DO UPDATE` sketch: an
    update path would need the FTS5 `'delete'` command with the old row's
    decompressed text, which is needless complexity for a one-time mirror.)
- `get_article(pageid) -> Article | None`, `count() -> int`, `clear()`
  (empties `articles` + the contentless index via `'delete-all'`; the primitive
  a future full-refresh/rebuild would call).
- `search(query, limit=50) -> list[SearchHit]`:
  - `SELECT rowid, bm25(articles_fts) FROM articles_fts WHERE articles_fts
    MATCH ? ORDER BY rank LIMIT ?`.
  - fetch matching `articles` rows, decompress bodies, build a
    `SearchHit(pageid, title, excerpt_html, ...)`.
- `get_article(pageid) -> Article|None`: decompress and return full text for the
  detail panel.
- `count()` for status display.

### 4. `meister_guide/scraper/excerpt.py` — excerpt builder (pure)
- `make_excerpt(body, query_terms, width=240) -> str`: find the first term hit
  (case-insensitive), take a window around it, HTML-escape, wrap matched terms in
  `<b>…</b>`. Replaces FTS5's `snippet()`, which contentless tables don't provide.
- Pure string logic → straightforward unit tests.

### 5. `meister_guide/scraper/worker.py` — QThread ingest worker
- `IngestWorker(QObject)` moved to a `QThread`; signals
  `progress(done:int, total:int)`, `finished()`, `error(str)`.
- Drives `wiki_client.iter_articles` → `ArticlesRepo.upsert_article`, updating
  `scrape_state` periodically (every N pages) so a crash/quit resumes from the
  last `continue` token.
- Cancellable via a flag checked between batches.

### 6. Guides tab UI (`overlay/window.py`)
- Replace the placeholder Guides tab with: a search `QLineEdit`, a results list
  (`QListWidget`/custom rows showing title + `excerpt_html`), and a detail panel
  (`QTextBrowser`) showing the selected article's full text.
- A footer/toolbar row in the tab: **"Update guides"** button, a `QProgressBar`,
  and a status label ("12,340 / 16,689" or "16,689 articles, updated <date>").
- Search runs on the existing connection (offline). Update kicks off the worker;
  progress signals drive the bar; on finish, refresh the count + re-run any
  active search.

## Data flow

```
Update guides clicked
  -> IngestWorker (thread) -> wiki_client.iter_articles (API, batched, polite)
     -> ArticlesRepo.upsert_article (compress body; sync FTS) [txn]
     -> scrape_state updated every N pages (resumable)
  -> progress(done,total) -> progress bar ; finished() -> refresh count

Search typed
  -> ArticlesRepo.search(query) -> FTS5 MATCH (rank) -> rowids
     -> decompress hit bodies -> excerpt.make_excerpt -> results list
  -> click result -> get_article(pageid) -> decompress -> detail panel
```

## Error handling
- **Offline / network error during update:** worker emits `error`; UI shows
  "Updating guides needs an internet connection." Existing offline data and
  search remain fully usable.
- **Transient API errors (429/503/timeouts):** bounded exponential backoff +
  `maxlag`; exceeding retries surfaces a clear error and leaves `scrape_state`
  intact so a retry resumes.
- **Interrupted ingest (quit/crash):** `scrape_state.continue_token` lets the
  next run resume; upserts are idempotent so no duplicates.
- **Empty/partial DB:** search simply returns no/fewer results; the status label
  reflects the count so the user knows an update is needed.
- **Corrupt/over-long extract:** stored as-is (compressed); excerpt builder is
  defensive about short bodies and missing terms.

## Testing
- `wiki_client`: canned multi-batch JSON (continuation across ≥2 pages, extract
  parsing, a 429-then-success retry) via injected `http_get` — no network.
- `excerpt`: term at start/middle/end, multiple terms, no match, HTML-escaping,
  width clamping.
- `ArticlesRepo` (in-memory SQLite): upsert → `search` returns the right hit with
  a highlighted excerpt and sane ranking; re-upsert is idempotent; round-trip
  compression in `get_article`.
- `schema`: tables/virtual table create cleanly; `scrape_state` single-row guard.
- `worker`: with a fake client + temp DB, progress is emitted, DB is populated,
  resume token advances, cancel stops between batches. (Qt signal test, headless.)
- UI search/detail/progress: verified manually via `run.bat` against a small live
  ingest.

## Out of scope (later phases)
- Image mirroring; incremental "what changed since last update" sync (beta does a
  full resumable pass).
- Prebuilt downloadable DB asset (needs hosting/release infra — revisit post-beta).
- AI/RAG over the articles — Phase 4 consumes this FTS index.
