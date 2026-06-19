# SP2a — On-Demand Wiki Fetch-on-Miss Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a chat retrieval miss for a game that has a wiki, search that wiki live, ingest the top pages scoped to the game, then re-retrieve and answer — so a newly added game with an empty corpus still answers (and is offline next time).

**Architecture:** Two new `WikiClient` methods (`search_titles`, `fetch_by_titles`) reuse the existing injectable-HTTP `_fetch`/`_articles_from`. A pure orchestrator `run_on_demand_fetch` (new `meister_guide/scraper/on_demand.py`) does search → fetch → skip-noise → `add_article(game_id=…)` and returns a count. A thin `OnDemandFetchWorker` (QThread, own SQLite connection) wraps it. `_on_send` gains a miss branch that fetches first (off-thread), then re-retrieves and answers via the existing chat worker. All heavy logic is in pure functions so the window code stays thin.

**Tech Stack:** Python, PySide6 (QThread/QObject signals), SQLite + FTS5, pytest. Tests inject fake HTTP / fake clients — no network.

**Test command (this machine):** `py -m pytest` (the `python` alias is a Windows Store stub; use `py`). Baseline before this work: **187 passed**.

---

## File Structure

- `meister_guide/scraper/wiki_client.py` — **modify**: add `search_titles` and `fetch_by_titles` (query-search + fetch-by-title), siblings of the existing bulk-ingest methods.
- `meister_guide/scraper/on_demand.py` — **create**: pure `run_on_demand_fetch(...)` + `_page_url(...)` helper. No Qt. Sibling of `ingest.py`.
- `meister_guide/scraper/worker.py` — **modify**: add `OnDemandFetchWorker(QObject)` next to `IngestWorker`.
- `meister_guide/overlay/window.py` — **modify**: factor `_retrieve(question)`, add `_active_wiki()`, add the miss branch + fetch wiring to `_on_send`, plus `_start_fetch` / `_on_fetch_done` / `_teardown_fetch_thread`, fetch-thread guard, and cancellation in `hideEvent`/`shutdown`.
- `tests/test_wiki_client.py` — **modify**: tests for the two new client methods.
- `tests/test_on_demand.py` — **create**: tests for `run_on_demand_fetch`.
- `tests/test_on_demand_worker.py` — **create**: tests for `OnDemandFetchWorker`.
- `tests/test_window_chat.py` — **modify**: tests for the `_on_send` miss/hit branches + `_on_fetch_done`.

---

## Task 1: WikiClient.search_titles + fetch_by_titles

**Files:**
- Modify: `meister_guide/scraper/wiki_client.py` (add two methods to the `WikiClient` class, after `article_count`)
- Test: `tests/test_wiki_client.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wiki_client.py`:

```python
def test_search_titles_returns_titles_in_namespace_0():
    def fake_get(params):
        assert params["action"] == "query"
        assert params["list"] == "search"
        assert params["srsearch"] == "how to tame a wolf"
        assert params["srnamespace"] == 0
        assert params["srlimit"] == 5
        return {"query": {"search": [
            {"title": "Wolf"}, {"title": "Bone"},
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.search_titles("how to tame a wolf") == ["Wolf", "Bone"]


def test_search_titles_respects_limit():
    seen = {}
    def fake_get(params):
        seen["srlimit"] = params["srlimit"]
        return {"query": {"search": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.search_titles("x", limit=3)
    assert seen["srlimit"] == 3


def test_search_titles_empty_when_no_results():
    client = WikiClient(http_get=lambda p: {"query": {"search": []}},
                        delay=0, sleep=lambda s: None)
    assert client.search_titles("zzzzz") == []


def test_fetch_by_titles_builds_titles_param_and_parses():
    def fake_get(params):
        assert params["titles"] == "Creeper|Cow"
        assert params["prop"] == "extracts"
        assert params["explaintext"] == 1
        return {"query": {"pages": {
            "1": {"pageid": 1, "title": "Creeper", "extract": "boom", "lastrevid": 5},
            "2": {"pageid": 2, "title": "Cow", "extract": "moo", "lastrevid": 6},
        }}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    arts = client.fetch_by_titles(["Creeper", "Cow"])
    assert sorted(a.title for a in arts) == ["Cow", "Creeper"]
    assert all(isinstance(a, WikiArticle) for a in arts)


def test_fetch_by_titles_empty_input_makes_no_request():
    calls = []
    def fake_get(params):
        calls.append(params)
        return {}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.fetch_by_titles([]) == []
    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_wiki_client.py -q`
Expected: FAIL — `AttributeError: 'WikiClient' object has no attribute 'search_titles'`

- [ ] **Step 3: Write the implementation**

In `meister_guide/scraper/wiki_client.py`, add these two methods to the `WikiClient` class, immediately after the `article_count` method (before `_redirect_params`):

```python
    def search_titles(self, query, limit=5):
        """MediaWiki full-text search (list=search) in the article namespace.
        Returns a list of page titles for the on-demand fetcher to pull."""
        data = self._fetch({
            "action": "query", "format": "json",
            "list": "search", "srsearch": query,
            "srnamespace": 0, "srlimit": limit, "maxlag": 5,
        })
        results = data.get("query", {}).get("search", [])
        return [r["title"] for r in results if "title" in r]

    def fetch_by_titles(self, titles):
        """Fetch plain-text extracts for specific titles (prop=extracts). Reuses
        _articles_from. TextExtracts may cap extracts per request; with <=3 titles
        we accept whatever comes back."""
        if not titles:
            return []
        data = self._fetch({
            "action": "query", "format": "json",
            "titles": "|".join(titles),
            "prop": "extracts", "explaintext": 1, "exlimit": "max",
            "maxlag": 5,
        })
        return self._articles_from(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_wiki_client.py -q`
Expected: PASS (all tests in file green)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: WikiClient.search_titles + fetch_by_titles for on-demand fetch

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: run_on_demand_fetch (pure orchestrator)

**Files:**
- Create: `meister_guide/scraper/on_demand.py`
- Test: `tests/test_on_demand.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_on_demand.py`:

```python
from meister_guide.scraper.on_demand import run_on_demand_fetch
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, articles):
        self._titles = titles
        self._articles = articles
        self.searched = None
        self.fetched = None

    def search_titles(self, query, limit=5):
        self.searched = (query, limit)
        return self._titles

    def fetch_by_titles(self, titles):
        self.fetched = titles
        return self._articles


def _repo(tmp_path):
    conn = connect(tmp_path / "od.db")
    init_db(conn)
    return ArticlesRepo(conn)


def test_ingests_non_noise_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Java Edition 1.16"],
        [WikiArticle(1, "Creeper", "boom", 5),
         WikiArticle(2, "Java Edition 1.16", "changelog", 6)],  # noise title
    )
    n = run_on_demand_fetch(client, repo, game_id=7, query="creeper",
                            base="https://minecraft.wiki")
    assert n == 1                       # the noise page is skipped
    assert repo.count(game_id=7) == 1
    art = repo.get_article(1)
    assert art.title == "Creeper"
    assert art.url == "https://minecraft.wiki/wiki/Creeper"


def test_returns_zero_and_no_fetch_when_no_search_results(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient([], [])
    assert run_on_demand_fetch(client, repo, game_id=7, query="zzz") == 0
    assert client.fetched is None       # never fetch when search found nothing


def test_limit_caps_titles_fetched(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["A", "B", "C", "D", "E"], [])
    run_on_demand_fetch(client, repo, game_id=7, query="x", limit=3)
    assert client.fetched == ["A", "B", "C"]


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Creeper"], [WikiArticle(1, "Creeper", "boom", 5)])
    assert run_on_demand_fetch(client, repo, 7, "creeper") == 1
    assert run_on_demand_fetch(client, repo, 7, "creeper") == 0   # dedupe by pageid
    assert repo.count(game_id=7) == 1


def test_page_url_handles_spaces_and_trailing_slash(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Iron Golem"],
                        [WikiArticle(9, "Iron Golem", "guards", 1)])
    run_on_demand_fetch(client, repo, 7, "golem", base="https://minecraft.wiki/")
    assert repo.get_article(9).url == "https://minecraft.wiki/wiki/Iron_Golem"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_on_demand.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'meister_guide.scraper.on_demand'`

- [ ] **Step 3: Write the implementation**

Create `meister_guide/scraper/on_demand.py`:

```python
"""On-demand wiki fetch: on a chat retrieval miss, search the active game's wiki,
fetch the top pages, and ingest them scoped to the game so they're offline next
time. Pure (no Qt) so it stays unit-testable; OnDemandFetchWorker wraps it for
threading."""
from meister_guide.ai.ranking import is_noise


def _page_url(base, title):
    """Best-effort display URL for a fetched page. Stored url is display-only."""
    return (base or "").rstrip("/") + "/wiki/" + title.replace(" ", "_")


def run_on_demand_fetch(client, articles_repo, game_id, query, limit=3, base=""):
    """Search -> fetch top `limit` titles -> skip noise -> add_article scoped to
    game_id. Returns the number of articles newly ingested. Idempotent: pages
    already stored are skipped (add_article dedupes by pageid), so a re-run after
    the same miss is a no-op."""
    titles = client.search_titles(query, limit)
    arts = client.fetch_by_titles(titles[:limit]) if titles else []
    n = 0
    for a in arts:
        if is_noise(a.title):
            continue
        if articles_repo.add_article(a.pageid, a.title, a.text, a.revid,
                                     _page_url(base, a.title), game_id=game_id):
            n += 1
    return n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_on_demand.py -q`
Expected: PASS (5 tests green)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/on_demand.py tests/test_on_demand.py
git commit -m "feat: run_on_demand_fetch — pure search+fetch+ingest orchestrator

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: OnDemandFetchWorker (thin Qt wrapper)

**Files:**
- Modify: `meister_guide/scraper/worker.py` (add a class + one import)
- Test: `tests/test_on_demand_worker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_on_demand_worker.py`:

```python
from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import OnDemandFetchWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, articles):
        self._titles, self._articles = titles, articles

    def search_titles(self, query, limit=5):
        return self._titles

    def fetch_by_titles(self, titles):
        return self._articles


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "od.db"
    client = FakeClient(["Creeper"], [WikiArticle(1, "Creeper", "boom", 5)])
    worker = OnDemandFetchWorker(str(db), game_id=7,
                                 api_url="https://x/api.php",
                                 page_url_base="https://x", query="creeper",
                                 client=client)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def search_titles(self, q, limit=5):
            raise RuntimeError("offline")
        def fetch_by_titles(self, t):
            return []
    worker = OnDemandFetchWorker(str(tmp_path / "e.db"), game_id=7,
                                 api_url="x", page_url_base="x", query="q",
                                 client=Boom())
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()

    assert counts == []
    assert errors and "offline" in errors[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_on_demand_worker.py -q`
Expected: FAIL — `ImportError: cannot import name 'OnDemandFetchWorker'`

- [ ] **Step 3: Write the implementation**

In `meister_guide/scraper/worker.py`, add this import next to the existing scraper imports (after the `from meister_guide.scraper.redirect_ingest import run_redirect_ingest` line):

```python
from meister_guide.scraper.on_demand import run_on_demand_fetch
```

Then append this class to the end of `meister_guide/scraper/worker.py`:

```python
class OnDemandFetchWorker(QObject):
    """Runs a single on-demand wiki fetch off the UI thread. Opens its OWN
    SQLite connection inside run() (SQLite connections aren't thread-safe to
    share) and builds a WikiClient pointed at the active game's API endpoint."""
    finished = Signal(int)   # number of articles ingested
    error = Signal(str)

    def __init__(self, db_path, game_id, api_url, page_url_base, query,
                 client=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._api_url = api_url
        self._page_url_base = page_url_base
        self._query = query
        self._client = client

    def run(self):
        conn = None
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient(api_url=self._api_url)
            n = run_on_demand_fetch(client, ArticlesRepo(conn), self._game_id,
                                    self._query, base=self._page_url_base)
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit(n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_on_demand_worker.py -q`
Expected: PASS (2 tests green)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/worker.py tests/test_on_demand_worker.py
git commit -m "feat: OnDemandFetchWorker — threaded wrapper for on-demand fetch

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Window wiring — `_retrieve` helper + miss branch

This task is split into sub-steps because it touches several methods in `window.py`. Do them in order; commit once at the end.

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_window_chat.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_window_chat.py` (the `OkClient`, `connect`, `init_db`, `ArticlesRepo`, `ChatRepo`, `OverlayWindow`, `QApplication`, `QSettings` imports already exist at the top of the file):

```python
from meister_guide.db.games import Game


def _window_with_wiki_game(tmp_path, with_article=False):
    conn = connect(tmp_path / "wg.db")
    init_db(conn)
    arts = ArticlesRepo(conn)
    game = Game(7, "Subnautica", [], "https://subnautica.fandom.com")
    if with_article:
        arts.add_article(1, "Peeper", "A peeper is a common fish.", 1, "u",
                         game_id=7)
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T2"), [game], arts, ":memory:",
                      chat, OkClient())
    w.active_game = game
    return w, chat


def test_send_miss_triggers_fetch_not_chat(tmp_path, monkeypatch):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    started = {}
    monkeypatch.setattr(w, "_start_fetch",
                        lambda q, h, wiki: started.update(q=q, wiki=wiki, h=h))
    w.chat_input.setText("where do peepers live?")
    w._on_send()
    assert started.get("q") == "where do peepers live?"
    assert started["wiki"][0] == "https://subnautica.fandom.com/api.php"
    assert started["h"] == []          # history captured before any turn appended
    assert w._chat_thread is None      # we answer AFTER the fetch, not now


def test_send_hit_skips_fetch(tmp_path, monkeypatch):
    w, chat = _window_with_wiki_game(tmp_path, with_article=True)
    calls = []
    monkeypatch.setattr(w, "_start_fetch", lambda *a: calls.append(a))
    w.chat_input.setText("peeper")
    w._on_send()
    assert calls == []                 # local hit -> no wiki fetch
    w._teardown_chat_thread()          # stop the chat worker started on the hit


def test_no_wiki_game_skips_fetch(tmp_path, monkeypatch):
    # Game without a wiki_url -> miss path is skipped, answer as today.
    conn = connect(tmp_path / "nw.db"); init_db(conn)
    arts = ArticlesRepo(conn)
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    game = Game(8, "MysteryGame", [], None)
    w = OverlayWindow(QSettings("MeisterGuide", "T3"), [game], arts, ":memory:",
                      chat, OkClient())
    w.active_game = game
    calls = []
    monkeypatch.setattr(w, "_start_fetch", lambda *a: calls.append(a))
    w.chat_input.setText("anything")
    w._on_send()
    assert calls == []
    w._teardown_chat_thread()


def test_on_fetch_done_answers_from_fetched(tmp_path):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    # Simulate the worker having ingested the page while it ran off-thread.
    w._articles_repo.add_article(1, "Peeper", "A peeper is a fish.", 1, "u",
                                 game_id=7)
    w._begin_exchange("what is a peeper?", [])   # placeholder, empty sources
    w._on_fetch_done("what is a peeper?", history=[])
    # the placeholder assistant turn now carries the freshly-fetched source
    assert w._chat_view[-1]["sources"] == [(1, "Peeper")]
    w._teardown_chat_thread()


def test_on_fetch_done_cancelled_does_not_start_chat(tmp_path):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    w._begin_exchange("q", [])
    w._chat_cancelled = True            # overlay hidden mid-fetch
    w._on_fetch_done("q", history=[])
    assert w._chat_thread is None       # no answer started after cancellation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_window_chat.py -q`
Expected: FAIL — `AttributeError: 'OverlayWindow' object has no attribute '_start_fetch'` (and `_on_fetch_done`).

- [ ] **Step 3: Add the new imports**

In `meister_guide/overlay/window.py`, change the worker import line:

```python
from meister_guide.scraper.worker import IngestWorker
```

to:

```python
from meister_guide.scraper.worker import IngestWorker, OnDemandFetchWorker
from meister_guide.db.games import api_url_for
```

- [ ] **Step 4: Initialize fetch-thread attributes**

In `OverlayWindow.__init__`, find the line `self._ingest_worker = None` (around line 89) and add two attributes right after it:

```python
        self._ingest_worker = None
        self._fetch_thread = None
        self._fetch_worker = None
```

- [ ] **Step 5: Replace `_on_send` with the miss-aware version + add helpers**

Replace the entire existing `_on_send` method:

```python
    def _on_send(self):
        if not self.chat_input.isEnabled() or self._chat_thread is not None:
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_input.clear()
        self._chat_cancelled = False

        sources, passages = [], []
        if self._articles_repo is not None:
            for hit in self._articles_repo.search_ranked(
                    question, limit=3, game_id=self._active_game_id()):
                article = self._articles_repo.get_article(hit.pageid)
                if article is None:
                    continue
                sources.append((hit.pageid, hit.title))
                passages.append((hit.title, relevant_passage(article.body, question)))

        history = [(m["role"], m["text"]) for m in self._chat_view if m["text"]]
        self._begin_exchange(question, sources)
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()
```

with this, and add the four helper methods immediately after it:

```python
    def _on_send(self):
        # A fetch thread blocks re-entry just like the chat thread does.
        if (not self.chat_input.isEnabled() or self._chat_thread is not None
                or self._fetch_thread is not None):
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_input.clear()
        self._chat_cancelled = False

        # Capture history BEFORE any turn is appended, so the fetch path can
        # reuse the exact same ordering the hit path relies on.
        history = [(m["role"], m["text"]) for m in self._chat_view if m["text"]]

        # Miss path: zero local hits for the active game AND the game has a wiki
        # -> fetch the wiki live first, then re-retrieve and answer.
        wiki = self._active_wiki()
        if (self._articles_repo is not None and wiki is not None
                and not self._articles_repo.search_ranked(
                    question, limit=1, game_id=self._active_game_id())):
            self._start_fetch(question, history, wiki)
            return

        # Hit path (and not-fetchable): answer from the local corpus now.
        sources, passages = self._retrieve(question)
        self._begin_exchange(question, sources)
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()

    def _retrieve(self, question):
        """Game-scoped ranked retrieval -> (sources, passages) for the prompt.
        Shared by the hit path and the post-fetch path."""
        sources, passages = [], []
        if self._articles_repo is not None:
            for hit in self._articles_repo.search_ranked(
                    question, limit=3, game_id=self._active_game_id()):
                article = self._articles_repo.get_article(hit.pageid)
                if article is None:
                    continue
                sources.append((hit.pageid, hit.title))
                passages.append(
                    (hit.title, relevant_passage(article.body, question)))
        return sources, passages

    def _active_wiki(self):
        """(api_url, wiki_base) for the active game if it has a wiki, else None."""
        gid = self._active_game_id()
        game = next((g for g in self._games if g.id == gid), None)
        if game is None or not game.wiki_url:
            return None
        api = api_url_for(game.wiki_url)
        if not api:
            return None
        return api, game.wiki_url

    def _start_fetch(self, question, history, wiki):
        """Miss path: show a placeholder, search+ingest the wiki off-thread, then
        answer from what was fetched (in _on_fetch_done). On either finished or
        error we proceed to answer — an empty fetch just yields no passages."""
        api_url, wiki_base = wiki
        self._begin_exchange(question, [])
        self.chat_status.setText("Searching the wiki…")
        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        self._fetch_thread = QThread(self)
        self._fetch_worker = OnDemandFetchWorker(
            str(self._db_path), self._active_game_id(), api_url, wiki_base,
            question)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(
            lambda _n: self._on_fetch_done(question, history))
        self._fetch_worker.error.connect(
            lambda _m: self._on_fetch_done(question, history))
        self._fetch_thread.start()

    def _on_fetch_done(self, question, history):
        self._teardown_fetch_thread()
        if self._chat_cancelled:
            return
        sources, passages = self._retrieve(question)
        # Reuse the existing placeholder assistant turn for streaming; just
        # attach the sources the fetch produced.
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["sources"] = sources
        self._render_chat()
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()

    def _teardown_fetch_thread(self):
        if self._fetch_thread is not None:
            self._fetch_thread.quit()
            self._fetch_thread.wait(5000)
        self._fetch_thread = None
        self._fetch_worker = None
```

- [ ] **Step 6: Add fetch teardown to cancellation paths**

In `hideEvent`, after the existing chat-worker cancellation block, add a fetch guard. Change:

```python
        if self._chat_worker is not None:
            self._chat_cancelled = True
            self._chat_worker.cancel()
        self._restore_demoted_game()
```

to:

```python
        if self._chat_worker is not None:
            self._chat_cancelled = True
            self._chat_worker.cancel()
        if self._fetch_worker is not None:
            self._chat_cancelled = True
        self._restore_demoted_game()
```

And in `shutdown`, change:

```python
        self._teardown_chat_thread()
        self._teardown_ingest()
```

to:

```python
        self._teardown_chat_thread()
        self._teardown_fetch_thread()
        self._teardown_ingest()
```

- [ ] **Step 7: Run the window tests to verify they pass**

Run: `py -m pytest tests/test_window_chat.py -q`
Expected: PASS (all tests in file green, including the existing `test_send_uses_ranked_retrieval`)

- [ ] **Step 8: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_chat.py
git commit -m "feat: on-demand wiki fetch on a chat retrieval miss

On 0 local hits for a game that has a wiki, search+ingest the wiki live
(off-thread), then re-retrieve and answer. Factor _retrieve; add fetch
guard + cancellation. Hit and no-wiki paths unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `py -m pytest -q`
Expected: PASS — **all green**. Baseline was 187; this plan adds 5 (`test_on_demand.py`) + 2 (`test_on_demand_worker.py`) + 4 client tests + 5 window tests = **203 passed** (exact count may differ by a test or two; the requirement is zero failures, zero errors).

- [ ] **Step 2: If anything fails, STOP and debug**

Use superpowers:systematic-debugging. Do not paper over a failure by editing the test to match broken behavior.

---

## Self-Review (performed by plan author)

**Spec coverage:**
- `WikiClient.search_titles` / `fetch_by_titles` → Task 1. ✓
- `run_on_demand_fetch(client, articles_repo, game_id, query, limit=3)` pure → Task 2 (added `base=""` param, used by `_page_url`, consistent with the spec pseudo-code that references `base`). ✓
- `OnDemandFetchWorker` (own connection, `finished(int)`/`error(str)`, ctor `(db_path, game_id, api_url, page_url_base, query, client=None)`) → Task 3. ✓
- `_on_send` miss branch on 0 local hits + game has a wiki → Task 4. ✓
- Re-entry guard for the fetch thread → Task 4 Step 5. ✓
- Capture `history` before any turn appended → Task 4 Step 5 (and asserted by `test_send_miss_triggers_fetch_not_chat`). ✓
- Miss decision via `search_ranked(..., limit=1, ...)` + `api_url_for` → Task 4 `_active_wiki` + `_on_send`. ✓
- `_begin_exchange(question, [])` placeholder + "Searching the wiki…" status → `_start_fetch`. ✓
- `_on_fetch_done` re-retrieves, sets placeholder sources, builds messages, `_start_chat_worker` → Task 4. ✓
- `_retrieve(question)` factored, used by both paths → Task 4. ✓
- Edge: offline/API error → worker `error` → still `_on_fetch_done` → answer with no passages → covered by `_start_fetch` wiring both signals to `_on_fetch_done` (`test_worker_emits_error_on_failure` proves the worker emits, no crash). ✓
- Edge: no wiki_url → miss skipped → `test_no_wiki_game_skips_fetch`. ✓
- Edge: zero search results → returns 0 → `test_returns_zero_and_no_fetch_when_no_search_results`. ✓
- Edge: dedupe idempotent → `test_idempotent_on_rerun`. ✓
- Edge: cancellation tears down fetch thread → Task 4 Step 6 + `test_on_fetch_done_cancelled_does_not_start_chat`. ✓

**Out of scope (correctly absent):** general-web fallback (SP2b), weak-hit triggering, per-game bulk (SP3). ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test shows full assertions. ✓

**Type consistency:** `run_on_demand_fetch(client, articles_repo, game_id, query, limit=3, base="")` is called identically in Task 3 worker and Task 2 tests. `OnDemandFetchWorker(db_path, game_id, api_url, page_url_base, query, client=None)` ctor matches all call sites (worker test + `_start_fetch`). `finished(int)`/`error(str)` signals match connections. `add_article(pageid, title, text, revid, url, game_id=…)` matches the real signature in `db/articles.py`. ✓
