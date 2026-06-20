# Per-game Category Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pre-load a bounded set of guide pages for any added game by choosing a wiki category, walking it one level deep, and ingesting up to 500 pages scoped to that game.

**Architecture:** A close parallel of the SP2a on-demand stack. A new `WikiClient.iter_category_members` enumerates a category (one level: direct article members + each immediate subcategory's article members). A pure `scraper/seed.py::run_category_seed` fetches each title's full extract, skips noise, and ingests idempotently (dedupe by pageid via `add_article`). A `CategorySeedWorker` (sibling of `OnDemandFetchWorker`) runs it off the UI thread with its own SQLite connection. The ⚙ Settings tab gains a "Seed guides from a category" block (game picker + category field + Seed button + progress bar). No `scrape_state` migration is needed — the seed is a single bounded, idempotent run, so Minecraft's full-walk machinery is untouched.

**Tech Stack:** Python, PySide6 (Qt), SQLite + FTS5, MediaWiki action API, pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-category-seed-design.md`

**Test runner:** `py -m pytest -q` (the `python`/`python3` aliases are broken Windows Store stubs — use `py`).

---

## File Structure

- **Modify** `meister_guide/scraper/wiki_client.py` — add `_normalize_category`, `_category_members` (paginated generator), and public `iter_category_members`.
- **Create** `meister_guide/scraper/seed.py` — pure `run_category_seed(...)`.
- **Modify** `meister_guide/scraper/worker.py` — add `CategorySeedWorker`.
- **Modify** `meister_guide/overlay/window.py` — Settings-tab UI, `_on_seed_category`, progress/finished/error/teardown handlers, `_refresh_seed_games`, lifecycle cancel hooks; init `_seed_thread`/`_seed_worker` in `__init__`.
- **Create** `tests/test_category_members.py` — client enumeration tests.
- **Create** `tests/test_seed.py` — pure `run_category_seed` tests.
- **Create** `tests/test_seed_worker.py` — worker signal tests.
- **Create** `tests/test_window_seed.py` — Settings-tab UI tests.

---

## Task 1: `WikiClient.iter_category_members`

Enumerate a category's article members one level deep (direct members + each immediate subcategory's article members), with `cmcontinue` pagination.

**Files:**
- Modify: `meister_guide/scraper/wiki_client.py`
- Test: `tests/test_category_members.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_category_members.py`:

```python
from meister_guide.scraper.wiki_client import WikiClient


def test_normalizes_bare_name_to_category_title():
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.iter_category_members("Mobs")
    assert seen[0]["cmtitle"] == "Category:Mobs"
    assert seen[0]["list"] == "categorymembers"


def test_accepts_category_prefixed_name():
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.iter_category_members("Category:Items")
    assert seen[0]["cmtitle"] == "Category:Items"


def test_empty_category_name_returns_empty_without_request():
    calls = []
    def fake_get(params):
        calls.append(params)
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("  ") == []
    assert calls == []


def test_returns_direct_article_members_only_when_no_subcats():
    def fake_get(params):
        return {"query": {"categorymembers": [
            {"pageid": 1, "ns": 0, "title": "Creeper"},
            {"pageid": 2, "ns": 0, "title": "Zombie"},
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["Creeper", "Zombie"]


def test_recurses_one_level_into_subcategories():
    def fake_get(params):
        if params["cmtitle"] == "Category:Mobs":
            # top level: one article + one subcategory (ns 14)
            assert params["cmnamespace"] == "0|14"
            return {"query": {"categorymembers": [
                {"pageid": 1, "ns": 0, "title": "Creeper"},
                {"pageid": 99, "ns": 14, "title": "Category:Hostile mobs"},
            ]}}
        if params["cmtitle"] == "Category:Hostile mobs":
            # subcategory: articles only (ns 0)
            assert params["cmnamespace"] == "0"
            return {"query": {"categorymembers": [
                {"pageid": 2, "ns": 0, "title": "Zombie"},
                {"pageid": 100, "ns": 14, "title": "Category:Nether mobs"},  # ignored
            ]}}
        raise AssertionError(params["cmtitle"])
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    # Zombie pulled from the subcategory; the deeper Nether subcategory is NOT walked.
    assert client.iter_category_members("Mobs") == ["Creeper", "Zombie"]


def test_dedupes_titles_across_category_and_subcategory():
    def fake_get(params):
        if params["cmtitle"] == "Category:Mobs":
            return {"query": {"categorymembers": [
                {"pageid": 1, "ns": 0, "title": "Creeper"},
                {"pageid": 14, "ns": 14, "title": "Category:Sub"},
            ]}}
        return {"query": {"categorymembers": [
            {"pageid": 1, "ns": 0, "title": "Creeper"},  # duplicate of top level
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["Creeper"]


def test_follows_cmcontinue_pagination():
    page1 = {"query": {"categorymembers": [{"pageid": 1, "ns": 0, "title": "A"}]},
             "continue": {"cmcontinue": "B", "continue": "-||"}}
    page2 = {"query": {"categorymembers": [{"pageid": 2, "ns": 0, "title": "B"}]}}
    responses = [page1, page2]
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return responses.pop(0)
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["A", "B"]
    assert seen[1].get("cmcontinue") == "B"   # carried the continuation
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_category_members.py -q`
Expected: FAIL with `AttributeError: 'WikiClient' object has no attribute 'iter_category_members'`.

- [ ] **Step 3: Implement the client method**

In `meister_guide/scraper/wiki_client.py`, add a module-level helper above the `WikiClient` class (after the `WikiArticle` dataclass):

```python
def _normalize_category(name):
    """Turn 'Mobs' or 'Category:Mobs' into a 'Category:'-prefixed title.
    Returns '' for blank input so the caller can short-circuit."""
    name = (name or "").strip()
    if not name:
        return ""
    if name.lower().startswith("category:"):
        return name
    return "Category:" + name
```

Then add these two methods to `WikiClient` (place them just above `iter_batches`):

```python
    def _category_members(self, category, namespaces):
        """Yield member dicts ({'pageid','ns','title'}) for one category,
        following cmcontinue. `namespaces` is a cmnamespace value, e.g. '0|14'
        (articles + subcategories) or '0' (articles only)."""
        token = None
        while True:
            params = {
                "action": "query", "format": "json",
                "list": "categorymembers", "cmtitle": category,
                "cmnamespace": namespaces, "cmlimit": 500, "maxlag": 5,
            }
            if token:
                params.update(token)
            data = self._fetch(params)
            for member in data.get("query", {}).get("categorymembers", []):
                yield member
            cont = data.get("continue")
            if not cont:
                return
            token = cont
            self._sleep(self._delay)

    def iter_category_members(self, category):
        """Article titles in `category`, walked one level deep: the category's
        direct article members (ns 0) plus the article members of each immediate
        subcategory (ns 14). Deduped, order-preserving. Returns [] for a blank
        category name without making a request."""
        cat = _normalize_category(category)
        if not cat:
            return []
        titles, subcats, seen = [], [], set()
        for member in self._category_members(cat, "0|14"):
            if member.get("ns") == 14:
                subcats.append(member["title"])
            else:
                title = member.get("title")
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        for sub in subcats:
            for member in self._category_members(sub, "0"):
                title = member.get("title")
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        return titles
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_category_members.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_category_members.py
git commit -m "feat: WikiClient.iter_category_members (one-level category walk)"
```

---

## Task 2: `run_category_seed` pure function

Fetch and ingest each enumerated title's full extract, skipping noise, idempotent by pageid, bounded by `cap`, with progress + cancel hooks.

**Files:**
- Create: `meister_guide/scraper/seed.py`
- Test: `tests/test_seed.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_seed.py`:

```python
from meister_guide.scraper.seed import run_category_seed
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    """iter_category_members returns canned titles; fetch_by_titles returns the
    canned article for each requested title (one per request, like TextExtracts)."""
    def __init__(self, titles, by_title):
        self._titles = titles
        self._by_title = by_title
        self.fetched = []

    def iter_category_members(self, category):
        return list(self._titles)

    def fetch_by_titles(self, titles):
        self.fetched.append(list(titles))
        out = []
        for t in titles:
            if t in self._by_title:
                out.append(self._by_title[t])
        return out


def _repo(tmp_path):
    conn = connect(tmp_path / "seed.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'TestGame', '[]')")
    conn.commit()
    return ArticlesRepo(conn)


def test_ingests_all_members_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Zombie"],
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
         "Zombie": WikiArticle(2, "Zombie", "groan", 6)},
    )
    n = run_category_seed(client, repo, game_id=7, category="Mobs",
                          base="https://mc.wiki")
    assert n == 2
    assert repo.count(game_id=7) == 2
    assert repo.get_article(1).url == "https://mc.wiki/wiki/Creeper"


def test_skips_noise_titles_without_fetching(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Java Edition 1.16"],   # second is a noise title
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5)},
    )
    n = run_category_seed(client, repo, 7, "Mobs")
    assert n == 1
    assert repo.count(game_id=7) == 1
    assert client.fetched == [["Creeper"]]   # never fetched the noise title


def test_caps_number_of_pages(tmp_path):
    repo = _repo(tmp_path)
    titles = [f"P{i}" for i in range(10)]
    by_title = {t: WikiArticle(i, t, "x", 1) for i, t in enumerate(titles)}
    client = FakeClient(titles, by_title)
    n = run_category_seed(client, repo, 7, "Mobs", cap=3)
    assert n == 3
    assert repo.count(game_id=7) == 3


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    assert run_category_seed(client, repo, 7, "Mobs") == 1
    assert run_category_seed(client, repo, 7, "Mobs") == 0   # dedupe by pageid
    assert repo.count(game_id=7) == 1


def test_progress_reports_total_then_each_step(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Zombie"],
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
         "Zombie": WikiArticle(2, "Zombie", "groan", 6)},
    )
    calls = []
    run_category_seed(client, repo, 7, "Mobs",
                      progress_cb=lambda d, t: calls.append((d, t)))
    assert calls[0] == (0, 2)
    assert calls[-1] == (2, 2)


def test_should_cancel_stops_mid_walk(tmp_path):
    repo = _repo(tmp_path)
    titles = ["Creeper", "Zombie", "Skeleton"]
    by_title = {t: WikiArticle(i, t, "x", 1) for i, t in enumerate(titles)}
    client = FakeClient(titles, by_title)
    # cancel after the first page is ingested
    seen = {"n": 0}
    def should_cancel():
        seen["n"] += 1
        return seen["n"] > 1
    n = run_category_seed(client, repo, 7, "Mobs", should_cancel=should_cancel)
    assert n == 1
    assert repo.count(game_id=7) == 1


def test_empty_category_ingests_nothing(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient([], {})
    assert run_category_seed(client, repo, 7, "Mobs") == 0
    assert client.fetched == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_seed.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.scraper.seed'`.

- [ ] **Step 3: Implement the pure function**

Create `meister_guide/scraper/seed.py`:

```python
"""Per-game category seed: enumerate a wiki category one level deep, fetch each
page's full extract, and ingest it scoped to the game. Pure (no Qt) so it stays
unit-testable; CategorySeedWorker wraps it for threading. Bounded by `cap` and
idempotent (add_article dedupes by pageid), so a re-run after an interruption
just skips already-stored pages."""
from meister_guide.ai.ranking import is_noise
from meister_guide.scraper.on_demand import _page_url


def run_category_seed(client, articles_repo, game_id, category, base="",
                      cap=500, progress_cb=None, should_cancel=None):
    """Walk `category` (one level) -> for each title fetch its full extract ->
    skip noise -> add_article scoped to game_id. Returns the number of articles
    newly ingested. Titles are deduped and truncated to `cap`. should_cancel()
    is polled before each page so a quit/hide aborts promptly. progress_cb(done,
    total) is called once with (0, total) and after each title."""
    seen, titles = set(), []
    for title in client.iter_category_members(category):
        if title not in seen:
            seen.add(title)
            titles.append(title)
    titles = titles[:cap]
    total = len(titles)
    if progress_cb:
        progress_cb(0, total)
    n = 0
    for i, title in enumerate(titles, start=1):
        if should_cancel and should_cancel():
            break
        if is_noise(title):
            if progress_cb:
                progress_cb(i, total)
            continue
        for art in client.fetch_by_titles([title]):
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, _page_url(base, art.title),
                                         game_id=game_id):
                n += 1
        if progress_cb:
            progress_cb(i, total)
    return n
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_seed.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/seed.py tests/test_seed.py
git commit -m "feat: run_category_seed pure bounded per-game category ingest"
```

---

## Task 3: `CategorySeedWorker`

Run the seed off the UI thread with its own SQLite connection and per-game `WikiClient`.

**Files:**
- Modify: `meister_guide/scraper/worker.py`
- Test: `tests/test_seed_worker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_seed_worker.py`:

```python
from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import CategorySeedWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, by_title):
        self._titles, self._by_title = titles, by_title

    def iter_category_members(self, category):
        return list(self._titles)

    def fetch_by_titles(self, titles):
        return [self._by_title[t] for t in titles if t in self._by_title]


def _seed_game(db):
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'T', '[]')")
    conn.commit()
    conn.close()


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "s.db"
    _seed_game(db)
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="https://x/api.php",
                                page_url_base="https://x", category="Mobs",
                                client=client)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_progress(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "p.db"
    _seed_game(db)
    client = FakeClient(["Creeper", "Zombie"],
                        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
                         "Zombie": WikiArticle(2, "Zombie", "groan", 6)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=client)
    progress = []
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.run()
    assert progress[0] == (0, 2)
    assert progress[-1] == (2, 2)


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def iter_category_members(self, category):
            raise RuntimeError("offline")
        def fetch_by_titles(self, titles):
            return []
    worker = CategorySeedWorker(str(tmp_path / "e.db"), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=Boom())
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
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=client)
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

Run: `py -m pytest tests/test_seed_worker.py -q`
Expected: FAIL with `ImportError: cannot import name 'CategorySeedWorker'`.

- [ ] **Step 3: Implement the worker**

In `meister_guide/scraper/worker.py`, add the seed import next to the existing on-demand import (near line 12):

```python
from meister_guide.scraper.seed import run_category_seed
```

Then append this class at the end of the file (after `OnDemandFetchWorker`):

```python
class CategorySeedWorker(QObject):
    """Runs a single per-game category seed off the UI thread. Opens its OWN
    SQLite connection inside run() (connections aren't thread-safe to share) and
    builds a WikiClient pointed at the active game's API endpoint."""
    progress = Signal(int, int)   # done, total
    finished = Signal(int)        # number of articles ingested
    error = Signal(str)

    def __init__(self, db_path, game_id, api_url, page_url_base, category,
                 cap=500, client=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._api_url = api_url
        self._page_url_base = page_url_base
        self._category = category
        self._cap = cap
        self._client = client
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        conn = None
        n = 0
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient(api_url=self._api_url)
            n = run_category_seed(
                client, ArticlesRepo(conn), self._game_id, self._category,
                base=self._page_url_base, cap=self._cap,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                should_cancel=lambda: self._cancel,
            )
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit(n)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_seed_worker.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/worker.py tests/test_seed_worker.py
git commit -m "feat: CategorySeedWorker runs the category seed off-thread"
```

---

## Task 4: Settings-tab seed UI + lifecycle

Add the "Seed guides from a category" block, its handlers, game-picker refresh, and cancel-on-hide/shutdown.

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_window_seed.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_window_seed.py`:

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


def _window(tmp_path):
    db = tmp_path / "w.db"
    conn = connect(db)
    init_db(conn)
    QApplication.instance() or QApplication([])
    games = GamesRepo(conn)
    nowiki = games.add("NoWiki", [], None)
    withwiki = games.add("Subnautica", [], "https://subnautica.fandom.com")
    w = OverlayWindow(QSettings("MeisterGuide", "Seed"),
                      games.list_games(), ArticlesRepo(conn), str(db), None,
                      OllamaStub(), settings_repo=SettingsRepo(conn),
                      games_repo=games)
    return w, nowiki, withwiki


def test_seed_combo_lists_games(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    labels = [w.seed_game.itemText(i) for i in range(w.seed_game.count())]
    assert "Subnautica" in labels and "NoWiki" in labels


def test_seed_without_wiki_url_shows_message_and_starts_no_thread(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_game.setCurrentIndex(w.seed_game.findData(nowiki.id))
    w.seed_category.setText("Mobs")
    w._on_seed_category()
    assert w._seed_thread is None
    assert "wiki" in w.seed_status.text().lower()


def test_seed_with_blank_category_does_nothing(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_game.setCurrentIndex(w.seed_game.findData(withwiki.id))
    w.seed_category.setText("   ")
    w._on_seed_category()
    assert w._seed_thread is None


def test_seed_progress_handler_updates_bar(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w._on_seed_progress(3, 10)
    assert w.seed_progress.maximum() == 10
    assert w.seed_progress.value() == 3


def test_seed_done_handler_reports_count_and_resets(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_btn.setEnabled(False)
    w.seed_progress.setVisible(True)
    w._on_seed_done(5)
    assert "5" in w.seed_status.text()
    assert w.seed_btn.isEnabled()
    assert not w.seed_progress.isVisible()


def test_seed_error_handler_shows_truncated_error(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w._on_seed_error("Boom happened\nsecond line")
    assert "Boom happened" in w.seed_status.text()
    assert "second line" not in w.seed_status.text()
    assert w.seed_btn.isEnabled()


def test_shutdown_cancels_active_seed_worker(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    class FakeWorker:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True
    fw = FakeWorker()
    w._seed_worker = fw
    w.shutdown()
    assert fw.cancelled
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_window_seed.py -q`
Expected: FAIL — `AttributeError` on `w.seed_game` / `w._on_seed_category` (attributes/methods don't exist yet).

- [ ] **Step 3: Add worker state to `__init__`**

In `meister_guide/overlay/window.py`, after the line `self._fetch_worker = None` (around line 92), add:

```python
        self._seed_thread = None
        self._seed_worker = None
```

- [ ] **Step 4: Add the imports**

The file already imports `IngestWorker, OnDemandFetchWorker` from `meister_guide.scraper.worker` and `api_url_for`. Update the worker import line to add `CategorySeedWorker`:

```python
from meister_guide.scraper.worker import (
    IngestWorker, OnDemandFetchWorker, CategorySeedWorker,
)
```

- [ ] **Step 5: Build the seed UI block**

In `_build_settings_tab`, replace the final `col.addStretch(1)` / `return page` lines (currently at the end of the method, after the "Add a game" block) with the seed block followed by the stretch/return:

```python
        # --- seed guides from a category ---
        col.addWidget(QLabel("<b>Seed guides from a category</b>"))
        self.seed_game = QComboBox()
        col.addWidget(self.seed_game)
        self.seed_category = QLineEdit()
        self.seed_category.setPlaceholderText("Wiki category (e.g. Mobs)")
        col.addWidget(self.seed_category)
        seed_row = QHBoxLayout()
        self.seed_btn = QPushButton("Seed")
        self.seed_btn.clicked.connect(self._on_seed_category)
        seed_row.addWidget(self.seed_btn)
        self.seed_progress = QProgressBar()
        self.seed_progress.setVisible(False)
        seed_row.addWidget(self.seed_progress, 1)
        col.addLayout(seed_row)
        self.seed_status = QLabel("")
        self.seed_status.setObjectName("Disclaimer")
        self.seed_status.setWordWrap(True)
        col.addWidget(self.seed_status)
        self._refresh_seed_games()

        col.addStretch(1)
        return page
```

- [ ] **Step 6: Add the helper + handlers**

Add these methods to `OverlayWindow` (place them right after `_on_add_game`):

```python
    def _refresh_seed_games(self):
        if not hasattr(self, "seed_game"):
            return
        current = self.seed_game.currentData()
        self.seed_game.clear()
        for game in self._games:
            self.seed_game.addItem(game.name, game.id)
        # default to the active game when nothing was previously chosen
        want = current if current is not None else (
            self.active_game.id if self.active_game is not None else None)
        if want is not None:
            idx = self.seed_game.findData(want)
            if idx >= 0:
                self.seed_game.setCurrentIndex(idx)

    def _on_seed_category(self):
        if self._db_path is None or self._seed_thread is not None:
            return
        game_id = self.seed_game.currentData()
        game = next((g for g in self._games if g.id == game_id), None)
        if game is None:
            return
        category = self.seed_category.text().strip()
        if not category:
            return
        api_url = api_url_for(game.wiki_url)
        if not api_url:
            self.seed_status.setText("This game has no wiki URL — add one first.")
            return
        self.seed_btn.setEnabled(False)
        self.seed_progress.setVisible(True)
        self.seed_progress.setRange(0, 0)   # indeterminate until first progress
        self.seed_status.setText("Seeding…")
        self._seed_thread = QThread(self)
        self._seed_worker = CategorySeedWorker(
            str(self._db_path), game.id, api_url, game.wiki_url, category)
        self._seed_worker.moveToThread(self._seed_thread)
        self._seed_thread.started.connect(self._seed_worker.run)
        self._seed_worker.progress.connect(self._on_seed_progress)
        self._seed_worker.finished.connect(self._on_seed_done)
        self._seed_worker.error.connect(self._on_seed_error)
        self._seed_thread.start()

    def _on_seed_progress(self, done, total):
        if total > 0:
            self.seed_progress.setRange(0, total)
            self.seed_progress.setValue(done)
            self.seed_status.setText(f"{done:,}/{total:,}")

    def _on_seed_done(self, count):
        self._teardown_seed()
        self.seed_status.setText(f"Added {count:,} guides.")
        self._refresh_guides_status()

    def _on_seed_error(self, message):
        self._teardown_seed()
        detail = (message or "unknown error").strip().splitlines()[0]
        if len(detail) > 160:
            detail = detail[:157] + "…"
        self.seed_status.setText(f"Seed failed: {detail}")
        self.seed_status.setToolTip(message or "")

    def _teardown_seed(self):
        self.seed_progress.setVisible(False)
        self.seed_btn.setEnabled(True)
        if self._seed_thread is not None:
            self._seed_thread.quit()
            self._seed_thread.wait(5000)
        self._seed_thread = None
        self._seed_worker = None
```

- [ ] **Step 7: Keep the game picker fresh + cancel on hide/shutdown**

In `_on_add_game`, after `self._rebuild_game_menu()`, add:

```python
        self._refresh_seed_games()
```

In `set_games`, after `self._rebuild_game_menu()`, add:

```python
        self._refresh_seed_games()
```

In `hideEvent`, after the `_fetch_worker` cancel block, add:

```python
        if self._seed_worker is not None:
            self._seed_worker.cancel()
```

In `shutdown`, after `self._fetch_worker.cancel()` (inside the `if`), add a sibling block, then add the teardown call alongside the others:

```python
        if self._seed_worker is not None:
            self._seed_worker.cancel()
```

and after `self._teardown_fetch_thread()`:

```python
        self._teardown_seed()
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `py -m pytest tests/test_window_seed.py -q`
Expected: PASS (7 passed).

- [ ] **Step 9: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS — all prior tests plus the new ones (207 + ~25 new).

- [ ] **Step 10: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_seed.py
git commit -m "feat: Settings-tab category seed UI + cancel-on-hide/shutdown"
```

---

## Final verification

- [ ] Run `py -m pytest -q` — confirm the whole suite passes.
- [ ] Confirm no perpetually-dirty files were staged (`.planning/HANDOFF.json`, `devlogs/the-whole-build.md`, `Meister Guide overlay design/`, `DONOTTOUCH.txt`).
- [ ] Then proceed to `superpowers:finishing-a-development-branch`.

## Notes / rationale

- **Why no `scrape_state`:** the seed is bounded + idempotent, so an interrupted run is recovered by re-running (already-stored pages skip). This deliberately leaves Minecraft's full-walk single-row state untouched.
- **One title per `fetch_by_titles` call:** MediaWiki TextExtracts returns ~1 full extract per request, so batching titles would silently drop all but one. The `cap=500` bound keeps the request count bounded; progress + cancel keep it interruptible.
- **`is_noise` checked on the enumerated title before fetching** — avoids spending a request on changelog/disambiguation pages.
- **`_page_url` is reused from `on_demand`** so the stored display URL uses the per-game wiki base (no hardcoded `minecraft.wiki`).
