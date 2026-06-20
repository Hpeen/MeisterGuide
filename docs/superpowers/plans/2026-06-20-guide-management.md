# Downloaded-guide Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user see how many guides each game has stored and either clear a game's guides or remove the game entirely, from the ⚙ Settings tab.

**Architecture:** Two new per-game bulk-delete repo methods (mirroring `ArticlesRepo.prune_noise`'s per-row contentless-FTS delete), plus a "Manage guides" block on the Settings tab (game-picker combo + count label + Clear/Remove buttons) wired to them. Minecraft is protected from removal; clearing Minecraft also resets the single-row scrape/redirect state. Destructive ops go through a stubbable `_confirm` helper.

**Tech Stack:** Python, PySide6 (Qt), SQLite + FTS5, pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-guide-management-design.md`

**Test runner:** `py -m pytest -q` (use `py`, not `python`).

---

## File Structure

- **Modify** `meister_guide/db/articles.py` — `ArticlesRepo.delete_by_game`.
- **Modify** `meister_guide/db/redirects.py` — `RedirectsRepo.delete_by_game` + `count_by_game`.
- **Modify** `meister_guide/overlay/window.py` — Manage-guides UI, handlers, `redirects_repo` kwarg, imports.
- **Modify** `meister_guide/main.py` — build + inject `RedirectsRepo`.
- **Create** tests: `tests/test_articles_delete_by_game.py`, `tests/test_redirects_delete_by_game.py`, `tests/test_window_manage.py`.

---

## Task 1: `ArticlesRepo.delete_by_game`

**Files:**
- Modify: `meister_guide/db/articles.py`
- Test: `tests/test_articles_delete_by_game.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_articles_delete_by_game.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    for gid in (1, 2):
        conn.execute("INSERT INTO games (id, name, process_names) VALUES (?, ?, '[]')",
                     (gid, f"G{gid}"))
    conn.commit()
    return ArticlesRepo(conn)


def test_deletes_only_target_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "boom", 1, "u", game_id=1)
    repo.add_article(2, "Leviathan", "big", 2, "u", game_id=2)
    n = repo.delete_by_game(1)
    assert n == 1
    assert repo.count(game_id=1) == 0
    assert repo.count(game_id=2) == 1          # other game untouched


def test_fts_index_consistent_after_delete(tmp_path):
    repo = _repo(tmp_path)
    repo.add_article(1, "Creeper", "it explodes", 1, "u", game_id=1)
    repo.add_article(2, "Creeper", "it explodes", 2, "u", game_id=2)
    repo.delete_by_game(1)
    # game 1's row is gone from the index; game 2's identical-title row remains
    hits = repo.search_ranked("creeper", limit=5, game_id=1)
    assert hits == []
    assert any(h.title == "Creeper" for h in repo.search_ranked("creeper", limit=5, game_id=2))


def test_idempotent_when_empty(tmp_path):
    repo = _repo(tmp_path)
    assert repo.delete_by_game(1) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_articles_delete_by_game.py -q`
Expected: FAIL with `AttributeError: 'ArticlesRepo' object has no attribute 'delete_by_game'`.

- [ ] **Step 3: Implement**

In `meister_guide/db/articles.py`, add this method to `ArticlesRepo` (right after `prune_noise`):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_articles_delete_by_game.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_delete_by_game.py
git commit -m "feat: ArticlesRepo.delete_by_game (per-game bulk delete + FTS)"
```

---

## Task 2: `RedirectsRepo.delete_by_game` + `count_by_game`

**Files:**
- Modify: `meister_guide/db/redirects.py`
- Test: `tests/test_redirects_delete_by_game.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_redirects_delete_by_game.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.redirects import RedirectsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    for gid in (1, 2):
        conn.execute("INSERT INTO games (id, name, process_names) VALUES (?, ?, '[]')",
                     (gid, f"G{gid}"))
    conn.commit()
    return RedirectsRepo(conn)


def test_count_by_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.add_redirect("Doggo", 10, game_id=1)
    repo.add_redirect("Reaper", 20, game_id=2)
    assert repo.count_by_game(1) == 2
    assert repo.count_by_game(2) == 1


def test_deletes_only_target_game(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.add_redirect("Reaper", 20, game_id=2)
    n = repo.delete_by_game(1)
    assert n == 1
    assert repo.count_by_game(1) == 0
    assert repo.count_by_game(2) == 1


def test_fts_index_consistent_after_delete(tmp_path):
    repo = _repo(tmp_path)
    repo.add_redirect("Wolf", 10, game_id=1)
    repo.delete_by_game(1)
    rows = repo._conn.execute(
        "SELECT COUNT(*) FROM redirects_fts WHERE redirects_fts MATCH ?", ("Wolf",)
    ).fetchone()[0]
    assert rows == 0


def test_idempotent_when_empty(tmp_path):
    repo = _repo(tmp_path)
    assert repo.delete_by_game(1) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_redirects_delete_by_game.py -q`
Expected: FAIL with `AttributeError: 'RedirectsRepo' object has no attribute 'count_by_game'`.

- [ ] **Step 3: Implement**

In `meister_guide/db/redirects.py`, add these two methods to `RedirectsRepo` (right after `count`):

```python
    def count_by_game(self, game_id) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM redirects WHERE game_id = ?", (game_id,)
        ).fetchone()[0]

    def delete_by_game(self, game_id) -> int:
        """Delete all redirect aliases for one game plus their contentless-FTS
        rows; return the number deleted. Contentless FTS5 needs the original
        title supplied to delete an index row."""
        rows = self._conn.execute(
            "SELECT id, title FROM redirects WHERE game_id = ?", (game_id,)
        ).fetchall()
        for id_, title in rows:
            self._conn.execute(
                "INSERT INTO redirects_fts(redirects_fts, rowid, title) "
                "VALUES('delete', ?, ?)",
                (id_, title),
            )
            self._conn.execute("DELETE FROM redirects WHERE id = ?", (id_,))
        self._conn.commit()
        return len(rows)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_redirects_delete_by_game.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/redirects.py tests/test_redirects_delete_by_game.py
git commit -m "feat: RedirectsRepo.delete_by_game + count_by_game"
```

---

## Task 3: Manage-guides UI + wiring

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Modify: `meister_guide/main.py`
- Test: `tests/test_window_manage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_window_manage.py`:

```python
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo, ScrapeState
from meister_guide.db.redirects import RedirectsRepo, RedirectStateRepo
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
    games.seed_defaults()                      # Minecraft (id 1)
    sub = games.add("Subnautica", [], "https://subnautica.fandom.com")
    articles = ArticlesRepo(conn)
    mc = next(g for g in games.list_games() if g.name == "Minecraft")
    articles.add_article(1, "Creeper", "boom", 1, "u", game_id=mc.id)
    articles.add_article(2, "Leviathan", "big", 2, "u", game_id=sub.id)
    redirects = RedirectsRepo(conn)
    redirects.add_redirect("Reaper", 2, game_id=sub.id)
    w = OverlayWindow(QSettings("MeisterGuide", "Manage"),
                      games.list_games(), articles, str(db), None, OllamaStub(),
                      settings_repo=SettingsRepo(conn),
                      scrape_state_repo=ScrapeStateRepo(conn),
                      redirect_state_repo=RedirectStateRepo(conn),
                      games_repo=games, redirects_repo=redirects)
    return w, games, articles, mc, sub


def _pick(w, game_id):
    w.manage_game.setCurrentIndex(w.manage_game.findData(game_id))


def test_combo_lists_games_and_shows_count(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    assert "1 guides" in w.manage_count.text()
    assert "1 aliases" in w.manage_count.text()


def test_remove_disabled_for_minecraft_enabled_otherwise(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, mc.id)
    assert not w.manage_remove_btn.isEnabled()
    _pick(w, sub.id)
    assert w.manage_remove_btn.isEnabled()


def test_clear_deletes_guides(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    w._confirm = lambda *a: True
    w._on_clear_guides()
    assert articles.count(game_id=sub.id) == 0
    assert "Cleared 1 guides" in w.manage_status.text()


def test_clear_cancelled_keeps_guides(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    w._confirm = lambda *a: False
    w._on_clear_guides()
    assert articles.count(game_id=sub.id) == 1


def test_clear_minecraft_resets_scrape_state(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    w._scrape_state_repo.save(ScrapeState("token", 17915, 16689))
    _pick(w, mc.id)
    w._confirm = lambda *a: True
    w._on_clear_guides()
    st = w._scrape_state_repo.load()
    assert st.continue_token is None and st.done == 0


def test_remove_game_deletes_and_resets_active(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    w._set_active(next(g for g in w._games if g.id == sub.id), manual=True)
    _pick(w, sub.id)
    w._confirm = lambda *a: True
    w._on_remove_game()
    assert all(g.id != sub.id for g in games.list_games())   # game row gone
    assert articles.count(game_id=sub.id) == 0               # guides gone
    assert w.active_game is None                              # active reset


def test_remove_minecraft_is_noop(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, mc.id)
    w._confirm = lambda *a: True
    w._on_remove_game()
    assert any(g.id == mc.id for g in games.list_games())     # still there
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_window_manage.py -q`
Expected: FAIL — `TypeError` (unexpected `redirects_repo` kwarg) or `AttributeError` on `manage_game`.

- [ ] **Step 3: Add `QMessageBox` to the widget import + the state dataclass imports**

In `meister_guide/overlay/window.py`, change the `from PySide6.QtWidgets import (...)` block to include `QMessageBox`:

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox, QCheckBox, QMessageBox,
    QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QProgressBar, QSplitter,
)
```

Add these imports near the other `meister_guide.db` imports (e.g. just after the `from meister_guide.db.settings import ...` line):

```python
from meister_guide.db.articles import ScrapeState
from meister_guide.db.redirects import RedirectState
```

- [ ] **Step 4: Accept and store the `redirects_repo` kwarg**

In `OverlayWindow.__init__`, add `redirects_repo=None` to the signature (after `games_repo=None`):

```python
                 games_repo=None, redirects_repo=None):
```

And store it next to `self._games_repo = games_repo`:

```python
        self._redirects_repo = redirects_repo
```

- [ ] **Step 5: Build the Manage-guides UI block**

In `_build_settings_tab`, immediately AFTER the seed block's `self._refresh_seed_games()` line and BEFORE `col.addStretch(1)`, insert:

```python
        # --- manage guides ---
        col.addWidget(QLabel("<b>Manage guides</b>"))
        self.manage_game = QComboBox()
        self.manage_game.currentIndexChanged.connect(
            lambda _i: self._on_manage_pick())
        col.addWidget(self.manage_game)
        self.manage_count = QLabel("")
        self.manage_count.setObjectName("Disclaimer")
        col.addWidget(self.manage_count)
        manage_row = QHBoxLayout()
        self.manage_clear_btn = QPushButton("Clear guides")
        self.manage_clear_btn.clicked.connect(self._on_clear_guides)
        manage_row.addWidget(self.manage_clear_btn)
        self.manage_remove_btn = QPushButton("Remove game")
        self.manage_remove_btn.clicked.connect(self._on_remove_game)
        manage_row.addWidget(self.manage_remove_btn)
        col.addLayout(manage_row)
        self.manage_status = QLabel("")
        self.manage_status.setObjectName("Disclaimer")
        self.manage_status.setWordWrap(True)
        col.addWidget(self.manage_status)
        self._refresh_manage_games()
```

- [ ] **Step 6: Add the helper + handler methods**

Add these methods to `OverlayWindow`, right after the seed methods (e.g. after `_teardown_seed`):

```python
    def _confirm(self, title, text):
        """Yes/No modal; factored out so tests can stub it. Returns True on Yes."""
        return QMessageBox.question(
            self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes

    def _manage_count_text(self, game_id):
        if self._articles_repo is None or game_id is None:
            return ""
        n = self._articles_repo.count(game_id=game_id)
        aliases = (self._redirects_repo.count_by_game(game_id)
                   if self._redirects_repo is not None else 0)
        return f"{n:,} guides · {aliases:,} aliases"

    def _refresh_manage_games(self):
        if not hasattr(self, "manage_game"):
            return
        current = self.manage_game.currentData()
        self.manage_game.blockSignals(True)
        self.manage_game.clear()
        for game in self._games:
            self.manage_game.addItem(game.name, game.id)
        want = current if current is not None else (
            self.active_game.id if self.active_game is not None else None)
        if want is not None:
            idx = self.manage_game.findData(want)
            if idx >= 0:
                self.manage_game.setCurrentIndex(idx)
        self.manage_game.blockSignals(False)
        self._on_manage_pick()

    def _on_manage_pick(self):
        if not hasattr(self, "manage_game"):
            return
        game_id = self.manage_game.currentData()
        game = next((g for g in self._games if g.id == game_id), None)
        self.manage_count.setText(self._manage_count_text(game_id))
        # Minecraft is the seeded default — its guides can be cleared but the
        # game itself can't be removed, so the app always has a default.
        self.manage_remove_btn.setEnabled(
            game is not None and game.name != "Minecraft")

    def _clear_game_guides(self, game):
        """Delete a game's stored articles + redirect aliases; reset the
        single-row scrape/redirect state when it's Minecraft (the only game that
        uses them). Returns the number of articles deleted."""
        n = self._articles_repo.delete_by_game(game.id) if self._articles_repo else 0
        if self._redirects_repo is not None:
            self._redirects_repo.delete_by_game(game.id)
        if game.name == "Minecraft":
            if self._scrape_state_repo is not None:
                self._scrape_state_repo.save(ScrapeState(None, 0, None))
            if self._redirect_state_repo is not None:
                self._redirect_state_repo.save(RedirectState(None, 0))
        return n

    def _on_clear_guides(self):
        if self._articles_repo is None:
            return
        game = next((g for g in self._games
                     if g.id == self.manage_game.currentData()), None)
        if game is None:
            return
        if not self._confirm(
                "Clear guides",
                f"Delete all stored guides for {game.name}? This can’t be undone."):
            return
        n = self._clear_game_guides(game)
        self._on_manage_pick()
        self._refresh_guides_status()
        self._refresh_seed_games()
        self.manage_status.setText(f"Cleared {n:,} guides.")

    def _on_remove_game(self):
        if self._games_repo is None:
            return
        game = next((g for g in self._games
                     if g.id == self.manage_game.currentData()), None)
        if game is None or game.name == "Minecraft":
            return
        if not self._confirm(
                "Remove game",
                f"Remove {game.name} and all its guides? This can’t be undone."):
            return
        self._clear_game_guides(game)
        self._games_repo.delete(game.id)
        self._games = self._games_repo.list_games()
        if self.active_game is not None and self.active_game.id == game.id:
            self.active_game = None
            self._update_game_pill()
        self._rebuild_game_menu()
        self._refresh_seed_games()
        self._refresh_manage_games()
        self._refresh_guides_status()
        self.manage_status.setText(f"Removed {game.name}.")
```

- [ ] **Step 7: Keep the manage combo fresh on add/set games**

In `_on_add_game`, after the existing `self._refresh_seed_games()` line, add:

```python
        self._refresh_manage_games()
```

In `set_games`, after the existing `self._refresh_seed_games()` line, add:

```python
        self._refresh_manage_games()
```

- [ ] **Step 8: Wire `RedirectsRepo` in main.py**

In `meister_guide/main.py`, update the redirects import line:

```python
from meister_guide.db.redirects import RedirectsRepo, RedirectStateRepo
```

After `redirect_state_repo = RedirectStateRepo(conn)`, add:

```python
    redirects_repo = RedirectsRepo(conn)
```

In the `OverlayWindow(...)` call, add the kwarg after `games_repo=games_repo`:

```python
                            games_repo=games_repo,
                            redirects_repo=redirects_repo)
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `py -m pytest tests/test_window_manage.py -q`
Expected: PASS (7 passed).

- [ ] **Step 10: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS — all prior tests plus the new ones.

- [ ] **Step 11: Commit**

```bash
git add meister_guide/overlay/window.py meister_guide/main.py tests/test_window_manage.py
git commit -m "feat: Manage-guides UI (clear guides / remove game) on Settings tab"
```

---

## Final verification

- [ ] Run `py -m pytest -q` — confirm the whole suite passes.
- [ ] Confirm no perpetually-dirty files were staged (`.planning/HANDOFF.json`, `devlogs/the-whole-build.md`, `Meister Guide overlay design/`, `DONOTTOUCH.txt`).
- [ ] Then proceed to `superpowers:finishing-a-development-branch`.

## Notes / rationale

- **Per-row contentless-FTS delete:** `articles_fts`/`redirects_fts` are contentless (`content=''`), so deleting an index row requires re-supplying the original column values via the `'delete'` command — the same pattern `prune_noise` already uses. A bulk `DELETE FROM articles WHERE game_id=?` alone would orphan the FTS index.
- **`redirects_repo` injection:** the window needs a `RedirectsRepo` to clear aliases; main.py already shares one sqlite connection across repos, so it just constructs and passes one (the window previously only held the *state* repos, not the redirects repo).
- **Minecraft state reset:** `scrape_state`/`redirect_state` are single-row tables only Minecraft populates; resetting them on a Minecraft clear stops the Guides tab reporting a stale "done" count over an emptied corpus.
- **`blockSignals` during repopulate:** `_refresh_manage_games` clears+refills the combo, which would otherwise fire `currentIndexChanged` mid-rebuild; signals are blocked and `_on_manage_pick` is called once at the end.
- **`_confirm` seam:** destructive ops route through `_confirm` so tests stub it instead of driving a modal.
```
