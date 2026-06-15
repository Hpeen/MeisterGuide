# Meister Guide — Phase 2: Data + Game Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist data in SQLite at `%APPDATA%\MeisterGuide\meister.db` with Minecraft preloaded, detect running games every 10s via process scanning, and show the result in the overlay header ("Playing: Minecraft") with a manual game-picker dropdown when nothing is detected.

**Architecture:** A thin `db/` layer (connection + schema init + a `GamesRepo`). A `detector/` package with a pure `match_running_game()` function and a `GameDetector` QObject that polls `psutil` on a `QTimer` and emits a signal on change. `main.py` wires the repo and detector into the existing `OverlayWindow`, which gains active-game state, a header indicator, and a manual dropdown.

**Tech Stack:** Python 3.12, `sqlite3` (stdlib), `psutil`, PySide6.

**Note on Python:** the system `python`/`pip` are broken Windows Store stubs. Use `py -3` (maps to Python 3.12.0) or the full path `C:\Users\Tudor\AppData\Local\Programs\Python\Python312\python.exe`. Run tests headless with `QT_QPA_PLATFORM=offscreen`.

**Scope note:** The 5 core tables (`games`, `guides`, `chat_sessions`, `chat_messages`, `settings`) are created in this phase. The FTS5 search table and its sync triggers are deferred to Phase 3, where guides are actually scraped and searched — creating them now would be unused machinery.

---

## File Structure

```
meister_guide/
  db/
    __init__.py            (new, empty)
    schema.py              (new) CREATE TABLE statements
    database.py            (new) path resolution, connect(), init_db()
    games.py               (new) Game dataclass + GamesRepo + Minecraft seed
  detector/
    __init__.py            (new, empty)
    matcher.py             (new) pure match_running_game()
    detector.py            (new) GameDetector QObject (QTimer + psutil)
  overlay/
    window.py              (modify) active-game state, indicator, dropdown
  main.py                  (modify) wire db + detector into overlay
tests/
  test_database.py         (new)
  test_games_repo.py       (new)
  test_matcher.py          (new)
  test_detector.py         (new)
devlogs/
  002-the-ledger.md        (new)
```

---

### Task 1: Database connection + schema init

**Files:**
- Create: `meister_guide/db/__init__.py` (empty)
- Create: `meister_guide/db/schema.py`
- Create: `meister_guide/db/database.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
import sqlite3
from meister_guide.db.database import connect, init_db


def test_init_creates_all_core_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"games", "guides", "chat_sessions", "chat_messages", "settings"} <= names


def test_init_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    init_db(conn)  # must not raise
    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_database.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `meister_guide/db/__init__.py`** (empty file)

- [ ] **Step 4: Write `meister_guide/db/schema.py`**

```python
"""SQLite schema for Meister Guide. Phase 2 creates the 5 core tables.
The FTS5 search table is added in Phase 3."""

CORE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        process_names TEXT NOT NULL,  -- JSON array of strings
        wiki_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guides (
        id INTEGER PRIMARY KEY,
        game_id INTEGER REFERENCES games(id),
        title TEXT NOT NULL,
        url TEXT,
        content TEXT NOT NULL,
        scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY,
        game_id INTEGER REFERENCES games(id),
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        title TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY,
        session_id INTEGER REFERENCES chat_sessions(id),
        role TEXT NOT NULL,  -- 'user' or 'assistant'
        content TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
]
```

- [ ] **Step 5: Write `meister_guide/db/database.py`**

```python
"""SQLite connection and schema initialisation."""
import os
import sqlite3
from pathlib import Path

from meister_guide.db.schema import CORE_TABLES


def default_db_path() -> Path:
    """%APPDATA%\\MeisterGuide\\meister.db (falls back to home if APPDATA unset)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MeisterGuide" / "meister.db"


def connect(db_path) -> sqlite3.Connection:
    """Open (creating parent dirs as needed) a SQLite connection."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the core tables if they don't exist. Idempotent."""
    for statement in CORE_TABLES:
        conn.execute(statement)
    conn.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_database.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add meister_guide/db/__init__.py meister_guide/db/schema.py meister_guide/db/database.py tests/test_database.py
git commit -m "feat: add SQLite connection and core schema"
```

---

### Task 2: Games repository + Minecraft seed

**Files:**
- Create: `meister_guide/db/games.py`
- Test: `tests/test_games_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_games_repo.py
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo, Game


def _repo(tmp_path):
    conn = connect(tmp_path / "g.db")
    init_db(conn)
    return GamesRepo(conn)


def test_seed_adds_minecraft_once(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_defaults()
    repo.seed_defaults()  # second call must be a no-op
    games = repo.list_games()
    assert len(games) == 1
    mc = games[0]
    assert mc.name == "Minecraft"
    assert "javaw.exe" in mc.process_names
    assert "Minecraft.exe" in mc.process_names
    assert "MinecraftLauncher.exe" in mc.process_names
    assert mc.wiki_url == "https://minecraft.wiki"


def test_add_get_update_delete(tmp_path):
    repo = _repo(tmp_path)
    g = repo.add("Terraria", ["Terraria.exe"], "https://terraria.wiki.gg")
    assert isinstance(g, Game)
    assert repo.get(g.id).name == "Terraria"

    repo.update(g.id, "Terraria", ["Terraria.exe", "tModLoader.exe"], "https://terraria.wiki.gg")
    assert "tModLoader.exe" in repo.get(g.id).process_names

    repo.delete(g.id)
    assert repo.get(g.id) is None


def test_process_names_roundtrip_as_list(tmp_path):
    repo = _repo(tmp_path)
    g = repo.add("X", ["a.exe", "b.exe"], None)
    assert repo.get(g.id).process_names == ["a.exe", "b.exe"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_games_repo.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `meister_guide/db/games.py`**

```python
"""Games table access: the Game model, CRUD, and the Minecraft seed."""
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class Game:
    id: int
    name: str
    process_names: list  # list[str]
    wiki_url: Optional[str]


_MINECRAFT = {
    "name": "Minecraft",
    "process_names": ["javaw.exe", "Minecraft.exe", "MinecraftLauncher.exe"],
    "wiki_url": "https://minecraft.wiki",
}

_SELECT = "SELECT id, name, process_names, wiki_url FROM games"


class GamesRepo:
    def __init__(self, conn):
        self._conn = conn

    @staticmethod
    def _row_to_game(row) -> Game:
        return Game(row[0], row[1], json.loads(row[2]), row[3])

    def list_games(self):
        cur = self._conn.execute(_SELECT + " ORDER BY name")
        return [self._row_to_game(r) for r in cur.fetchall()]

    def get(self, game_id):
        cur = self._conn.execute(_SELECT + " WHERE id = ?", (game_id,))
        row = cur.fetchone()
        return self._row_to_game(row) if row else None

    def add(self, name, process_names, wiki_url) -> Game:
        cur = self._conn.execute(
            "INSERT INTO games (name, process_names, wiki_url) VALUES (?, ?, ?)",
            (name, json.dumps(process_names), wiki_url),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)

    def update(self, game_id, name, process_names, wiki_url) -> None:
        self._conn.execute(
            "UPDATE games SET name = ?, process_names = ?, wiki_url = ? WHERE id = ?",
            (name, json.dumps(process_names), wiki_url, game_id),
        )
        self._conn.commit()

    def delete(self, game_id) -> None:
        self._conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        self._conn.commit()

    def seed_defaults(self) -> None:
        """Insert Minecraft only if the games table is empty."""
        if self._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0:
            self.add(
                _MINECRAFT["name"],
                _MINECRAFT["process_names"],
                _MINECRAFT["wiki_url"],
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_games_repo.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/games.py tests/test_games_repo.py
git commit -m "feat: add games repository with Minecraft seed"
```

---

### Task 3: Process matcher (pure)

**Files:**
- Create: `meister_guide/detector/__init__.py` (empty)
- Create: `meister_guide/detector/matcher.py`
- Test: `tests/test_matcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matcher.py
from meister_guide.detector.matcher import match_running_game
from meister_guide.db.games import Game

MINECRAFT = Game(1, "Minecraft", ["javaw.exe", "Minecraft.exe"], "https://minecraft.wiki")
TERRARIA = Game(2, "Terraria", ["Terraria.exe"], None)
GAMES = [MINECRAFT, TERRARIA]


def test_matches_by_process_name_case_insensitive():
    assert match_running_game(["chrome.exe", "JAVAW.EXE"], GAMES) is MINECRAFT


def test_returns_none_when_no_match():
    assert match_running_game(["chrome.exe", "explorer.exe"], GAMES) is None


def test_returns_first_listed_game_on_match():
    assert match_running_game(["Terraria.exe"], GAMES) is TERRARIA


def test_empty_running_list_returns_none():
    assert match_running_game([], GAMES) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_matcher.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `meister_guide/detector/__init__.py`** (empty file)

- [ ] **Step 4: Write `meister_guide/detector/matcher.py`**

```python
"""Pure logic: pick the active game from a list of running process names."""


def match_running_game(running_names, games):
    """Return the first Game whose any process name is currently running.

    running_names: iterable of process executable names (any case).
    games: list of Game. Returns the matching Game, or None.
    """
    running = {n.lower() for n in running_names}
    for game in games:
        for proc_name in game.process_names:
            if proc_name.lower() in running:
                return game
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_matcher.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/detector/__init__.py meister_guide/detector/matcher.py tests/test_matcher.py
git commit -m "feat: add pure running-game matcher"
```

---

### Task 4: GameDetector (QTimer + psutil)

**Files:**
- Create: `meister_guide/detector/detector.py`
- Test: `tests/test_detector.py`

The detector accepts an injectable `process_lister` so its change-detection logic can
be unit-tested without real processes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_detector.py
from meister_guide.detector.detector import GameDetector
from meister_guide.db.games import Game

MINECRAFT = Game(1, "Minecraft", ["javaw.exe"], None)


def test_poll_emits_game_then_none_on_change():
    running = {"names": ["javaw.exe"]}
    detector = GameDetector(
        games_provider=lambda: [MINECRAFT],
        process_lister=lambda: running["names"],
    )
    seen = []
    detector.detected.connect(seen.append)

    detector.poll()                 # match -> emit Minecraft
    running["names"] = ["chrome.exe"]
    detector.poll()                 # no match -> emit None

    assert seen == [MINECRAFT, None]


def test_poll_does_not_re_emit_same_state():
    detector = GameDetector(
        games_provider=lambda: [MINECRAFT],
        process_lister=lambda: ["javaw.exe"],
    )
    seen = []
    detector.detected.connect(seen.append)

    detector.poll()
    detector.poll()  # same match -> must NOT emit again

    assert seen == [MINECRAFT]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_detector.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `meister_guide/detector/detector.py`**

```python
"""Background game detection: polls running processes on a timer and emits
the active Game (or None) whenever the detected state changes."""
import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from meister_guide.detector.matcher import match_running_game

_UNSET = object()


def _psutil_process_names():
    names = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name:
                names.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return names


class GameDetector(QObject):
    """Emits `detected(Game | None)` on every change of detected game."""

    detected = Signal(object)

    def __init__(self, games_provider, interval_ms=10000,
                 process_lister=_psutil_process_names):
        super().__init__()
        self._games_provider = games_provider
        self._process_lister = process_lister
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)
        self._last_id = _UNSET

    def start(self):
        """Poll immediately, then every interval_ms."""
        self.poll()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll(self):
        game = match_running_game(self._process_lister(), self._games_provider())
        current_id = game.id if game is not None else None
        if current_id != self._last_id:
            self._last_id = current_id
            self.detected.emit(game)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_detector.py -v`
Expected: PASS (2 tests). If `QTimer`/`QObject` construction raises about a missing
application, add this fixture at the top of the test file and report the deviation:
```python
import pytest
from PySide6.QtCore import QCoreApplication

@pytest.fixture(autouse=True)
def _app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app
```

- [ ] **Step 5: Commit**

```bash
git add meister_guide/detector/detector.py tests/test_detector.py
git commit -m "feat: add GameDetector polling with change detection"
```

---

### Task 5: Overlay integration — active game + manual dropdown

**Files:**
- Modify: `meister_guide/overlay/window.py`

Adds active-game state, updates the header indicator, and shows a manual game-picker
`QComboBox` only when no game is detected. No new unit test (GUI verified by running).

- [ ] **Step 1: Update the imports in `meister_guide/overlay/window.py`**

Replace this import block:

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame,
)
```

with:

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame, QComboBox,
)
```

- [ ] **Step 2: Change the constructor signature and store games + active state**

Replace:

```python
    def __init__(self, settings: QSettings):
        super().__init__()
        self._settings = settings
        self._drag_offset = None
```

with:

```python
    def __init__(self, settings: QSettings, games=None):
        super().__init__()
        self._settings = settings
        self._drag_offset = None
        self._games = list(games) if games else []
        self.active_game = None
```

- [ ] **Step 3: Replace `_build_header` to add the dropdown**

Replace the whole `_build_header` method with:

```python
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(40)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(12, 0, 12, 0)

        title = QLabel("⚒ Meister Guide")  # crossed hammers
        title.setObjectName("HeaderTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        self.game_indicator = QLabel("● No game detected")
        self.game_indicator.setObjectName("GameIndicator")
        lay.addWidget(self.game_indicator)

        self.game_dropdown = QComboBox()
        self.game_dropdown.setObjectName("GameDropdown")
        self.game_dropdown.currentIndexChanged.connect(self._on_manual_pick)
        lay.addWidget(self.game_dropdown)
        self._populate_dropdown()

        self._header = header
        return header
```

- [ ] **Step 4: Add the dropdown/state helper methods**

Add these methods to the `OverlayWindow` class (place them just after `_build_footer`):

```python
    # ---- game selection -------------------------------------------------
    def _populate_dropdown(self):
        self.game_dropdown.blockSignals(True)
        self.game_dropdown.clear()
        self.game_dropdown.addItem("Select a game...", None)
        for game in self._games:
            self.game_dropdown.addItem(game.name, game.id)
        self.game_dropdown.blockSignals(False)

    def set_games(self, games):
        self._games = list(games)
        self._populate_dropdown()

    def _set_active(self, game, manual: bool):
        self.active_game = game
        if game is None:
            self.game_indicator.setText("● No game detected")
            self.game_dropdown.setVisible(True)
        else:
            suffix = " (manual)" if manual else ""
            self.game_indicator.setText(f"● Playing: {game.name}{suffix}")
            # Hide the picker on auto-detection; keep it on a manual pick so the
            # user can re-choose.
            self.game_dropdown.setVisible(manual)

    def set_detected_game(self, game):
        """Called by the detector. A detection always wins over a manual pick."""
        self._set_active(game, manual=False)

    def _on_manual_pick(self, index):
        game_id = self.game_dropdown.itemData(index)
        if game_id is None:
            return
        chosen = next((g for g in self._games if g.id == game_id), None)
        if chosen is not None:
            self._set_active(chosen, manual=True)
```

- [ ] **Step 5: Verify it constructs offscreen**

Run:
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; app=QApplication([]); from meister_guide.overlay.window import OverlayWindow; from meister_guide.db.games import Game; w=OverlayWindow(QSettings('MG','t'), [Game(1,'Minecraft',['javaw.exe'],None)]); w.set_detected_game(Game(1,'Minecraft',['javaw.exe'],None)); print(w.game_indicator.text()); w.set_detected_game(None); print(w.game_indicator.text())"
```
Expected output:
```
● Playing: Minecraft
● No game detected
```

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: overlay active-game indicator and manual game picker"
```

---

### Task 6: Wire db + detector into the app

**Files:**
- Modify: `meister_guide/main.py`

- [ ] **Step 1: Add imports**

After the existing `from meister_guide.input.hotkey import GlobalHotkey` line, add:

```python
from meister_guide.db.database import default_db_path, connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.detector.detector import GameDetector
```

- [ ] **Step 2: Build db + repo + detector and wire them in `main()`**

Replace these two lines:

```python
    settings = QSettings(ORG, APP)
    overlay = OverlayWindow(settings)
```

with:

```python
    settings = QSettings(ORG, APP)

    conn = connect(default_db_path())
    init_db(conn)
    games_repo = GamesRepo(conn)
    games_repo.seed_defaults()

    overlay = OverlayWindow(settings, games_repo.list_games())

    detector = GameDetector(games_provider=games_repo.list_games)
    detector.detected.connect(overlay.set_detected_game)
```

- [ ] **Step 3: Start the detector and stop it on quit**

Replace:

```python
    app.aboutToQuit.connect(hotkey.unregister)
    app.aboutToQuit.connect(settings.sync)  # flush geometry once on quit
    return app.exec()
```

with:

```python
    detector.start()

    app.aboutToQuit.connect(hotkey.unregister)
    app.aboutToQuit.connect(detector.stop)
    app.aboutToQuit.connect(settings.sync)  # flush geometry once on quit
    return app.exec()
```

- [ ] **Step 4: Verify it imports (do not run the event loop)**

Run:
```
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "import meister_guide.main as m; print('import ok', callable(m.main))"
```
Expected: `import ok True`.

- [ ] **Step 5: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add meister_guide/main.py
git commit -m "feat: wire SQLite, games repo, and game detector into app"
```

---

### Task 7: Phase 2 devlog

**Files:**
- Create: `devlogs/002-the-ledger.md`

- [ ] **Step 1: Write the devlog (playful, informative, no emojis)**

```markdown
# Devlog 002 - The Ledger

Today Meister Guide grew a memory. Up until now it forgot everything the moment
you closed it, which is a bad look for an app whose whole job is remembering
stuff for you. So I gave it a proper SQLite database, tucked away in your AppData
folder, with tables for games, guides, chat sessions, and settings. Minecraft
gets seeded in automatically on first launch, like the founding entry in a
workshop ledger.

The fun part was teaching it to actually notice when you are playing. Every ten
seconds it quietly sweeps the list of running processes and checks them against
the games it knows about. See javaw.exe or Minecraft.exe in the list? The header
flips to "Playing: Minecraft" without you lifting a finger. No popups, no
nagging, it just knows.

I made the detection logic its own tiny pure function on purpose, so I could test
it without launching an actual game. Feed it a fake list of process names, ask
who is playing, check the answer. The detector wrapper handles the boring timer
plumbing and only speaks up when the answer actually changes, so it is not
spamming the rest of the app every ten seconds with "still Minecraft, still
Minecraft."

And if nothing is detected, there is now a little dropdown so you can just tell
it what you are playing. Next phase is the big one: scraping the Minecraft wiki
and stuffing all those guides into the database so they work offline. See you
there.
```

- [ ] **Step 2: Commit**

```bash
git add devlogs/002-the-ledger.md
git commit -m "docs: add Phase 2 devlog"
```

---

## Self-Review

**Spec coverage (Phase 2 scope):**
- SQLite at `%APPDATA%\MeisterGuide\meister.db` — Task 1 (`default_db_path`). ✓
- Full 5-table schema — Task 1 (FTS5 deferred to Phase 3, documented). ✓
- Minecraft preloaded with the 3 process names + wiki URL — Task 2 seed. ✓
- Game list stored in DB with add/edit/delete — Task 2 `GamesRepo`. ✓
- Scan processes every 10s — Task 4 (`interval_ms=10000`). ✓
- Match process names — Task 3 matcher. ✓
- Auto-set active game + "Playing: Minecraft" indicator — Tasks 4, 5, 6. ✓
- "No game detected" + manual dropdown — Task 5. ✓
- Silent background detection, no popups — Task 4 (signal only, no UI interrupts). ✓

Deferred correctly: the Games **settings page** (add/edit/delete UI) is Phase 5; this
phase delivers the repository and dropdown only. Loading a game's guides/chat on
detection is Phase 3/4 (no guides/chat exist yet) — `active_game` state is exposed now
for those phases to consume.

**Placeholder scan:** No TBDs. Every step has complete code.

**Type consistency:** `Game(id, name, process_names: list, wiki_url)` is constructed
identically in `GamesRepo._row_to_game`, the matcher tests, and the detector tests.
`GamesRepo.list_games` is the callable passed as `games_provider` to `GameDetector` and
returns `list[Game]`. `GameDetector.detected` emits `Game | None`, consumed by
`OverlayWindow.set_detected_game(game)`. `connect()`/`init_db()` signatures match across
`database.py`, tests, and `main.py`. `OverlayWindow.__init__(settings, games=None)`
matches the call in `main.py` which passes `games_repo.list_games()`.

**Behavior note:** manual picks keep the dropdown visible (so the user can re-pick);
auto-detections hide it. A later detection always overrides a manual pick via
`set_detected_game`.
```
