# Web-search Fallback (SP2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the active game's wiki can't answer a chat question (or the game has no wiki), search the web via the Brave API, scrape the top results, ingest them scoped to the game, and answer through the existing RAG path.

**Architecture:** A last-resort fallback layered onto the existing SP2a miss path. New pure units mirror the SP2a stack: a Brave search client, an HTML main-text extractor, and a pure `run_web_fetch` orchestrator, wrapped by a `WebFetchWorker`. `window._on_send` becomes a chain (local hits → wiki fetch → web fetch → answer). Web pages are stored in `articles` with a synthetic URL-hash `pageid`. Gated by a Brave key + an "Allow web search fallback" checkbox (default on when a key is set).

**Tech Stack:** Python, PySide6 (Qt), SQLite + FTS5, Brave Search REST API, `trafilatura` (HTML extraction), `requests`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-web-fallback-design.md`

**Test runner:** `py -m pytest -q` (use `py`, not `python` — the `python`/`python3` aliases are broken Windows Store stubs).

---

## File Structure

- **Modify** `meister_guide/scraper/urls.py` — add `web_pageid(url)`.
- **Modify** `meister_guide/db/settings.py` — defaults + `brave_api_key()` / `web_fallback_enabled()`.
- **Create** `meister_guide/scraper/web_search.py` — `BraveSearchClient`.
- **Create** `meister_guide/scraper/web_fetch.py` — `fetch_main_text`.
- **Create** `meister_guide/scraper/web_ingest.py` — pure `run_web_fetch`.
- **Modify** `meister_guide/scraper/worker.py` — `WebFetchWorker`.
- **Modify** `meister_guide/overlay/window.py` — fallback chaining, Settings UI, lifecycle.
- **Modify** `requirements.txt` — add `trafilatura`.
- **Create** tests: `tests/test_web_pageid.py`, `tests/test_settings_web.py`, `tests/test_web_search.py`, `tests/test_web_fetch.py`, `tests/test_web_ingest.py`, `tests/test_web_worker.py`, `tests/test_window_web.py`.

---

## Task 1: `web_pageid` synthetic id

**Files:**
- Modify: `meister_guide/scraper/urls.py`
- Test: `tests/test_web_pageid.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_pageid.py`:

```python
from meister_guide.scraper.urls import web_pageid


def test_stable_for_same_url():
    assert web_pageid("https://example.com/a") == web_pageid("https://example.com/a")


def test_distinct_for_different_urls():
    assert web_pageid("https://example.com/a") != web_pageid("https://example.com/b")


def test_positive_and_above_wiki_range():
    # wiki pageids are small (< 1e8); synthetic ids must never collide with them
    pid = web_pageid("https://example.com/page")
    assert pid > 100_000_000
    assert pid > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_pageid.py -q`
Expected: FAIL with `ImportError: cannot import name 'web_pageid'`.

- [ ] **Step 3: Implement**

In `meister_guide/scraper/urls.py`, append:

```python
def web_pageid(url):
    """Stable positive int id for a scraped web page. articles.pageid is
    UNIQUE NOT NULL INTEGER and wiki pageids are small (< 1e8), so a ~60-bit
    truncated SHA-1 of the URL never collides with a real wiki pageid and keeps
    ingestion idempotent (re-fetching the same URL is a no-op)."""
    import hashlib
    return int(hashlib.sha1(url.encode("utf-8")).hexdigest()[:15], 16)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_pageid.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/urls.py tests/test_web_pageid.py
git commit -m "feat: web_pageid synthetic id for scraped web pages"
```

---

## Task 2: SettingsRepo Brave key + web-fallback gate

**Files:**
- Modify: `meister_guide/db/settings.py`
- Test: `tests/test_settings_web.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_web.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    return SettingsRepo(conn)


def test_brave_api_key_defaults_empty(tmp_path):
    assert _repo(tmp_path).brave_api_key() == ""


def test_web_fallback_disabled_without_key(tmp_path):
    repo = _repo(tmp_path)
    assert repo.web_fallback_enabled() is False


def test_web_fallback_enabled_when_key_set(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    assert repo.web_fallback_enabled() is True   # defaults on once a key exists


def test_web_fallback_can_be_paused_with_key_set(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    repo.set("web_fallback", "0")
    assert repo.web_fallback_enabled() is False


def test_web_fallback_off_pref_without_key_still_false(tmp_path):
    repo = _repo(tmp_path)
    repo.set("web_fallback", "1")     # pref on but no key
    assert repo.web_fallback_enabled() is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_settings_web.py -q`
Expected: FAIL with `AttributeError: 'SettingsRepo' object has no attribute 'brave_api_key'`.

- [ ] **Step 3: Implement**

In `meister_guide/db/settings.py`, add two entries to the `_DEFAULTS` dict (after `"claude_model"`):

```python
    "brave_api_key": "",
    "web_fallback": "1",
```

Then add two accessors to `SettingsRepo` (after `claude_model`):

```python
    def brave_api_key(self):
        return self.get("brave_api_key")

    def web_fallback_enabled(self):
        """Web fallback is on when a Brave key is set and the pref isn't paused.
        Defaults on once a key exists; the Settings checkbox writes '1'/'0'."""
        return bool(self.brave_api_key()) and self.get("web_fallback") != "0"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_settings_web.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/settings.py tests/test_settings_web.py
git commit -m "feat: SettingsRepo brave_api_key + web_fallback_enabled gate"
```

---

## Task 3: BraveSearchClient

**Files:**
- Create: `meister_guide/scraper/web_search.py`
- Test: `tests/test_web_search.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_search.py`:

```python
from meister_guide.scraper.web_search import BraveSearchClient


def test_sends_token_header_and_query_params():
    seen = {}
    def fake_get(url, headers, params):
        seen["url"] = url
        seen["headers"] = headers
        seen["params"] = params
        return {"web": {"results": [
            {"title": "Tame a wolf", "url": "https://x/wolf"},
        ]}}
    client = BraveSearchClient("brv-123", http_get=fake_get)
    client.search("how to tame a wolf", count=3)
    assert seen["headers"]["X-Subscription-Token"] == "brv-123"
    assert seen["params"]["q"] == "how to tame a wolf"
    assert seen["params"]["count"] == 3
    assert "api.search.brave.com" in seen["url"]


def test_parses_title_url_pairs():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": "A", "url": "https://x/a"},
            {"title": "B", "url": "https://x/b"},
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert client.search("q") == [("A", "https://x/a"), ("B", "https://x/b")]


def test_respects_count_limit():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": f"T{i}", "url": f"https://x/{i}"} for i in range(10)
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert len(client.search("q", count=2)) == 2


def test_skips_results_without_url_and_falls_back_title_to_url():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": "no url here"},                 # dropped (no url)
            {"url": "https://x/c"},                    # title falls back to url
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert client.search("q") == [("https://x/c", "https://x/c")]


def test_empty_when_no_results():
    client = BraveSearchClient("k", http_get=lambda u, h, p: {"web": {"results": []}})
    assert client.search("zzz") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_search.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.scraper.web_search'`.

- [ ] **Step 3: Implement**

Create `meister_guide/scraper/web_search.py`:

```python
"""Brave Search API client. Pure: the HTTP call is injectable so tests run
without a network or a real key. Returns (title, url) pairs for the web-fetch
orchestrator to scrape."""

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "MeisterGuide/0.4 (game guide reader; https://github.com/meister-guide)"


class BraveSearchClient:
    def __init__(self, api_key, http_get=None):
        self._api_key = api_key
        self._http_get = http_get or self._default_get

    def _default_get(self, url, headers, params):
        import requests
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search(self, query, count=3):
        """Return up to `count` (title, url) pairs for `query`. Raises on a
        network/API error (the worker catches it)."""
        data = self._http_get(
            ENDPOINT,
            {"X-Subscription-Token": self._api_key,
             "Accept": "application/json",
             "User-Agent": USER_AGENT},
            {"q": query, "count": count},
        )
        results = data.get("web", {}).get("results", [])
        out = []
        for r in results[:count]:
            url = r.get("url")
            if url:
                out.append((r.get("title") or url, url))
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_search.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/web_search.py tests/test_web_search.py
git commit -m "feat: BraveSearchClient (keyed web search, injectable http)"
```

---

## Task 4: fetch_main_text (HTML extraction) + trafilatura dependency

**Files:**
- Create: `meister_guide/scraper/web_fetch.py`
- Modify: `requirements.txt`
- Test: `tests/test_web_fetch.py`

The default extractor lazy-imports `trafilatura` (like the codebase lazy-imports `anthropic`). The extractor is injectable so tests need no dependency and no network.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_fetch.py`:

```python
from meister_guide.scraper.web_fetch import fetch_main_text


def test_returns_title_and_text_from_extractor():
    def fake_get(url):
        return "<html>...</html>"
    def fake_extract(html):
        return ("Tame a Wolf", "Give a wolf a bone to tame it.")
    title, text = fetch_main_text("https://x/wolf", http_get=fake_get,
                                  extract=fake_extract)
    assert title == "Tame a Wolf"
    assert "bone" in text


def test_title_falls_back_to_host_when_extractor_gives_none():
    def fake_extract(html):
        return ("", "some body text")
    title, text = fetch_main_text("https://wiki.example.com/page",
                                  http_get=lambda u: "<html></html>",
                                  extract=fake_extract)
    assert title == "wiki.example.com"
    assert text == "some body text"


def test_empty_text_returned_without_raising():
    def fake_extract(html):
        return ("", "")
    title, text = fetch_main_text("https://x/empty",
                                  http_get=lambda u: "<html></html>",
                                  extract=fake_extract)
    assert text == ""        # caller decides to skip; no exception
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_fetch.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.scraper.web_fetch'`.

- [ ] **Step 3: Implement**

Create `meister_guide/scraper/web_fetch.py`:

```python
"""Download a web page and extract its main article text. Pure: both the HTTP
GET and the HTML->(title, text) extractor are injectable so tests run without a
network or the trafilatura dependency. The real default extractor lazy-imports
trafilatura (mirrors the anthropic lazy-import pattern)."""
from urllib.parse import urlparse

USER_AGENT = "MeisterGuide/0.4 (game guide reader; https://github.com/meister-guide)"


def _default_get(url):
    import requests
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _default_extract(html):
    """(title, text) via trafilatura. Returns empty strings when nothing is
    extractable (e.g. a JS-only page) rather than raising."""
    import trafilatura
    text = trafilatura.extract(html) or ""
    title = ""
    meta = trafilatura.extract_metadata(html)
    if meta is not None and meta.title:
        title = meta.title
    return title, text


def fetch_main_text(url, http_get=None, extract=None):
    """Fetch `url` and return (title, text). Title falls back to the URL host
    when the extractor yields none. Only network errors propagate; empty
    extraction yields ('<host>', '') for the caller to skip."""
    get = http_get or _default_get
    extract = extract or _default_extract
    html = get(url)
    title, text = extract(html)
    if not title:
        title = urlparse(url).netloc or url
    return title, text
```

- [ ] **Step 4: Add the dependency**

In `requirements.txt`, add this line after the `beautifulsoup4` line:

```
trafilatura>=1.8  # web-fallback (SP2b) HTML main-text extraction; lazy-imported
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_fetch.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/scraper/web_fetch.py requirements.txt tests/test_web_fetch.py
git commit -m "feat: fetch_main_text web extractor (trafilatura, injectable)"
```

---

## Task 5: run_web_fetch pure orchestrator

**Files:**
- Create: `meister_guide/scraper/web_ingest.py`
- Test: `tests/test_web_ingest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_ingest.py`:

```python
from meister_guide.scraper.web_ingest import run_web_fetch
from meister_guide.scraper.urls import web_pageid
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeSearch:
    def __init__(self, results):
        self._results = results
        self.searched = None

    def search(self, query, count=3):
        self.searched = (query, count)
        return list(self._results)


def _repo(tmp_path):
    conn = connect(tmp_path / "web.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'G', '[]')")
    conn.commit()
    return ArticlesRepo(conn)


def _fetch_fn(pages):
    # pages: dict url -> (title, text)
    def fetch(url):
        return pages.get(url, ("", ""))
    return fetch


def test_ingests_results_scoped_to_game_with_source_url(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Tame a wolf", "https://x/wolf")])
    fetch = _fetch_fn({"https://x/wolf": ("Tame a wolf", "Give it a bone." * 50)})
    n = run_web_fetch(search, fetch, repo, game_id=7, query="tame wolf")
    assert n == 1
    assert repo.count(game_id=7) == 1
    art = repo.get_article(web_pageid("https://x/wolf"))
    assert art.url == "https://x/wolf"
    assert "bone" in art.body


def test_skips_pages_under_min_chars(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Thin", "https://x/thin")])
    fetch = _fetch_fn({"https://x/thin": ("Thin", "too short")})
    n = run_web_fetch(search, fetch, repo, 7, "q", min_chars=200)
    assert n == 0
    assert repo.count(game_id=7) == 0


def test_caps_at_limit(tmp_path):
    repo = _repo(tmp_path)
    results = [(f"T{i}", f"https://x/{i}") for i in range(10)]
    pages = {u: (t, "body " * 100) for t, u in results}
    n = run_web_fetch(FakeSearch(results), _fetch_fn(pages), repo, 7, "q", limit=3)
    assert n == 3
    assert repo.count(game_id=7) == 3


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetch = _fetch_fn({"https://x/wolf": ("Wolf", "body " * 100)})
    assert run_web_fetch(search, fetch, repo, 7, "q") == 1
    assert run_web_fetch(search, fetch, repo, 7, "q") == 0   # synthetic pageid dedupe
    assert repo.count(game_id=7) == 1


def test_no_results_makes_no_fetch(tmp_path):
    repo = _repo(tmp_path)
    fetched = []
    def fetch(url):
        fetched.append(url)
        return ("t", "body " * 100)
    n = run_web_fetch(FakeSearch([]), fetch, repo, 7, "q")
    assert n == 0
    assert fetched == []


def test_should_cancel_stops_before_fetch(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetched = []
    def fetch(url):
        fetched.append(url)
        return ("t", "body " * 100)
    n = run_web_fetch(search, fetch, repo, 7, "q", should_cancel=lambda: True)
    assert n == 0
    assert fetched == []        # cancelled before any fetch
    assert repo.count(game_id=7) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_ingest.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.scraper.web_ingest'`.

- [ ] **Step 3: Implement**

Create `meister_guide/scraper/web_ingest.py`:

```python
"""Web-search fallback: search the web, scrape the top results, and ingest them
scoped to the game so they answer through the normal RAG path. Pure (no Qt) so
it stays unit-testable; WebFetchWorker wraps it for threading. Idempotent: pages
are keyed by a synthetic URL-hash pageid, so a re-run skips already-stored pages."""
from meister_guide.scraper.urls import web_pageid


def run_web_fetch(search_client, fetch_fn, articles_repo, game_id, query,
                  limit=3, min_chars=200, should_cancel=None):
    """search -> per-URL fetch+extract -> skip too-short pages -> add_article
    scoped to game_id (url stored as the real result URL, revid None). Returns
    the number newly ingested. should_cancel() is polled before the search result
    is consumed and before each page fetch so a quit/hide aborts promptly."""
    results = search_client.search(query, limit)
    if should_cancel and should_cancel():
        return 0
    n = 0
    for title, url in results[:limit]:
        if should_cancel and should_cancel():
            break
        page_title, text = fetch_fn(url)
        if len((text or "").strip()) < min_chars:
            continue
        if articles_repo.add_article(web_pageid(url), page_title or title or url,
                                     text, None, url, game_id=game_id):
            n += 1
    return n
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_ingest.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/web_ingest.py tests/test_web_ingest.py
git commit -m "feat: run_web_fetch pure web search+scrape+ingest orchestrator"
```

---

## Task 6: WebFetchWorker

**Files:**
- Modify: `meister_guide/scraper/worker.py`
- Test: `tests/test_web_worker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_worker.py`:

```python
from PySide6.QtWidgets import QApplication
from meister_guide.scraper.worker import WebFetchWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeSearch:
    def __init__(self, results):
        self._results = results
    def search(self, query, count=3):
        return list(self._results)


def _seed_game(db):
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'G', '[]')")
    conn.commit()
    conn.close()


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "w.db"
    _seed_game(db)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetch = lambda url: ("Wolf", "body " * 100)
    worker = WebFetchWorker(str(db), game_id=7, query="wolf", api_key="k",
                            client=search, fetch_fn=fetch)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def search(self, q, count=3):
            raise RuntimeError("offline")
    worker = WebFetchWorker(str(tmp_path / "e.db"), game_id=7, query="q",
                            api_key="k", client=Boom(), fetch_fn=lambda u: ("", ""))
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert counts == []
    assert errors and "offline" in errors[0]


def test_worker_cancel_skips_ingest(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "c.db"
    _seed_game(db)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    worker = WebFetchWorker(str(db), game_id=7, query="wolf", api_key="k",
                            client=search, fetch_fn=lambda u: ("Wolf", "body " * 100))
    worker.cancel()
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [0]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_worker.py -q`
Expected: FAIL with `ImportError: cannot import name 'WebFetchWorker'`.

- [ ] **Step 3: Implement**

In `meister_guide/scraper/worker.py`, add these imports next to the existing scraper imports (near the `run_on_demand_fetch` / `run_category_seed` imports):

```python
from meister_guide.scraper.web_search import BraveSearchClient
from meister_guide.scraper.web_fetch import fetch_main_text
from meister_guide.scraper.web_ingest import run_web_fetch
```

Then append this class at the END of the file (after `CategorySeedWorker`):

```python
class WebFetchWorker(QObject):
    """Runs a single web-search fallback off the UI thread. Opens its OWN SQLite
    connection inside run() and builds a BraveSearchClient from the api_key (or
    uses an injected client/fetch_fn for tests)."""
    finished = Signal(int)   # number of articles ingested
    error = Signal(str)

    def __init__(self, db_path, game_id, query, api_key, limit=3,
                 client=None, fetch_fn=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._query = query
        self._api_key = api_key
        self._limit = limit
        self._client = client
        self._fetch_fn = fetch_fn
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        conn = None
        n = 0
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or BraveSearchClient(self._api_key)
            fetch_fn = self._fetch_fn or fetch_main_text
            n = run_web_fetch(client, fetch_fn, ArticlesRepo(conn),
                              self._game_id, self._query, limit=self._limit,
                              should_cancel=lambda: self._cancel)
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit(n)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_worker.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/worker.py tests/test_web_worker.py
git commit -m "feat: WebFetchWorker runs the web fallback off-thread"
```

---

## Task 7: Window integration — fallback chain, Settings UI, lifecycle

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_window_web.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_window_web.py`:

```python
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.settings import SettingsRepo


class OllamaStub:
    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]
    def chat(self, model, messages):
        return iter(())


def _window(tmp_path, key=""):
    db = tmp_path / "w.db"
    conn = connect(db)
    init_db(conn)
    QApplication.instance() or QApplication([])
    games = GamesRepo(conn)
    g = games.add("NoWiki", [], None)   # no wiki_url -> web is the only fallback
    repo = SettingsRepo(conn)
    if key:
        repo.set("brave_api_key", key)
    w = OverlayWindow(QSettings("MeisterGuide", "Web"),
                      games.list_games(), ArticlesRepo(conn), str(db), None,
                      OllamaStub(), settings_repo=repo, games_repo=games)
    w._set_active(g, manual=True)
    return w, repo


def test_web_enabled_reflects_settings(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    assert w._web_enabled() is True
    repo.set("web_fallback", "0")
    assert w._web_enabled() is False


def test_hits_answer_without_web(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._retrieve = lambda q: ([(1, "T")], [("T", "passage")])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web


def test_miss_with_web_enabled_starts_web_fetch(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert web and not answered


def test_miss_with_web_disabled_answers_anyway(tmp_path):
    w, repo = _window(tmp_path)   # no key -> web disabled
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web


def test_web_fetch_done_cancelled_restores_input(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._chat_cancelled = True
    started = []
    w._start_chat_worker = lambda: started.append(True)
    w._on_web_fetch_done("q", [])
    assert started == []
    assert w.chat_input.isEnabled()


def test_web_fetch_done_answers(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    w._chat_cancelled = False
    w._chat_view = [{"role": "user", "text": "q", "sources": []},
                    {"role": "assistant", "text": "", "sources": []}]
    w._retrieve = lambda q: ([(1, "T")], [("T", "p")])
    started = []
    w._start_chat_worker = lambda: started.append(True)
    w._on_web_fetch_done("q", [])
    assert started == [True]


def test_shutdown_cancels_active_web_worker(tmp_path):
    w, repo = _window(tmp_path, key="brv-123")
    class FakeWorker:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True
    fw = FakeWorker()
    w._web_worker = fw
    w.shutdown()
    assert fw.cancelled


def test_settings_persists_brave_key_and_toggle(tmp_path):
    w, repo = _window(tmp_path)
    w.set_brave_key.setText("brv-xyz")
    w.set_web_fallback.setChecked(False)
    w._on_save_settings()
    assert repo.brave_api_key() == "brv-xyz"
    assert repo.get("web_fallback") == "0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_window_web.py -q`
Expected: FAIL — `AttributeError` on `w._web_enabled` / `w.set_brave_key` (don't exist yet).

- [ ] **Step 3: Add `QCheckBox` to the widget import**

In `meister_guide/overlay/window.py`, change the `from PySide6.QtWidgets import (...)` block to include `QCheckBox`:

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox, QCheckBox,
    QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QProgressBar, QSplitter,
)
```

- [ ] **Step 4: Add the worker import + `__init__` state**

Update the worker import line to add `WebFetchWorker`:

```python
from meister_guide.scraper.worker import (
    IngestWorker, OnDemandFetchWorker, CategorySeedWorker, WebFetchWorker,
)
```

In `__init__`, after `self._seed_worker = None`, add:

```python
        self._web_thread = None
        self._web_worker = None
```

- [ ] **Step 5: Add the re-entry guard for the web thread**

In `_on_send`, change the guard condition from:

```python
        if (not self.chat_input.isEnabled() or self._chat_thread is not None
                or self._fetch_thread is not None):
            return
```

to:

```python
        if (not self.chat_input.isEnabled() or self._chat_thread is not None
                or self._fetch_thread is not None or self._web_thread is not None):
            return
```

- [ ] **Step 6: Route the hit/not-fetchable path through the fallback helper**

In `_on_send`, replace the "Hit path (and not-fetchable)" block:

```python
        # Hit path (and not-fetchable): answer from the local corpus now.
        sources, passages = self._retrieve(question)
        self._begin_exchange(question, sources)
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()
```

with:

```python
        # Hit path, or a miss we can't fetch from a wiki: answer now, or fall
        # back to a web search first if it's enabled.
        self._answer_or_web_fallback(question, history, reuse_turn=False)
```

- [ ] **Step 7: Route the post-wiki-fetch path through the fallback helper**

In `_on_fetch_done`, replace the answer portion (everything after the `_chat_cancelled` early-return block):

```python
        sources, passages = self._retrieve(question)
        # Reuse the existing placeholder assistant turn for streaming; just
        # attach the sources the fetch produced.
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["sources"] = sources
        self._render_chat()
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()
```

with:

```python
        # The wiki fetch is done. If it produced hits we answer; if it's still
        # empty and web fallback is on, escalate to a web search (reusing the
        # placeholder assistant turn already on screen).
        self._answer_or_web_fallback(question, history, reuse_turn=True)
```

- [ ] **Step 8: Add the helper methods**

Add these methods to `OverlayWindow`, right after `_on_fetch_done` / `_teardown_fetch_thread` (i.e. alongside the existing fetch lifecycle):

```python
    def _web_enabled(self):
        return (self._db_path is not None and self._settings_repo is not None
                and self._settings_repo.web_fallback_enabled())

    def _answer_now(self, question, history, sources, passages, reuse_turn):
        """Start the chat stream for `question`. reuse_turn=True keeps the
        on-screen placeholder assistant turn (post-fetch); False opens a new
        exchange (direct hit path)."""
        if reuse_turn:
            if self._chat_view and self._chat_view[-1]["role"] == "assistant":
                self._chat_view[-1]["sources"] = sources
            self._render_chat()
        else:
            self._begin_exchange(question, sources)
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()

    def _answer_or_web_fallback(self, question, history, reuse_turn):
        """Retrieve and answer; if there's nothing and web fallback is enabled,
        run a web search first (then answer in _on_web_fetch_done)."""
        sources, passages = self._retrieve(question)
        if sources or not self._web_enabled():
            self._answer_now(question, history, sources, passages, reuse_turn)
        else:
            self._start_web_fetch(question, history, reuse_turn)

    def _start_web_fetch(self, question, history, reuse_turn):
        """Last-resort miss path: search the web, scrape+ingest off-thread, then
        answer from what was fetched (in _on_web_fetch_done). reuse_turn keeps an
        existing placeholder turn (post-wiki-fetch) instead of opening a new one."""
        if not reuse_turn:
            self._begin_exchange(question, [])
        self.chat_status.setText("Searching the web…")
        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        self._web_thread = QThread(self)
        self._web_worker = WebFetchWorker(
            str(self._db_path), self._active_game_id(), question,
            self._settings_repo.brave_api_key())
        self._web_worker.moveToThread(self._web_thread)
        self._web_thread.started.connect(self._web_worker.run)
        self._web_worker.finished.connect(
            lambda _n: self._on_web_fetch_done(question, history))
        self._web_worker.error.connect(
            lambda _m: self._on_web_fetch_done(question, history))
        self._web_thread.start()

    def _on_web_fetch_done(self, question, history):
        self._teardown_web_thread()
        if self._chat_cancelled:
            # Overlay was hidden mid-fetch: restore input and don't start a chat.
            self.chat_input.setEnabled(True)
            self.chat_send_btn.setEnabled(True)
            self.chat_status.setText("")
            return
        sources, passages = self._retrieve(question)
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["sources"] = sources
        self._render_chat()
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()

    def _teardown_web_thread(self):
        if self._web_thread is not None:
            self._web_thread.quit()
            self._web_thread.wait(5000)
        self._web_thread = None
        self._web_worker = None
```

- [ ] **Step 9: Build the Settings UI (Brave key + checkbox)**

In `_build_settings_tab`, inside the `if self._settings_repo is not None:` block, immediately after the "Claude model" combo is added (the `col.addWidget(self.set_model)` line) and BEFORE the `save = QPushButton("Save backend settings")` line, insert:

```python
            col.addWidget(QLabel("Brave Search API key (web fallback)"))
            self.set_brave_key = QLineEdit(self._settings_repo.brave_api_key())
            self.set_brave_key.setEchoMode(QLineEdit.Password)
            self.set_brave_key.setPlaceholderText(
                "brv-…  (enables web search when the wiki can't answer)")
            col.addWidget(self.set_brave_key)
            self.set_web_fallback = QCheckBox("Allow web search fallback")
            self.set_web_fallback.setChecked(
                self._settings_repo.get("web_fallback") != "0")
            col.addWidget(self.set_web_fallback)
```

- [ ] **Step 10: Persist the new settings on save**

In `_on_save_settings`, after the existing `self._settings_repo.set("claude_model", ...)` line and before `self._refresh_chat_backend()`, add:

```python
        self._settings_repo.set("brave_api_key", self.set_brave_key.text().strip())
        self._settings_repo.set("web_fallback",
                                "1" if self.set_web_fallback.isChecked() else "0")
```

- [ ] **Step 11: Cancel the web worker on hide/shutdown**

In `hideEvent`, after the `_seed_worker` cancel block, add:

```python
        if self._web_worker is not None:
            self._chat_cancelled = True
            self._web_worker.cancel()
```

In `shutdown`, after the `_seed_worker` cancel block (`if self._seed_worker is not None: self._seed_worker.cancel()`), add:

```python
        if self._web_worker is not None:
            self._web_worker.cancel()
```

and after `self._teardown_seed()` add:

```python
        self._teardown_web_thread()
```

- [ ] **Step 12: Run the tests to verify they pass**

Run: `py -m pytest tests/test_window_web.py -q`
Expected: PASS (8 passed).

- [ ] **Step 13: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS — all prior tests plus the new ones.

- [ ] **Step 14: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_web.py
git commit -m "feat: web-search fallback chain + Brave key Settings UI + lifecycle"
```

---

## Final verification

- [ ] Run `py -m pytest -q` — confirm the whole suite passes.
- [ ] Confirm no perpetually-dirty files were staged (`.planning/HANDOFF.json`, `devlogs/the-whole-build.md`, `Meister Guide overlay design/`, `DONOTTOUCH.txt`).
- [ ] Then proceed to `superpowers:finishing-a-development-branch`.

## Notes / rationale

- **Last-resort chain:** `_answer_or_web_fallback` is the single decision point, called from both the direct path (`_on_send`, `reuse_turn=False`) and the post-wiki path (`_on_fetch_done`, `reuse_turn=True`). `reuse_turn` is the only behavioral difference (open a new exchange vs reuse the on-screen placeholder), factored into `_answer_now` / `_start_web_fetch`.
- **Gating:** `_web_enabled()` defers entirely to `SettingsRepo.web_fallback_enabled()` (key present AND pref not "0"), so no key or a paused toggle means the chain never enters web fetch and behavior is identical to today.
- **Injectable everything:** Brave HTTP, the HTML extractor, and the worker's client/fetch_fn are all injectable, so the whole stack tests offline without the trafilatura dependency or a network/key.
- **Synthetic pageid:** web pages reuse the `articles` table via `web_pageid(url)`; idempotency and game-scoping come for free from `add_article`.
- **trafilatura is lazy-imported** in the default extractor only (mirrors the `anthropic` pattern), so importing the scraper modules never requires it.
```
