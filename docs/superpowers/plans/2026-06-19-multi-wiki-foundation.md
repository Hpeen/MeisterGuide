# SP1 — Multi-Wiki Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Partition the corpus and retrieval per game/wiki — add `game_id` to `articles`/`redirects` (migrating the existing Minecraft corpus), scope chat retrieval to the active game, and add an "add a game" UI — as the foundation for on-demand multi-wiki support.

**Architecture:** A guarded, idempotent startup migration adds `game_id` (schema in `init_db`, backfill after games are seeded). Writes carry `game_id`; `search_ranked`/`count` filter by it; the Minecraft bulk ingest passes Minecraft's id. A Settings-tab form adds games via the existing `GamesRepo`. On-demand fetch (SP2) and per-game bulk (SP3) are out of scope.

**Tech Stack:** Python 3.12, SQLite + FTS5 (contentless), PySide6, pytest. Tests: `py -m pytest -q`.

**Spec:** `docs/superpowers/specs/2026-06-19-multi-wiki-foundation-design.md`

**Branch:** `multi-wiki-foundation` (checked out; spec already committed).

**Back-compat convention used throughout:** new `game_id` parameters are added as the
LAST argument with a default (`None`), so existing positional call sites and tests
keep working. `game_id=None` in `search_ranked`/`count` means "unscoped (all games)".
The Minecraft bulk ingest passes a real id; pre-existing rows are backfilled at startup.

---

## File map
- `meister_guide/db/schema.py` — `game_id` in the `articles` + `redirects` CREATE TABLEs.
- `meister_guide/db/database.py` — `init_db` adds the column to existing DBs (guarded ALTER); new `migrate_game_ids(conn)` backfills to Minecraft.
- `meister_guide/db/articles.py` — `add_article(game_id=None)`, `count(game_id=None)`, `search_ranked(..., game_id=None)`.
- `meister_guide/db/redirects.py` — `add_redirect(game_id=None)`.
- `meister_guide/db/games.py` — `api_url` helper (`api_url_for(wiki_url)`).
- `meister_guide/scraper/ingest.py`, `redirect_ingest.py`, `worker.py` — thread `game_id` through; `IngestWorker(db_path, game_id, …)`.
- `meister_guide/overlay/window.py` — pass active game id to `search_ranked`; resolve Minecraft id for ingest; scope Guides count/status; disable Update-guides for non-Minecraft; add-game form.
- `meister_guide/main.py` — call `migrate_game_ids` after `seed_defaults`.
- Tests: `tests/test_database.py`, `test_articles_repo.py`, `test_redirects*`, `test_games_repo.py`, `test_ingest.py`.

---

## Task 1: Schema — `game_id` columns + guarded migration

**Files:** Modify `meister_guide/db/schema.py`, `meister_guide/db/database.py`; Test `tests/test_database.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_database.py`:

```python
def test_init_db_adds_game_id_to_existing_old_shape_db(tmp_path):
    import sqlite3
    from meister_guide.db.database import connect, init_db
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    # Simulate a pre-migration DB: articles/redirects WITHOUT game_id.
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, pageid INTEGER "
                 "UNIQUE NOT NULL, title TEXT NOT NULL, body_zlib BLOB NOT NULL, "
                 "revid INTEGER, url TEXT)")
    conn.execute("CREATE TABLE redirects (id INTEGER PRIMARY KEY, title TEXT "
                 "UNIQUE NOT NULL, target_pageid INTEGER NOT NULL)")
    conn.commit(); conn.close()

    conn = connect(path)
    init_db(conn)                      # must ALTER in the missing column
    cols_a = [r[1] for r in conn.execute("PRAGMA table_info(articles)")]
    cols_r = [r[1] for r in conn.execute("PRAGMA table_info(redirects)")]
    assert "game_id" in cols_a
    assert "game_id" in cols_r
    init_db(conn)                      # idempotent: re-run must not raise
```

- [ ] **Step 2: Run — expect FAIL** (`game_id` absent): `py -m pytest tests/test_database.py::test_init_db_adds_game_id_to_existing_old_shape_db -v`

- [ ] **Step 3: Implement.** In `schema.py`, add `game_id INTEGER REFERENCES games(id)` to the `articles` CREATE (in `PHASE3_TABLES`) and the `redirects` CREATE (in `PHASE6_TABLES`). Example for articles:

```python
    """
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY,
        pageid INTEGER UNIQUE NOT NULL,
        title TEXT NOT NULL,
        body_zlib BLOB NOT NULL,
        revid INTEGER,
        url TEXT,
        game_id INTEGER REFERENCES games(id)
    )
    """,
```

(redirects similarly: add `, game_id INTEGER REFERENCES games(id)` before the closing `)`.)

In `database.py`, add a guarded column-adder and call it from `init_db` after the CREATE statements:

```python
def _ensure_column(conn, table, column, decl):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db(conn: sqlite3.Connection) -> None:
    """Create the core + Phase 3 + Phase 6 tables if they don't exist, then add
    any columns missing from an older DB. Idempotent."""
    for statement in CORE_TABLES + PHASE3_TABLES + PHASE6_TABLES:
        conn.execute(statement)
    # Migrations for DBs created before a column existed (CREATE IF NOT EXISTS
    # won't add columns to an existing table).
    _ensure_column(conn, "articles", "game_id", "INTEGER REFERENCES games(id)")
    _ensure_column(conn, "redirects", "game_id", "INTEGER REFERENCES games(id)")
    conn.commit()
```

- [ ] **Step 4: Run — expect PASS** (that test) then full suite `py -m pytest -q` (must stay green; existing DB tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/schema.py meister_guide/db/database.py tests/test_database.py
git commit -m "feat: add game_id columns + guarded migration to init_db"
```

---

## Task 2: Backfill existing rows to Minecraft (`migrate_game_ids`)

**Files:** Modify `meister_guide/db/database.py`, `meister_guide/main.py`; Test `tests/test_database.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_database.py`:

```python
def test_migrate_game_ids_backfills_null_rows_to_minecraft(tmp_path):
    import zlib
    from meister_guide.db.database import connect, init_db, migrate_game_ids
    from meister_guide.db.games import GamesRepo
    conn = connect(tmp_path / "m.db"); init_db(conn)
    games = GamesRepo(conn); games.seed_defaults()
    mc = next(g for g in games.list_games() if g.name == "Minecraft")
    # Insert rows with NULL game_id (pre-migration shape) + one already-set row.
    conn.execute("INSERT INTO articles (pageid, title, body_zlib, game_id) "
                 "VALUES (1, 'A', ?, NULL)", (zlib.compress(b'x'),))
    conn.execute("INSERT INTO articles (pageid, title, body_zlib, game_id) "
                 "VALUES (2, 'B', ?, 999)", (zlib.compress(b'y'),))
    conn.execute("INSERT INTO redirects (title, target_pageid, game_id) "
                 "VALUES ('R', 1, NULL)")
    conn.commit()

    migrate_game_ids(conn)

    rows = dict(conn.execute("SELECT pageid, game_id FROM articles"))
    assert rows[1] == mc.id          # NULL backfilled to Minecraft
    assert rows[2] == 999            # already-set row untouched
    assert conn.execute("SELECT game_id FROM redirects WHERE title='R'").fetchone()[0] == mc.id
    migrate_game_ids(conn)           # idempotent: no error, no change
    assert dict(conn.execute("SELECT pageid, game_id FROM articles"))[1] == mc.id
```

- [ ] **Step 2: Run — expect FAIL** (`migrate_game_ids` undefined).

- [ ] **Step 3: Implement** in `database.py`:

```python
def migrate_game_ids(conn: sqlite3.Connection) -> None:
    """Backfill NULL game_id rows to the seeded Minecraft game. Runs AFTER games
    are seeded (needs Minecraft's id). Idempotent — only touches NULL rows."""
    row = conn.execute("SELECT id FROM games WHERE name = 'Minecraft' "
                       "ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return
    mc_id = row[0]
    conn.execute("UPDATE articles SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    conn.execute("UPDATE redirects SET game_id = ? WHERE game_id IS NULL", (mc_id,))
    conn.commit()
```

In `main.py`, after `games_repo.seed_defaults()` and `games_repo.reconcile_builtin_games()`, add:

```python
    from meister_guide.db.database import migrate_game_ids  # or top-level import
    migrate_game_ids(conn)
```

(Prefer adding `migrate_game_ids` to the existing `from meister_guide.db.database import ...` line at the top of `main.py`.)

- [ ] **Step 4: Run — expect PASS** + full suite green.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/database.py meister_guide/main.py tests/test_database.py
git commit -m "feat: backfill existing corpus to Minecraft game_id after seeding"
```

---

## Task 3: Writes carry `game_id`

**Files:** Modify `meister_guide/db/articles.py`, `meister_guide/db/redirects.py`; Test `tests/test_articles_repo.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_articles_repo.py`:

```python
def test_add_article_stores_game_id(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "a creeper", 1, "u1", game_id=7)
    row = repo._conn.execute("SELECT game_id FROM articles WHERE pageid=1").fetchone()
    assert row[0] == 7
```

- [ ] **Step 2: Run — expect FAIL** (`add_article` has no `game_id` kwarg → TypeError).

- [ ] **Step 3: Implement.** In `articles.py`, change `add_article` signature to
`def add_article(self, pageid, title, text, revid, url, game_id=None, commit=True)` and
add `game_id` to the INSERT:

```python
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO articles "
            "(pageid, title, body_zlib, revid, url, game_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pageid, title, body, revid, url, game_id),
        )
```

(Leave the FTS insert unchanged.) In `redirects.py`, change `add_redirect` to
`def add_redirect(self, title, target_pageid, game_id=None, commit=True)` and add
`game_id` to its INSERT columns/values the same way.

- [ ] **Step 4: Run** the new test + full suite. Existing callers pass no `game_id` (defaults `None`) so they stay green.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py meister_guide/db/redirects.py tests/test_articles_repo.py
git commit -m "feat: add_article/add_redirect carry game_id"
```

---

## Task 4: Scope `search_ranked` + `count` by `game_id`

**Files:** Modify `meister_guide/db/articles.py`; Test `tests/test_articles_repo.py`.

- [ ] **Step 1: Failing tests** — add to `tests/test_articles_repo.py`:

```python
def test_search_ranked_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "A creeper explodes in Minecraft.", 1, "u1", game_id=1)
    repo.add_article(2, "Creeper", "A creeper plant grows in this other game.", 1, "u2", game_id=2)
    g1 = repo.search_ranked("creeper", limit=5, game_id=1)
    assert [h.pageid for h in g1] == [1]          # only game 1's article
    g2 = repo.search_ranked("creeper", limit=5, game_id=2)
    assert [h.pageid for h in g2] == [2]

def test_count_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "A", "x", 1, "u1", game_id=1)
    repo.add_article(2, "B", "y", 1, "u2", game_id=2)
    assert repo.count() == 2            # unscoped total
    assert repo.count(game_id=1) == 1
    assert repo.count(game_id=2) == 1
```

- [ ] **Step 2: Run — expect FAIL** (no `game_id` kwarg on either).

- [ ] **Step 3: Implement.**
`count`: `def count(self, game_id=None) -> int:` →

```python
    def count(self, game_id=None) -> int:
        if game_id is None:
            return self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM articles WHERE game_id = ?", (game_id,)
        ).fetchone()[0]
```

`search_ranked`: add `game_id=None` as the last param:
`def search_ranked(self, raw_query, limit=3, candidate_pool=15, game_id=None):`.
Inside, the two FTS lookups must join `articles` and filter by game when set. Replace
the article-pass query and the redirect-pass query with game-aware variants. For the
article pass:

```python
            if game_id is None:
                pass_rows = self._conn.execute(
                    "SELECT rowid, rank FROM articles_fts "
                    "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts, candidate_pool),
                ).fetchall()
            else:
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
```

For the redirect-alias pass, add the same `AND a.game_id = ?` to the existing
`JOIN articles a ON a.pageid = r.target_pageid` query (only when `game_id` is set):

```python
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
```

Read the current `search_ranked` first and adapt these into its existing two-pass
loop, preserving the coverage computation and `rerank(...)` call unchanged.

- [ ] **Step 4: Run** the new tests + full suite (existing `search_ranked` tests call without `game_id` → unscoped → still pass).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_repo.py
git commit -m "feat: scope search_ranked and count by game_id"
```

---

## Task 5: `api_url` helper

**Files:** Modify `meister_guide/db/games.py`; Test `tests/test_games_repo.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_games_repo.py`:

```python
def test_api_url_for_derives_mediawiki_endpoint():
    from meister_guide.db.games import api_url_for
    assert api_url_for("https://minecraft.wiki") == "https://minecraft.wiki/api.php"
    assert api_url_for("https://subnautica.fandom.com/") == "https://subnautica.fandom.com/api.php"
    assert api_url_for(None) is None
```

- [ ] **Step 2: Run — expect FAIL** (no `api_url_for`).

- [ ] **Step 3: Implement** in `games.py` (module-level):

```python
def api_url_for(wiki_url):
    """Derive a MediaWiki action-API endpoint from a wiki base URL. Works for
    minecraft.wiki and Fandom wikis. Returns None when no wiki_url is set.
    Consumed by SP2's on-demand fetcher."""
    if not wiki_url:
        return None
    return wiki_url.rstrip("/") + "/api.php"
```

- [ ] **Step 4: Run — expect PASS** + full suite.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/games.py tests/test_games_repo.py
git commit -m "feat: api_url_for helper (wiki base -> MediaWiki api.php)"
```

---

## Task 6: Thread Minecraft `game_id` through the bulk ingest

**Files:** Modify `meister_guide/scraper/ingest.py`, `meister_guide/scraper/redirect_ingest.py`, `meister_guide/scraper/worker.py`; Test `tests/test_ingest.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_ingest.py`:

```python
def test_run_ingest_tags_articles_with_game_id(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [([WikiArticle(1, "Creeper", "a creeper", 1)], None)]
    run_ingest(FakeClient(batches), arts, state, conn, game_id=42)
    assert conn.execute("SELECT game_id FROM articles WHERE pageid=1").fetchone()[0] == 42
```

- [ ] **Step 2: Run — expect FAIL** (`run_ingest` has no `game_id`).

- [ ] **Step 3: Implement.** Read `ingest.py` first. Add `game_id=None` to `run_ingest`
and `_ingest_from`, and pass it to `add_article`:

```python
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, _url_for(art.title),
                                         game_id=game_id, commit=False):
                done += 1
```

(Thread `game_id` from `run_ingest` into both `_ingest_from(...)` calls.)

In `redirect_ingest.py` (read it first), add `game_id=None` to `run_redirect_ingest`
and pass it to `add_redirect(...)`.

In `worker.py`, `IngestWorker.__init__(self, db_path, game_id=None, client=None)`; store
`self._game_id`; pass `game_id=self._game_id` to both `run_ingest(...)` and
`run_redirect_ingest(...)`.

- [ ] **Step 4: Run** the new test + full suite. (Existing `run_ingest` tests omit
`game_id` → defaults None → green.)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/ingest.py meister_guide/scraper/redirect_ingest.py meister_guide/scraper/worker.py tests/test_ingest.py
git commit -m "feat: thread game_id through bulk ingest workers"
```

---

## Task 7: Window wiring — scoped retrieval, scoped Guides, Minecraft ingest

**Files:** Modify `meister_guide/overlay/window.py`. (Qt wiring — verified by full suite + offscreen import; no new unit test required, but do not break existing tests.)

- [ ] **Step 1: Active-game id helper + scoped chat retrieval.** Add a small helper and
use it where `search_ranked` is called (the chat send path, ~line 357):

```python
    def _active_game_id(self):
        if self.active_game is not None:
            return self.active_game.id
        # Fall back to the seeded Minecraft game so retrieval still works before
        # detection sets an active game.
        for g in self._games:
            if g.name == "Minecraft":
                return g.id
        return None
```

Change the retrieval call to:

```python
            for hit in self._articles_repo.search_ranked(
                    question, limit=3, game_id=self._active_game_id()):
```

- [ ] **Step 2: Scope the Guides tab to the active game.** In `_refresh_guides_status`,
change `n = self._articles_repo.count()` to
`n = self._articles_repo.count(game_id=self._active_game_id())`.

- [ ] **Step 3: Pass Minecraft's id into the ingest + gate the button.** In
`_on_update_guides`, build the worker with the Minecraft game id and only run when the
active game is Minecraft (per spec §4):

```python
    def _on_update_guides(self):
        if self._db_path is None or self._ingest_thread is not None:
            return
        mc_id = next((g.id for g in self._games if g.name == "Minecraft"), None)
        # SP1: only Minecraft has a wired bulk corpus; other games fill on-demand (SP2).
        if self.active_game is not None and self.active_game.name != "Minecraft":
            self.guides_status.setText("On-demand updates for this game are coming soon")
            return
        self.guides_update_btn.setEnabled(False)
        self.guides_progress.setVisible(True)
        self.guides_progress.setRange(0, 0)
        self.guides_status.setText("Starting…")
        self._last_progress_done = None
        self._ingest_thread = QThread(self)
        self._ingest_worker = IngestWorker(str(self._db_path), game_id=mc_id)
        self._ingest_worker.moveToThread(self._ingest_thread)
        self._ingest_thread.started.connect(self._ingest_worker.run)
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_thread.start()
```

(Read the current `_on_update_guides` and preserve any lines not shown here.)

- [ ] **Step 4: Verify.** `py -m pytest -q` (green) and
`QT_QPA_PLATFORM=offscreen py -c "import meister_guide.overlay.window; print('ok')"`.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: scope chat retrieval + Guides tab to active game; tag Minecraft ingest"
```

---

## Task 8: Add-game UI (Settings tab form)

**Files:** Modify `meister_guide/overlay/window.py`. (Qt — verified by offscreen smoke.)

- [ ] **Step 1: Add the form to the Settings page.** In the method that builds the
Settings (⚙) tab, add a small "Add a game" group: three `QLineEdit`s (Name, Wiki URL,
Process names — comma-separated) and an "Add game" `QPushButton` wired to
`_on_add_game`. Store the line edits on `self` (e.g. `self.addgame_name`, etc.). Read
the existing Settings-tab builder first and follow its layout style.

- [ ] **Step 2: Implement the slot:**

```python
    def _on_add_game(self):
        if self._games_repo is None:
            return
        name = self.addgame_name.text().strip()
        wiki = self.addgame_wiki.text().strip() or None
        procs = [p.strip() for p in self.addgame_procs.text().split(",") if p.strip()]
        if not name:
            return
        self._games_repo.add(name, procs, wiki)
        self._games = self._games_repo.list_games()
        self._rebuild_game_menu()
        self.addgame_name.clear(); self.addgame_wiki.clear(); self.addgame_procs.clear()
```

> `OverlayWindow` must have access to a `GamesRepo`. If `self._games_repo` is not
> already passed in, add a `games_repo=None` kwarg to `__init__` (append at the end),
> store it, and pass `games_repo=games_repo` from `main.py`. `_rebuild_game_menu`
> already exists.

- [ ] **Step 3: Verify** with an offscreen smoke script: construct `OverlayWindow` with
an in-memory `GamesRepo`, call `_on_add_game` after setting the line-edit texts, assert
`games_repo.list_games()` now includes the new game. Run `py -m pytest -q` (green) and
the offscreen import.

```python
# /tmp smoke (offscreen): set QT_QPA_PLATFORM=offscreen, build QApplication,
# GamesRepo on :memory: (seed_defaults), construct OverlayWindow(games_repo=repo),
# set addgame_* texts, call _on_add_game(), assert the game was added.
```

- [ ] **Step 4: Commit**

```bash
git add meister_guide/overlay/window.py meister_guide/main.py
git commit -m "feat: add-game form on the Settings tab"
```

---

## Task 9: Integration verification

**Files:** none (verification only).

- [ ] **Step 1:** Full suite `py -m pytest -q` — all green (well above 179).
- [ ] **Step 2:** Offscreen app import: `QT_QPA_PLATFORM=offscreen py -c "import meister_guide.main; print('ok')"`.
- [ ] **Step 3 (migration on real data — recommended):** copy the live DB to a temp path, open it with `connect` + `init_db` + seed + `migrate_game_ids`, and assert every `articles.game_id` is the Minecraft id and counts are unchanged. Do NOT mutate the live DB itself.
- [ ] **Step 4:** Manual launch: add a game in Settings → it appears in the game-pill menu; switching to it shows an empty Guides count and disables Update-guides; Minecraft still answers and downloads.

---

## Self-review

**Spec coverage:** migration §1 → Tasks 1–2; writes carry game_id §2 → Task 3; retrieval scoping §3 → Task 4 (+ window wiring Task 7); Guides scoping + Update-guides gate §4 → Task 7; add-game UI + api_url §5 → Tasks 5, 8. Non-goals (SP2/SP3) untouched.

**Placeholder scan:** none — each step has concrete code or an exact command.

**Type/name consistency:** `game_id` is the last, defaulted param on `add_article`, `add_redirect`, `count`, `search_ranked`, `run_ingest`, `run_redirect_ingest`, `IngestWorker`. `migrate_game_ids(conn)` is defined in Task 2 and called in `main.py`. `api_url_for(wiki_url)` (Task 5). `_active_game_id()` (Task 7) used by retrieval + Guides count. `games_repo` kwarg threaded for Task 8.
