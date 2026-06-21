# Full Wiki Downloads For Any Game — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Wiki-tab "Update guides" perform a full, resumable wiki download for any game that has a wiki URL, not just Minecraft.

**Architecture:** Make the two resume-state tables per-game (a one-time guarded rebuild, because their `CHECK (id = 1)` forbids more than one row), generalize the ingest worker with the game's API URL + page-URL base, and enable the window to start a download for the picked game while showing the wiki's page-count estimate first.

**Tech Stack:** Python, SQLite, PySide6/Qt, pytest.

**Spec:** `docs/superpowers/specs/2026-06-21-any-game-full-download-design.md`

---

## File structure

- `meister_guide/db/schema.py` — state-table DDL becomes game-keyed (named constants, reused by the migration).
- `meister_guide/db/database.py` — `migrate_game_ids` also rebuilds legacy single-row state tables to game-keyed.
- `meister_guide/db/articles.py` — `ScrapeStateRepo.load/save` take `game_id`.
- `meister_guide/db/redirects.py` — `RedirectStateRepo.load/save` take `game_id`.
- `meister_guide/scraper/ingest.py` — thread `game_id` to state; build URLs from a `base`; accept a `total` override.
- `meister_guide/scraper/redirect_ingest.py` — thread `game_id` to state and the restart count.
- `meister_guide/scraper/worker.py` — `IngestWorker` gains `api_url`/`page_url_base`, a `counted` signal, and passes them through.
- `meister_guide/overlay/window.py` — per-game state in `_refresh_guides_status`/`_clear_game_guides`; `_start_ingest(game)` + `_on_counted`; any-game `_on_update_guides`.
- Tests updated/added across the matching `tests/` files.

**Note on state-table FK:** the new state tables use `game_id INTEGER PRIMARY KEY` (no `REFERENCES games(id)`). A foreign key would force every test and the migration to ensure a matching `games` row, and the table is only ever keyed by game internally. This is a deliberate, minor refinement of the spec (which wrote `REFERENCES games(id)`).

---

## Task 1: Per-game resume state (schema, migration, repos, callers, tests)

This task is atomic: changing the state model touches the schema, the repos, both
ingest orchestrators, and the window together, so the suite stays green only when
all land at once.

**Files:**
- Modify: `meister_guide/db/schema.py`
- Modify: `meister_guide/db/database.py`
- Modify: `meister_guide/db/articles.py`
- Modify: `meister_guide/db/redirects.py`
- Modify: `meister_guide/scraper/ingest.py`
- Modify: `meister_guide/scraper/redirect_ingest.py`
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_state_per_game.py` (new), and updates to
  `tests/test_articles_repo.py`, `tests/test_redirects.py`, `tests/test_ingest.py`,
  `tests/test_redirect_ingest.py`, `tests/test_window_manage.py`

- [ ] **Step 1: Write the new failing tests (per-game state + migration)**

Create `tests/test_state_per_game.py`:

```python
import sqlite3
from meister_guide.db.database import connect, init_db, migrate_game_ids
from meister_guide.db.articles import ScrapeStateRepo, ScrapeState
from meister_guide.db.redirects import RedirectStateRepo, RedirectState


def test_scrape_state_is_per_game(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    repo = ScrapeStateRepo(conn)
    repo.save(ScrapeState("tokA", 5, 100), game_id=1)
    repo.save(ScrapeState("tokB", 7, 200), game_id=2)
    assert repo.load(1) == ScrapeState("tokA", 5, 100)
    assert repo.load(2) == ScrapeState("tokB", 7, 200)
    assert repo.load(999) == ScrapeState(None, 0, None)   # unknown -> default


def test_redirect_state_is_per_game(tmp_path):
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    repo = RedirectStateRepo(conn)
    repo.save(RedirectState("tokA", 3), game_id=1)
    repo.save(RedirectState("tokB", 9), game_id=2)
    assert repo.load(1) == RedirectState("tokA", 3)
    assert repo.load(2) == RedirectState("tokB", 9)
    assert repo.load(7) == RedirectState(None, 0)


def _legacy_state_db(path):
    """A DB built with the OLD single-row state schema and a stored Minecraft row."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, "
                 "process_names TEXT, wiki_url TEXT)")
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (1,'Minecraft','[]')")
    conn.execute("CREATE TABLE scrape_state (id INTEGER PRIMARY KEY CHECK (id=1), "
                 "continue_token TEXT, done INTEGER NOT NULL DEFAULT 0, total INTEGER, "
                 "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO scrape_state (id, continue_token, done, total) "
                 "VALUES (1, 'RESUME', 9000, 16000)")
    conn.execute("CREATE TABLE redirect_state (id INTEGER PRIMARY KEY CHECK (id=1), "
                 "continue_token TEXT, done INTEGER NOT NULL DEFAULT 0, "
                 "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO redirect_state (id, continue_token, done) VALUES (1, 'RTOK', 12)")
    conn.commit()
    return conn


def test_migration_moves_legacy_state_to_minecraft(tmp_path):
    db = tmp_path / "legacy.db"
    conn = _legacy_state_db(db)
    migrate_game_ids(conn)                       # rebuilds state tables, keyed by game
    assert ScrapeStateRepo(conn).load(1) == ScrapeState("RESUME", 9000, 16000)
    assert RedirectStateRepo(conn).load(1) == RedirectState("RTOK", 12)
    # a second game can now keep its own state
    ScrapeStateRepo(conn).save(ScrapeState("X", 1, 2), game_id=2)
    assert ScrapeStateRepo(conn).load(2) == ScrapeState("X", 1, 2)


def test_migration_is_idempotent(tmp_path):
    conn = _legacy_state_db(tmp_path / "legacy2.db")
    migrate_game_ids(conn)
    migrate_game_ids(conn)                        # second run is a no-op
    assert ScrapeStateRepo(conn).load(1) == ScrapeState("RESUME", 9000, 16000)
```

(`ScrapeState`/`RedirectState` are `@dataclass`es, so `==` compares fields.)

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `py -m pytest tests/test_state_per_game.py -v`
Expected: FAIL (e.g. `TypeError: load() takes 1 positional argument but 2 were given`, or migration not rebuilding).

- [ ] **Step 3: Make the state-table DDL game-keyed (`db/schema.py`)**

In `meister_guide/db/schema.py`, define named DDL constants and use them in the
table lists (so the migration can reuse them). Replace the inline `scrape_state`
string in `PHASE3_TABLES` and the `redirect_state` string in `PHASE6_TABLES`:

```python
SCRAPE_STATE_DDL = """
CREATE TABLE IF NOT EXISTS scrape_state (
    game_id INTEGER PRIMARY KEY,
    continue_token TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

REDIRECT_STATE_DDL = """
CREATE TABLE IF NOT EXISTS redirect_state (
    game_id INTEGER PRIMARY KEY,
    continue_token TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""
```

Use `SCRAPE_STATE_DDL` in place of the old `scrape_state` entry in `PHASE3_TABLES`,
and `REDIRECT_STATE_DDL` in place of the old `redirect_state` entry in
`PHASE6_TABLES`. (Keep all other table entries unchanged.)

- [ ] **Step 4: Rebuild legacy state tables in the migration (`db/database.py`)**

In `meister_guide/db/database.py`, import the DDL and add the rebuild helper, then
call it from `migrate_game_ids` before its `conn.commit()`:

```python
from meister_guide.db.schema import (CORE_TABLES, PHASE3_TABLES, PHASE6_TABLES,
                                      SCRAPE_STATE_DDL, REDIRECT_STATE_DDL)


def _rebuild_state_table_if_legacy(conn, table, create_sql, cols, mc_id):
    """Old state tables were single-row (CHECK id=1). Rebuild to the game-keyed
    schema, moving the existing row to Minecraft. No-op once game_id exists."""
    existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if "game_id" in existing:
        return
    conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
    conn.execute(create_sql)
    conn.execute(
        f"INSERT INTO {table} (game_id, {cols}) "
        f"SELECT ?, {cols} FROM {table}_legacy WHERE id = 1",
        (mc_id,),
    )
    conn.execute(f"DROP TABLE {table}_legacy")
```

Then in `migrate_game_ids`, after the two existing `UPDATE … SET game_id` lines and
before `conn.commit()`, add:

```python
    _rebuild_state_table_if_legacy(conn, "scrape_state", SCRAPE_STATE_DDL,
                                   "continue_token, done, total, updated_at", mc_id)
    _rebuild_state_table_if_legacy(conn, "redirect_state", REDIRECT_STATE_DDL,
                                   "continue_token, done, updated_at", mc_id)
```

(Adjust the existing `from meister_guide.db.schema import …` line to the new import
shown above.)

- [ ] **Step 5: Make `ScrapeStateRepo` game-keyed (`db/articles.py`)**

Replace the `load`/`save` bodies (the class docstring's "single-row" wording too):

```python
class ScrapeStateRepo:
    """Per-game ingest progress (keyed by game_id) so an interrupted download
    resumes."""

    def __init__(self, conn):
        self._conn = conn

    def load(self, game_id) -> ScrapeState:
        row = self._conn.execute(
            "SELECT continue_token, done, total FROM scrape_state WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return ScrapeState(None, 0, None)
        return ScrapeState(row[0], row[1], row[2])

    def save(self, state: ScrapeState, game_id, commit=True) -> None:
        self._conn.execute(
            "INSERT INTO scrape_state (game_id, continue_token, done, total, updated_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(game_id) DO UPDATE SET "
            "continue_token=excluded.continue_token, done=excluded.done, "
            "total=excluded.total, updated_at=CURRENT_TIMESTAMP",
            (game_id, state.continue_token, state.done, state.total),
        )
        if commit:
            self._conn.commit()
```

- [ ] **Step 6: Make `RedirectStateRepo` game-keyed (`db/redirects.py`)**

```python
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
```

- [ ] **Step 7: Thread `game_id` through `run_ingest` (`scraper/ingest.py`)**

Update the state calls and restart count in `run_ingest` (leave `_ingest_from`'s
signature; it already receives `game_id` and calls `state_repo.save(..., game_id)`
— update that save in this step too):

```python
def run_ingest(client, articles_repo, state_repo, conn,
               progress_cb=None, should_cancel=None, game_id=None):
    total = state_repo.load(game_id).total
    if total is None:
        try:
            total = client.article_count()
        except Exception:
            total = None

    saved = state_repo.load(game_id)
    try:
        _ingest_from(saved.continue_token, saved.done,
                     client, articles_repo, state_repo, conn, total,
                     progress_cb, should_cancel, game_id)
    except InvalidContinueError:
        restart_done = articles_repo.count(game_id=game_id)
        state_repo.save(ScrapeState(None, restart_done, total), game_id)
        _ingest_from(None, restart_done, client, articles_repo, state_repo,
                     conn, total, progress_cb, should_cancel, game_id)
```

In `_ingest_from`, change the two `state_repo.save(...)` calls to pass `game_id`:
`state_repo.save(ScrapeState(next_token, done, total), game_id, commit=False)` and
the final `state_repo.save(ScrapeState(None, done, total), game_id)`.

- [ ] **Step 8: Thread `game_id` through `run_redirect_ingest` (`scraper/redirect_ingest.py`)**

```python
def run_redirect_ingest(client, redirects_repo, articles_repo, state_repo, conn,
                        progress_cb=None, should_cancel=None, game_id=None):
    st = state_repo.load(game_id)
    try:
        _walk(st.continue_token, st.done, client, redirects_repo, articles_repo,
              state_repo, conn, progress_cb, should_cancel, game_id)
    except InvalidContinueError:
        restart_done = redirects_repo.count_by_game(game_id)
        state_repo.save(RedirectState(None, restart_done), game_id)
        _walk(None, restart_done, client, redirects_repo, articles_repo,
              state_repo, conn, progress_cb, should_cancel, game_id)
```

In `_walk`, change the two `state_repo.save(...)` calls to pass `game_id`:
`state_repo.save(RedirectState(next_token, done), game_id, commit=False)` and the
final `state_repo.save(RedirectState(None, done), game_id)`.

- [ ] **Step 9: Update the window's state calls (`overlay/window.py`)**

In `_refresh_guides_status`, the state loads use the picked game (the resume status
now applies to every game, so drop the Minecraft-only special-case). Replace the
body that computes `articles_done`/`redirects_done`:

```python
        game = self._guides_target_game()
        gid = game.id if game is not None else None
        n = self._articles_repo.count(game_id=gid)
        articles_done = True
        redirects_done = True
        if gid is not None and self._scrape_state_repo is not None:
            articles_done = (self._scrape_state_repo.load(gid).continue_token is None
                             and n > 0)
        if gid is not None and self._redirect_state_repo is not None:
            rs = self._redirect_state_repo.load(gid)
            redirects_done = rs.continue_token is None and rs.done > 0
        self.guides_status.setText(
            guides_status_text(n, articles_done, redirects_done)
        )
```

In `_clear_game_guides`, reset that game's state (any game now, not just Minecraft):

```python
    def _clear_game_guides(self, game):
        """Delete a game's stored articles + redirect aliases and reset its
        per-game scrape/redirect resume state. Returns the article count deleted."""
        n = self._articles_repo.delete_by_game(game.id) if self._articles_repo else 0
        if self._redirects_repo is not None:
            self._redirects_repo.delete_by_game(game.id)
        if self._scrape_state_repo is not None:
            self._scrape_state_repo.save(ScrapeState(None, 0, None), game.id)
        if self._redirect_state_repo is not None:
            self._redirect_state_repo.save(RedirectState(None, 0), game.id)
        return n
```

- [ ] **Step 10: Update existing tests for the new `game_id` argument**

`tests/test_articles_repo.py` — in `test_scrape_state_defaults_then_persists`, pass
a `game_id` (use `1`) to every `repo.load(...)` / `repo.save(...)`:
```python
def test_scrape_state_defaults_then_persists(tmp_path):
    from meister_guide.db.articles import ScrapeStateRepo, ScrapeState
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    repo = ScrapeStateRepo(conn)
    assert repo.load(1) == ScrapeState(None, 0, None)
    repo.save(ScrapeState(continue_token='{"gapcontinue":"Boat"}', done=40, total=16689), 1)
    assert repo.load(1).done == 40
    repo.save(ScrapeState(continue_token=None, done=16689, total=16689), 1)
    assert repo.load(1).continue_token is None
```
(Match the surrounding style of the existing test; keep its `connect`/`init_db`
setup. Adjust the existing assertions to use `repo.load(1)`.)

`tests/test_redirects.py` — in `test_redirect_state_defaults_then_persists`, pass
`game_id` (use `1`):
```python
def test_redirect_state_defaults_then_persists(tmp_path):
    repo = RedirectStateRepo(_conn(tmp_path))
    assert repo.load(1) == RedirectState(None, 0)
    repo.save(RedirectState(continue_token='{"apcontinue":"Boat"}', done=12), 1)
    assert repo.load(1).done == 12
    repo.save(RedirectState(continue_token=None, done=50), 1)
    assert repo.load(1).continue_token is None
```

`tests/test_ingest.py` — make state usable per-game: in `_setup` insert a games row
so `game_id=1` is valid for the articles FK, and pass `game_id=1` everywhere. Change
`_setup` to:
```python
def _setup(tmp_path):
    conn = connect(tmp_path / "i.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (1,'T','[]')")
    conn.commit()
    return conn, ArticlesRepo(conn), ScrapeStateRepo(conn)
```
Then in each test, pass `game_id=1` to `run_ingest(...)` and to every `state.save(...)`
/ `state.load(...)`:
- `test_run_ingest_populates_db_and_reports_progress`: `run_ingest(FakeClient(batches), arts, state, conn, progress_cb=..., game_id=1)`; `state.load(1).continue_token is None`.
- `test_run_ingest_skips_noise_pages`: `run_ingest(FakeClient(batches), arts, state, conn, game_id=1)` (counts use `arts.count()` unchanged).
- `test_run_ingest_resumes_from_saved_token`: `state.save(ScrapeState("tok1", 2, 3), 1)`; `run_ingest(client, arts, state, conn, game_id=1)`.
- `test_run_ingest_stops_when_cancelled`: `run_ingest(..., should_cancel=lambda: True, game_id=1)`; `state.load(1).continue_token is None`.
- `test_run_ingest_recovers_from_stale_continue_token`: `state.save(ScrapeState("STALE", 7, 2), 1)`; `run_ingest(client, arts, state, conn, game_id=1)`; `state.load(1).continue_token is None`.
- `test_run_ingest_tags_articles_with_game_id`: already inserts game 42; pass `game_id=42` (unchanged) — but ensure `state.save`/`load` aren't called with a bare arg here (it isn't).

`tests/test_redirect_ingest.py` — in `_setup` insert a games row and pass `game_id=1`:
```python
def _setup(tmp_path):
    conn = connect(tmp_path / "ri.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (1,'T','[]')")
    conn.commit()
    return conn, ArticlesRepo(conn), RedirectsRepo(conn), RedirectStateRepo(conn)
```
Then pass `game_id=1` to each `run_redirect_ingest(...)` and `state.save(...)`/`state.load(...)`:
- `test_stores_aliases_only_for_known_target_articles`: `run_redirect_ingest(..., progress_cb=..., game_id=1)`; `state.load(1).continue_token is None`. (add_article/add_redirect without game_id store NULL; targets resolve by title regardless — assertions on `reds.count()` are unchanged.)
- `test_resumes_from_saved_token`: `state.save(RedirectState("tok1", 5), 1)`; `run_redirect_ingest(client, reds, arts, state, conn, game_id=1)`.
- `test_stops_when_cancelled`: `run_redirect_ingest(..., should_cancel=lambda: True, game_id=1)`.
- `test_recovers_from_stale_continue_token`: `state.save(RedirectState("STALE", 3), 1)`; `run_redirect_ingest(client, reds, arts, state, conn, game_id=1)`; `state.load(1).continue_token is None`.

`tests/test_window_manage.py` — in `test_clear_minecraft_resets_scrape_state`, pass
`mc.id`:
```python
def test_clear_minecraft_resets_scrape_state(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    w._scrape_state_repo.save(ScrapeState("token", 17915, 16689), mc.id)
    _pick(w, mc.id)
    w._confirm = lambda *a: True
    w._on_clear_guides()
    st = w._scrape_state_repo.load(mc.id)
    assert st.continue_token is None and st.done == 0
```

- [ ] **Step 11: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS (the new `tests/test_state_per_game.py` plus all updated tests; no
remaining `load()`/`save()` calls without `game_id`).

- [ ] **Step 12: Commit**

```bash
git add meister_guide/db/schema.py meister_guide/db/database.py meister_guide/db/articles.py meister_guide/db/redirects.py meister_guide/scraper/ingest.py meister_guide/scraper/redirect_ingest.py meister_guide/overlay/window.py tests/test_state_per_game.py tests/test_articles_repo.py tests/test_redirects.py tests/test_ingest.py tests/test_redirect_ingest.py tests/test_window_manage.py
git commit -m "feat: per-game scrape/redirect resume state (schema, migration, repos)"
```

---

## Task 2: Generalize the ingest to any wiki (URL base, total override, worker)

**Files:**
- Modify: `meister_guide/scraper/ingest.py`
- Modify: `meister_guide/scraper/worker.py`
- Test: `tests/test_ingest.py`, `tests/test_ingest_worker.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ingest.py`:

```python
def test_run_ingest_builds_urls_from_base(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [([WikiArticle(1, "Reaper Leviathan", "big", 1)], None)]
    run_ingest(FakeClient(batches), arts, state, conn, game_id=1,
               base="https://subnautica.fandom.com")
    url = conn.execute("SELECT url FROM articles WHERE pageid=1").fetchone()[0]
    assert url == "https://subnautica.fandom.com/wiki/Reaper_Leviathan"


def test_run_ingest_uses_total_override_without_calling_count(tmp_path):
    conn, arts, state = _setup(tmp_path)
    class NoCountClient(FakeClient):
        def article_count(self):
            raise AssertionError("article_count must not be called when total is given")
    seen = []
    run_ingest(NoCountClient([([WikiArticle(1, "A", "a", 1)], None)]),
               arts, state, conn, game_id=1, total=42,
               progress_cb=lambda d, t: seen.append((d, t)))
    assert seen[-1][1] == 42        # reported total is the override
```

Append to `tests/test_ingest_worker.py`:

```python
def test_worker_uses_api_url_and_emits_counted(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "c.db"
    # games row so the worker's game_id has a valid FK target for articles
    conn = connect(db); init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (5,'G','[]')")
    conn.commit(); conn.close()

    client = FakeClient([([WikiArticle(1, "A", "a", 1)], None)])
    worker = IngestWorker(str(db), game_id=5, api_url="https://x/api.php",
                          page_url_base="https://x", client=client)
    counted, finished = [], []
    worker.counted.connect(lambda n: counted.append(n))
    worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert counted == [2]          # FakeClient.article_count() == 2
    assert finished == [True]
    conn = connect(db); init_db(conn)
    url = conn.execute("SELECT url FROM articles WHERE pageid=1").fetchone()[0]
    assert url == "https://x/wiki/A"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `py -m pytest tests/test_ingest.py::test_run_ingest_builds_urls_from_base tests/test_ingest_worker.py::test_worker_uses_api_url_and_emits_counted -v`
Expected: FAIL (`run_ingest` has no `base`/`total`; `IngestWorker` has no `api_url`/`counted`).

- [ ] **Step 3: Add `base`/`total` to `run_ingest` and build URLs from base (`scraper/ingest.py`)**

Replace the module-level `_url_for` and `run_ingest` signature/total logic:

```python
from meister_guide.scraper.urls import page_url


def run_ingest(client, articles_repo, state_repo, conn,
               progress_cb=None, should_cancel=None, game_id=None,
               base="", total=None):
    saved = state_repo.load(game_id)
    if saved.total is not None:
        total = saved.total
    elif total is None:
        try:
            total = client.article_count()
        except Exception:
            total = None
    try:
        _ingest_from(saved.continue_token, saved.done,
                     client, articles_repo, state_repo, conn, total,
                     progress_cb, should_cancel, game_id, base)
    except InvalidContinueError:
        restart_done = articles_repo.count(game_id=game_id)
        state_repo.save(ScrapeState(None, restart_done, total), game_id)
        _ingest_from(None, restart_done, client, articles_repo, state_repo,
                     conn, total, progress_cb, should_cancel, game_id, base)
```

Update `_ingest_from` to take `base` and use `page_url` for the URL:

```python
def _ingest_from(token, done, client, articles_repo, state_repo, conn, total,
                 progress_cb, should_cancel, game_id=None, base=""):
    for articles, next_token in client.iter_batches(start_token=token):
        if should_cancel and should_cancel():
            return
        for art in articles:
            if is_noise(art.title):
                continue
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, page_url(base, art.title),
                                         game_id=game_id, commit=False):
                done += 1
        state_repo.save(ScrapeState(next_token, done, total), game_id, commit=False)
        conn.commit()
        if progress_cb:
            progress_cb(done, total)

    state_repo.save(ScrapeState(None, done, total), game_id)
```

Delete the old `_url_for` function (no longer used).

- [ ] **Step 4: Generalize `IngestWorker` (`scraper/worker.py`)**

Update the import and the `IngestWorker` class. Add `counted` signal, `api_url` /
`page_url_base` params, build the client from `api_url`, emit the page count, and
pass `base`/`total` through. Replace the existing `IngestWorker`:

```python
class IngestWorker(QObject):
    progress = Signal(int, int)   # done, total (total may be 0 if unknown)
    counted = Signal(int)         # wiki page count, emitted before the walk
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_path, game_id=None, api_url=None, page_url_base="",
                 client=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._api_url = api_url
        self._page_url_base = page_url_base
        self._client = client
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        conn = None
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient(api_url=self._api_url) \
                if self._api_url else (self._client or WikiClient())
            articles_repo = ArticlesRepo(conn)
            articles_repo.prune_noise(is_noise)
            total = None
            try:
                total = client.article_count()
            except Exception:
                total = None
            self.counted.emit(total or 0)
            run_ingest(
                client, articles_repo, ScrapeStateRepo(conn), conn,
                progress_cb=lambda d, t: self.progress.emit(d, t or 0),
                should_cancel=lambda: self._cancel,
                game_id=self._game_id, base=self._page_url_base, total=total,
            )
            if self._cancel:
                return
            run_redirect_ingest(
                client, RedirectsRepo(conn), articles_repo,
                RedirectStateRepo(conn), conn,
                progress_cb=lambda d: self.progress.emit(d, 0),
                should_cancel=lambda: self._cancel,
                game_id=self._game_id,
            )
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit()
```

Note the client construction: `WikiClient(api_url=self._api_url)` when an
`api_url` is set, else the default-API `WikiClient()` (preserves Minecraft
behavior), and an injected `client` always wins. Write it clearly:

```python
            if self._client is not None:
                client = self._client
            elif self._api_url:
                client = WikiClient(api_url=self._api_url)
            else:
                client = WikiClient()
```

(Use this clear form in place of the one-liner above.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -m pytest tests/test_ingest.py tests/test_ingest_worker.py -q`
Expected: PASS (existing worker tests still pass: `game_id` defaults to None, but
those DBs store NULL article game_ids — FK-safe — and `counted` is simply ignored).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/scraper/ingest.py meister_guide/scraper/worker.py tests/test_ingest.py tests/test_ingest_worker.py
git commit -m "feat: ingest any wiki via api_url + page base; emit page-count estimate"
```

---

## Task 3: Window — full download for any game with a wiki URL

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_window_guides.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_window_guides.py`:

```python
def test_update_starts_for_any_game_with_wiki_url():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(),
                      ":memory:")
    started = []
    w._start_ingest = lambda game: started.append(game)
    w.guides_game.setCurrentIndex(w.guides_game.findText("Subnautica"))
    w._on_update_guides()
    assert len(started) == 1 and started[0].name == "Subnautica"


def test_update_refuses_game_without_wiki_url():
    QApplication.instance() or QApplication([])
    games = [Game(id=1, name="Minecraft", process_names=[], wiki_url="https://minecraft.wiki"),
             Game(id=3, name="NoWiki", process_names=[], wiki_url=None)]
    w = OverlayWindow(QSettings("MeisterGuide", "T"), games, StubRepo(), ":memory:")
    started = []
    w._start_ingest = lambda game: started.append(game)
    w.guides_game.setCurrentIndex(w.guides_game.findText("NoWiki"))
    w._on_update_guides()
    assert started == []
    assert "wiki URL" in w.guides_status.text()


def test_counted_handler_shows_estimate():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(),
                      ":memory:")
    w.guides_game.setCurrentIndex(w.guides_game.findText("Subnautica"))
    w._on_ingest_counted(6200)
    assert "6,200 pages" in w.guides_status.text()
    assert "Subnautica" in w.guides_status.text()
    w._on_ingest_counted(140000)
    assert "while" in w.guides_status.text().lower()   # large-wiki note
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `py -m pytest tests/test_window_guides.py -q`
Expected: FAIL (`_start_ingest` not used by `_on_update_guides`; `_on_ingest_counted`
not defined; non-Minecraft is currently refused).

- [ ] **Step 3: Rework `_on_update_guides` + add `_start_ingest` and `_on_ingest_counted` (`overlay/window.py`)**

Replace the current `_on_update_guides` (the version that gates on
`game.name != "Minecraft"`) and the body that creates the thread. New code:

```python
    def _on_update_guides(self):
        if self._db_path is None or self._ingest_thread is not None:
            return
        game = self._guides_target_game()
        if game is None:
            return
        if not game.wiki_url:
            self.guides_status.setText(
                "This game has no wiki URL yet. Add one in Settings first.")
            return
        self._start_ingest(game)

    def _start_ingest(self, game):
        from meister_guide.db.games import api_url_for
        self.guides_update_btn.setEnabled(False)
        self.guides_progress.setVisible(True)
        self.guides_progress.setRange(0, 0)
        self.guides_status.setText("Starting…")
        self._last_progress_done = None
        self._ingest_thread = QThread(self)
        self._ingest_worker = IngestWorker(
            str(self._db_path), game_id=game.id,
            api_url=api_url_for(game.wiki_url), page_url_base=game.wiki_url)
        self._ingest_worker.moveToThread(self._ingest_thread)
        self._ingest_thread.started.connect(self._ingest_worker.run)
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.counted.connect(self._on_ingest_counted)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_thread.start()

    def _on_ingest_counted(self, total):
        game = self._guides_target_game()
        name = game.name if game is not None else "This game"
        if total > 0:
            msg = f"{name} wiki has ~{total:,} pages. Downloading…"
            if total > 25000:
                msg += " This will take a while."
        else:
            msg = f"Downloading {name} guides…"
        self.guides_status.setText(msg)
```

Confirm `api_url_for` is imported where used (the local import above keeps it
self-contained; if `api_url_for` is already imported at module top, drop the local
import and use it directly).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_window_guides.py -q`
Expected: PASS (all guides-tab tests, including the earlier picker tests).

- [ ] **Step 5: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS (full suite green).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_guides.py
git commit -m "feat: full wiki download for any game with a wiki URL + size estimate"
```

---

## Self-review notes

- **Spec coverage:** schema+migration (Task 1, steps 3–4) ✓; per-game state repos (Task 1, steps 5–6) ✓; orchestrators thread game_id + base + total (Task 1 steps 7–8, Task 2 step 3) ✓; worker api_url/page_url_base/counted (Task 2 step 4) ✓; window any-game + counted + per-game status/clear (Task 1 step 9, Task 3 step 3) ✓; size estimate with large-wiki note (Task 3) ✓; tests incl. legacy-schema migration test (Task 1 step 1) ✓.
- **Type/name consistency:** `load(game_id)` / `save(state, game_id, commit=True)` used identically in repos, orchestrators, window, and tests; `IngestWorker(..., api_url=, page_url_base=)` and the `counted(int)` signal / `_on_ingest_counted` handler match across worker, window, and tests; `page_url(base, title)` is the single URL builder.
- **Migration safety:** rebuild is guarded by the absence of a `game_id` column and is idempotent (tested); it runs in `migrate_game_ids` (after games are seeded) so Minecraft's id is available.
- **No placeholders:** every code/test/command step is concrete.
- **Note:** state tables use `game_id INTEGER PRIMARY KEY` without a `REFERENCES games(id)` FK (documented above) to keep state keying simple and tests free of mandatory games rows.
