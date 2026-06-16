# Phase 4: Meister AI Chat (Ollama + RAG) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Chat tab where the user asks a question, the app retrieves the top-3 relevant guide passages from the offline FTS5 index, sends them + the conversation to a local Ollama model, and streams the grounded answer back with clickable source citations and persisted session history.

**Architecture:** Pure, injectable `ai/` units (Ollama HTTP client, RAG passage builder, prompt builder) + a `db/chat.py` repo over the existing chat tables. FTS retrieval and DB writes run on the main thread; only the Ollama stream runs on a `QThread` (`ChatStreamWorker`) emitting `token`/`finished`/`error` signals so the overlay stays responsive.

**Tech Stack:** Python 3.12, PySide6 (QThread/QObject signals, QTextBrowser anchors), SQLite, `requests`, Ollama HTTP API. Tests: pytest, headless via `QT_QPA_PLATFORM=offscreen`, network-free via injected HTTP callables.

**Environment:** Use `py -3` (system `python` is a broken Store stub). Prefix GUI-touching commands with `QT_QPA_PLATFORM=offscreen` (and `PYTHONIOENCODING=utf-8` for smoke checks). Run tests with `QT_QPA_PLATFORM=offscreen py -3 -m pytest`. End every commit message with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Never stage `.planning/HANDOFF.json`.

---

## File Structure

- Modify `meister_guide/scraper/excerpt.py` — extract `window_bounds()`; `make_excerpt` reuses it (no behaviour change).
- Create `meister_guide/ai/__init__.py` — package marker.
- Create `meister_guide/ai/passage.py` — `relevant_passage()` plain-text RAG window.
- Create `meister_guide/ai/ollama_client.py` — `OllamaClient`, `OllamaUnavailable`, `pick_model`.
- Create `meister_guide/ai/prompt.py` — `build_messages()`.
- Create `meister_guide/db/chat.py` — `ChatRepo`, `ChatSession`, `ChatMessage`.
- Create `meister_guide/ai/worker.py` — `ChatStreamWorker(QObject)`.
- Modify `meister_guide/overlay/window.py` — Chat tab UI + send/stream/sources/sessions; new `__init__` params; store `self._tabs`.
- Modify `meister_guide/main.py` — build `ChatRepo` + `OllamaClient`, pass to `OverlayWindow`.
- Modify `README.md` — document the Chat tab.
- Tests: `tests/test_passage.py`, `tests/test_ollama_client.py`, `tests/test_prompt.py`, `tests/test_chat_repo.py`, `tests/test_chat_worker.py`, `tests/test_window_chat.py`, plus an appended case in `tests/test_excerpt.py`.

---

## Task 1: Refactor `window_bounds` out of `make_excerpt`

**Files:**
- Modify: `meister_guide/scraper/excerpt.py`
- Test: `tests/test_excerpt.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_excerpt.py`:

```python
def test_window_bounds_centers_on_match():
    from meister_guide.scraper.excerpt import window_bounds
    body = "x" * 100 + "creeper" + "y" * 100
    start, end = window_bounds(body, "creeper", 60)
    assert start <= 100 < end          # the match (at index 100) is inside
    assert end - start <= 60


def test_window_bounds_no_match_is_leading_window():
    from meister_guide.scraper.excerpt import window_bounds
    assert window_bounds("alpha beta", "zzz", 5) == (0, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_excerpt.py::test_window_bounds_centers_on_match -v`
Expected: FAIL (`cannot import name 'window_bounds'`).

- [ ] **Step 3: Implement the refactor**

Replace the body of `meister_guide/scraper/excerpt.py` (keep the module docstring and imports) so the window logic is a shared function:

```python
def window_bounds(body: str, query: str, width: int) -> tuple:
    """Return (start, end) of a `width`-char window centred on the earliest
    query-term match, or the leading window when nothing matches."""
    terms = [t for t in _WORD.findall(query.lower()) if t]
    lowered = body.lower()
    first = -1
    for term in terms:
        idx = lowered.find(term)
        if idx != -1 and (first == -1 or idx < first):
            first = idx
    if first == -1:
        return 0, min(len(body), width)
    start = max(0, first - width // 3)
    end = min(len(body), start + width)
    return start, end


def make_excerpt(body: str, query: str, width: int = 240) -> str:
    terms = [t for t in _WORD.findall(query.lower()) if t]
    start, end = window_bounds(body, query, width)
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""

    escaped = html.escape(snippet)
    unique_terms = sorted(set(terms), key=len, reverse=True)
    if unique_terms:
        pattern = "|".join(re.escape(html.escape(t)) for t in unique_terms)
        escaped = re.sub("(" + pattern + ")", r"<b>\1</b>", escaped,
                         flags=re.IGNORECASE)
    return f"{prefix}{escaped}{suffix}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_excerpt.py -v`
Expected: PASS (the new window tests AND all pre-existing make_excerpt tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/excerpt.py tests/test_excerpt.py
git commit -m "refactor: extract window_bounds from make_excerpt for reuse"
```

---

## Task 2: `ai/passage.py` — plain-text RAG passage

**Files:**
- Create: `meister_guide/ai/__init__.py` (empty)
- Create: `meister_guide/ai/passage.py`
- Test: `tests/test_passage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_passage.py`:

```python
from meister_guide.ai.passage import relevant_passage


def test_passage_is_plain_text_window_around_match():
    body = "alpha " * 100 + "creeper explodes " + "omega " * 100
    out = relevant_passage(body, "creeper", width=80)
    assert "creeper" in out
    assert "<b>" not in out               # plain text, not HTML
    assert out.startswith("…") and out.endswith("…")
    assert len(out) <= 82                  # width + the two ellipses


def test_passage_no_match_returns_leading_text():
    out = relevant_passage("Redstone basics here.", "zzz", width=9)
    assert out.startswith("Redstone")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_passage.py -v`
Expected: FAIL (`No module named 'meister_guide.ai'`).

- [ ] **Step 3: Implement**

Create `meister_guide/ai/__init__.py` (empty file). Create `meister_guide/ai/passage.py`:

```python
"""Plain-text relevance window for RAG context (model input).

Sibling of scraper.excerpt.make_excerpt, but returns plain text (no HTML
escaping or <b> highlighting) since it feeds the model, not a QLabel."""
from meister_guide.scraper.excerpt import window_bounds


def relevant_passage(body: str, query: str, width: int = 1500) -> str:
    start, end = window_bounds(body, query, width)
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet}{suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_passage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/__init__.py meister_guide/ai/passage.py tests/test_passage.py
git commit -m "feat: plain-text RAG passage builder"
```

---

## Task 3: `OllamaClient.list_models` + `pick_model`

**Files:**
- Create: `meister_guide/ai/ollama_client.py`
- Test: `tests/test_ollama_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ollama_client.py`:

```python
import pytest
from meister_guide.ai.ollama_client import OllamaClient, OllamaUnavailable, pick_model


def test_list_models_parses_tags():
    def fake_get(url):
        assert url.endswith("/api/tags")
        return {"models": [{"name": "llama3:latest"}, {"name": "mistral"}]}
    client = OllamaClient(http_get=fake_get)
    assert client.list_models() == ["llama3:latest", "mistral"]


def test_list_models_raises_when_unreachable():
    def boom(url):
        raise OllamaUnavailable("connection refused")
    client = OllamaClient(http_get=boom)
    with pytest.raises(OllamaUnavailable):
        client.list_models()


def test_pick_model_prefers_llama3_then_first_then_none():
    assert pick_model(["mistral", "llama3:latest"]) == "llama3:latest"
    assert pick_model(["mistral", "phi"]) == "mistral"
    assert pick_model([]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ollama_client.py -v`
Expected: FAIL (`No module named 'meister_guide.ai.ollama_client'`).

- [ ] **Step 3: Implement**

Create `meister_guide/ai/ollama_client.py`:

```python
"""Client for a local Ollama server. HTTP is injectable so tests run without a
server; defaults use `requests`. Connection failures raise OllamaUnavailable."""
import json

DEFAULT_BASE = "http://localhost:11434"


class OllamaUnavailable(Exception):
    """Ollama could not be reached (not running / wrong port / network)."""


def pick_model(names):
    """Prefer a llama3* model, else the first installed, else None."""
    for name in names:
        if name.startswith("llama3"):
            return name
    return names[0] if names else None


class OllamaClient:
    def __init__(self, base_url=DEFAULT_BASE, http_get=None, http_post=None):
        self._base = base_url.rstrip("/")
        self._http_get = http_get or self._default_get
        self._http_post = http_post or self._default_post_lines

    def _default_get(self, url):
        import requests
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as err:
            raise OllamaUnavailable(str(err))

    def _default_post_lines(self, url, payload):
        import requests
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=300)
            resp.raise_for_status()
            return resp.iter_lines()
        except requests.RequestException as err:
            raise OllamaUnavailable(str(err))

    def list_models(self):
        data = self._http_get(self._base + "/api/tags")
        return [m["name"] for m in data.get("models", [])]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ollama_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: Ollama client model listing + model preference"
```

---

## Task 4: `OllamaClient.chat` streaming

**Files:**
- Modify: `meister_guide/ai/ollama_client.py`
- Test: `tests/test_ollama_client.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ollama_client.py`:

```python
def test_chat_streams_content_chunks_until_done():
    sent = {}
    def fake_post(url, payload):
        sent["url"] = url
        sent["payload"] = payload
        return [
            '{"message": {"role": "assistant", "content": "Hel"}, "done": false}',
            '{"message": {"role": "assistant", "content": "lo"}, "done": false}',
            '',  # keep-alive / blank line, must be skipped
            '{"message": {"role": "assistant", "content": "!"}, "done": true}',
            '{"message": {"role": "assistant", "content": "IGNORED"}, "done": false}',
        ]
    client = OllamaClient(http_post=fake_post)
    chunks = list(client.chat("llama3", [{"role": "user", "content": "hi"}]))
    assert "".join(chunks) == "Hello!"        # stops at done, ignores trailing
    assert sent["url"].endswith("/api/chat")
    assert sent["payload"]["model"] == "llama3"
    assert sent["payload"]["stream"] is True


def test_chat_accepts_bytes_lines():
    def fake_post(url, payload):
        return [b'{"message": {"content": "hi"}, "done": true}']
    client = OllamaClient(http_post=fake_post)
    assert list(client.chat("m", [])) == ["hi"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ollama_client.py -k chat -v`
Expected: FAIL (`'OllamaClient' object has no attribute 'chat'`).

- [ ] **Step 3: Implement**

Add the `chat` method to `OllamaClient` in `meister_guide/ai/ollama_client.py`:

```python
    def chat(self, model, messages):
        """Stream a chat completion, yielding content chunks. Stops at the line
        whose `done` is true. `_http_post` returns an iterable of NDJSON lines
        (str or bytes)."""
        lines = self._http_post(
            self._base + "/api/chat",
            {"model": model, "messages": messages, "stream": True},
        )
        for line in lines:
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            obj = json.loads(line)
            chunk = (obj.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_ollama_client.py -v`
Expected: PASS (all client tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: streaming Ollama /api/chat client"
```

---

## Task 5: `prompt.build_messages`

**Files:**
- Create: `meister_guide/ai/prompt.py`
- Test: `tests/test_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompt.py`:

```python
from meister_guide.ai.prompt import build_messages


def test_build_messages_structures_system_history_user():
    passages = [("Creeper", "A creeper explodes."), ("TNT", "TNT is craftable.")]
    history = [("user", "hi"), ("assistant", "hello")]
    msgs = build_messages("How do creepers work?", passages, history)

    assert msgs[0]["role"] == "system"
    assert "Creeper" in msgs[0]["content"] and "A creeper explodes." in msgs[0]["content"]
    assert "TNT" in msgs[0]["content"]
    assert msgs[1:3] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert msgs[-1] == {"role": "user", "content": "How do creepers work?"}


def test_build_messages_without_passages_has_no_excerpt_block():
    msgs = build_messages("hello", [], [])
    assert msgs[0]["role"] == "system"
    assert "Guide excerpts" not in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "hello"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_prompt.py -v`
Expected: FAIL (`No module named 'meister_guide.ai.prompt'`).

- [ ] **Step 3: Implement**

Create `meister_guide/ai/prompt.py`:

```python
"""Build the Ollama /api/chat `messages` array: a system prompt carrying the
retrieved guide excerpts, the prior turns, then the new question."""

SYSTEM_PREAMBLE = (
    "You are Meister, a helpful in-game Minecraft assistant. Answer the user's "
    "question using the guide excerpts below when they are relevant. If the "
    "excerpts do not contain the answer, say you are not sure based on the "
    "available guides rather than inventing details. Keep answers concise."
)


def build_messages(question, passages, history):
    """passages: list[(title, text)]; history: list[(role, content)]."""
    system = SYSTEM_PREAMBLE
    if passages:
        blocks = "\n\n".join(f"[{title}]\n{text}" for title, text in passages)
        system += "\n\n--- Guide excerpts ---\n" + blocks + "\n--- end excerpts ---"
    messages = [{"role": "system", "content": system}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/prompt.py tests/test_prompt.py
git commit -m "feat: RAG prompt builder"
```

---

## Task 6: `ChatRepo` (db/chat.py)

**Files:**
- Create: `meister_guide/db/chat.py`
- Test: `tests/test_chat_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_chat_repo.py`:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.chat import ChatRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "c.db")
    init_db(conn)
    return ChatRepo(conn)


def test_session_and_message_crud(tmp_path):
    repo = _repo(tmp_path)
    sid = repo.create_session(game_id=1, title=None)
    repo.add_message(sid, "user", "hi")
    repo.add_message(sid, "assistant", "hello")
    msgs = repo.get_messages(sid)
    assert [(m.role, m.content) for m in msgs] == [("user", "hi"), ("assistant", "hello")]


def test_set_title_and_list_newest_first(tmp_path):
    repo = _repo(tmp_path)
    s1 = repo.create_session()
    s2 = repo.create_session()
    repo.set_title(s1, "First chat")
    sessions = repo.list_sessions()
    assert sessions[0].id == s2            # newest first
    titles = {s.id: s.title for s in sessions}
    assert titles[s1] == "First chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_chat_repo.py -v`
Expected: FAIL (`No module named 'meister_guide.db.chat'`).

- [ ] **Step 3: Implement**

Create `meister_guide/db/chat.py`:

```python
"""Chat persistence over the Phase 2 chat_sessions / chat_messages tables."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatSession:
    id: int
    title: Optional[str]
    started_at: str


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatRepo:
    def __init__(self, conn):
        self._conn = conn

    def create_session(self, game_id=None, title=None) -> int:
        cur = self._conn.execute(
            "INSERT INTO chat_sessions (game_id, title) VALUES (?, ?)",
            (game_id, title),
        )
        self._conn.commit()
        return cur.lastrowid

    def set_title(self, session_id, title) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        self._conn.commit()

    def add_message(self, session_id, role, content) -> int:
        cur = self._conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_sessions(self):
        rows = self._conn.execute(
            "SELECT id, title, started_at FROM chat_sessions ORDER BY id DESC"
        ).fetchall()
        return [ChatSession(r[0], r[1], r[2]) for r in rows]

    def get_messages(self, session_id):
        rows = self._conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [ChatMessage(r[0], r[1]) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_chat_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/chat.py tests/test_chat_repo.py
git commit -m "feat: ChatRepo for persisted sessions and messages"
```

---

## Task 7: `ChatStreamWorker` (ai/worker.py)

**Files:**
- Create: `meister_guide/ai/worker.py`
- Test: `tests/test_chat_worker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_chat_worker.py`:

```python
from PySide6.QtWidgets import QApplication
from meister_guide.ai.worker import ChatStreamWorker


class FakeClient:
    def __init__(self, chunks=None, boom=False):
        self._chunks = chunks or []
        self._boom = boom
    def chat(self, model, messages):
        if self._boom:
            raise RuntimeError("stream broke")
        for c in self._chunks:
            yield c


def test_worker_emits_tokens_then_finished():
    QApplication.instance() or QApplication([])
    worker = ChatStreamWorker(FakeClient(["He", "llo"]), "llama3", [])
    tokens, done = [], []
    worker.token.connect(lambda t: tokens.append(t))
    worker.finished.connect(lambda full: done.append(full))
    worker.run()
    assert tokens == ["He", "llo"]
    assert done == ["Hello"]


def test_worker_emits_error_not_finished_on_failure():
    QApplication.instance() or QApplication([])
    worker = ChatStreamWorker(FakeClient(boom=True), "llama3", [])
    errors, done = [], []
    worker.error.connect(lambda m: errors.append(m))
    worker.finished.connect(lambda full: done.append(full))
    worker.run()
    assert errors and "stream broke" in errors[0]
    assert done == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_chat_worker.py -v`
Expected: FAIL (`No module named 'meister_guide.ai.worker'`).

- [ ] **Step 3: Implement**

Create `meister_guide/ai/worker.py`:

```python
"""QThread worker that streams an Ollama chat completion off the UI thread.
No DB — retrieval and persistence happen on the main thread."""
from PySide6.QtCore import QObject, Signal


class ChatStreamWorker(QObject):
    token = Signal(str)       # one streamed content chunk
    finished = Signal(str)    # the full assembled answer
    error = Signal(str)

    def __init__(self, client, model, messages):
        super().__init__()
        self._client = client
        self._model = model
        self._messages = messages

    def run(self):
        parts = []
        try:
            for chunk in self._client.chat(self._model, self._messages):
                parts.append(chunk)
                self.token.emit(chunk)
        except Exception as err:
            self.error.emit(str(err))
            return
        self.finished.emit("".join(parts))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_chat_worker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/worker.py tests/test_chat_worker.py
git commit -m "feat: ChatStreamWorker (background Ollama streaming)"
```

---

## Task 8: Chat tab UI + model detection

**Files:**
- Modify: `meister_guide/overlay/window.py`

- [ ] **Step 1: Extend `__init__` and imports**

In `meister_guide/overlay/window.py`, add to the `PySide6.QtWidgets` import block: `QTextEdit` (for the input is not needed — keep `QLineEdit`). Add these imports near the top (after the existing scraper import):

```python
import html as _html
from meister_guide.ai.passage import relevant_passage
from meister_guide.ai.prompt import build_messages
from meister_guide.ai.ollama_client import OllamaUnavailable, pick_model
from meister_guide.ai.worker import ChatStreamWorker
```

Extend `OverlayWindow.__init__` signature and attributes (keep existing params/order):

```python
    def __init__(self, settings: QSettings, games=None, articles_repo=None,
                 db_path=None, chat_repo=None, ollama_client=None):
```

Add alongside the other `self._...` assignments:

```python
        self._chat_repo = chat_repo
        self._ollama = ollama_client
        self._tabs = None
        self._guides_index = 1
        self._chat_session = None
        self._chat_view = []        # list of {"role", "text", "sources"}
        self._chat_thread = None
        self._chat_worker = None
        self._model = None
```

- [ ] **Step 2: Store tabs and build the Chat tab**

Replace `_build_tabs` in `window.py` so the Chat tab is real and `self._tabs` is stored:

```python
    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_chat_tab(), "Chat")
        tabs.addTab(self._build_guides_tab(), "Guides")
        settings = QLabel("Settings — coming in a later phase")
        settings.setAlignment(Qt.AlignCenter)
        settings.setContentsMargins(16, 16, 16, 16)
        tabs.addTab(settings, "Settings")
        self._tabs = tabs
        return tabs

    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(8)

        top = QHBoxLayout()
        self.chat_new_btn = QPushButton("New chat")
        self.chat_new_btn.clicked.connect(self._on_new_chat)
        top.addWidget(self.chat_new_btn)
        self.chat_history = QComboBox()
        self.chat_history.activated.connect(self._on_load_session)
        top.addWidget(self.chat_history, 1)
        col.addLayout(top)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenLinks(False)   # we handle guide: links ourselves
        self.chat_view.anchorClicked.connect(self._on_chat_anchor)
        col.addWidget(self.chat_view, 1)

        self.chat_status = QLabel("")
        self.chat_status.setObjectName("Disclaimer")
        self.chat_status.setWordWrap(True)
        col.addWidget(self.chat_status)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask Meister…")
        self.chat_input.returnPressed.connect(self._on_send)
        row.addWidget(self.chat_input, 1)
        self.chat_send_btn = QPushButton("Send")
        self.chat_send_btn.clicked.connect(self._on_send)
        row.addWidget(self.chat_send_btn)
        col.addLayout(row)

        self._refresh_history()
        self._detect_ollama()
        return page
```

- [ ] **Step 3: Add model detection + helpers**

Add these methods to `OverlayWindow`:

```python
    # ---- chat: model detection + state -----------------------------------
    def _detect_ollama(self):
        """Pick a model and set the input enabled/disabled state + status text."""
        if self._ollama is None:
            self._set_chat_enabled(False, "AI chat is unavailable.")
            return
        try:
            models = self._ollama.list_models()
        except OllamaUnavailable:
            self._set_chat_enabled(False,
                "Meister needs Ollama running at localhost:11434.")
            return
        self._model = pick_model(models)
        if self._model is None:
            self._set_chat_enabled(False,
                "No Ollama model installed. Run: ollama pull llama3")
            return
        note = ""
        if self._articles_repo is not None and self._articles_repo.count() == 0:
            note = "  (No guides loaded yet — run Update guides for better answers.)"
        self._set_chat_enabled(True, f"Model: {self._model}{note}")

    def _set_chat_enabled(self, enabled, status):
        self.chat_input.setEnabled(enabled)
        self.chat_send_btn.setEnabled(enabled)
        self.chat_status.setText(status)

    def _refresh_history(self):
        self.chat_history.blockSignals(True)
        self.chat_history.clear()
        self.chat_history.addItem("History…", None)
        if self._chat_repo is not None:
            for s in self._chat_repo.list_sessions():
                self.chat_history.addItem(s.title or f"Chat {s.id}", s.id)
        self.chat_history.blockSignals(False)
```

- [ ] **Step 4: Headless smoke check (detection states)**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; from meister_guide.overlay.window import OverlayWindow
class OkClient:
    def list_models(self): return ['llama3:latest']
class DownClient:
    def list_models(self):
        from meister_guide.ai.ollama_client import OllamaUnavailable
        raise OllamaUnavailable('refused')
app=QApplication([])
w=OverlayWindow(QSettings('MeisterGuide','T'), [], None, ':memory:', None, OkClient())
print('enabled:', w.chat_input.isEnabled(), '| model:', w._model)
w2=OverlayWindow(QSettings('MeisterGuide','T'), [], None, ':memory:', None, DownClient())
print('enabled:', w2.chat_input.isEnabled(), '| status:', w2.chat_status.text())"
```

Expected: first line `enabled: True | model: llama3:latest`; second `enabled: False | status: Meister needs Ollama running at localhost:11434.`

- [ ] **Step 5: Run full suite + commit**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS (no regressions).

```bash
git add meister_guide/overlay/window.py
git commit -m "feat: Chat tab scaffold with Ollama model detection + states"
```

---

## Task 9: Send → stream → sources → sessions

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test: `tests/test_window_chat.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_window_chat.py`:

```python
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.chat import ChatRepo
from meister_guide.db.articles import ArticlesRepo


class OkClient:
    def list_models(self):
        return ["llama3"]


def _window(tmp_path):
    conn = connect(tmp_path / "w.db")
    init_db(conn)
    arts = ArticlesRepo(conn)
    arts.add_article(1, "Creeper", "A creeper is a hostile mob that explodes.", 1, "u")
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), [], arts, ":memory:",
                      chat, OkClient())
    return w, chat


def test_streaming_handlers_render_and_persist(tmp_path):
    w, chat = _window(tmp_path)
    # Simulate a send having started: user + empty assistant bubble queued.
    w._begin_exchange("How do creepers work?", [(1, "Creeper")])
    w._on_chat_token("Creepers ")
    w._on_chat_token("explode.")
    w._on_chat_finished("Creepers explode.")

    html = w.chat_view.toHtml()
    assert "How do creepers work?" in html
    assert "Creepers explode." in html
    assert 'guide:1' in html                      # clickable source anchor
    # persisted: a session with the user + assistant messages
    sessions = chat.list_sessions()
    assert sessions
    msgs = chat.get_messages(sessions[0].id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "How do creepers work?"),
        ("assistant", "Creepers explode."),
    ]


def test_error_shows_message_and_persists_partial(tmp_path):
    w, chat = _window(tmp_path)
    w._begin_exchange("hi", [])
    w._on_chat_token("partial")
    w._on_chat_error("stream broke")
    html = w.chat_view.toHtml()
    assert "stream broke" in html
    msgs = chat.get_messages(chat.list_sessions()[0].id)
    assert msgs[-1].role == "assistant"           # partial persisted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_window_chat.py -v`
Expected: FAIL (`'OverlayWindow' object has no attribute '_begin_exchange'`).

- [ ] **Step 3: Implement send, streaming handlers, rendering, sources, sessions**

Add these methods to `OverlayWindow` in `window.py`. `_begin_exchange` is factored out so it (and the streaming handlers) are unit-testable without a live thread; `_on_send` wires retrieval + the worker thread on top.

```python
    # ---- chat: conversation ---------------------------------------------
    def _ensure_session(self):
        if self._chat_session is None and self._chat_repo is not None:
            self._chat_session = self._chat_repo.create_session()
        return self._chat_session

    def _begin_exchange(self, question, sources):
        """Record the user turn + an empty assistant turn, persist the user
        message, and render. `sources` is a list of (pageid, title)."""
        self._ensure_session()
        if self._chat_repo is not None:
            self._chat_repo.add_message(self._chat_session, "user", question)
            if len(self._chat_repo.get_messages(self._chat_session)) == 1:
                self._chat_repo.set_title(self._chat_session, question[:40])
                self._refresh_history()
        self._chat_view.append({"role": "user", "text": question, "sources": []})
        self._chat_view.append({"role": "assistant", "text": "", "sources": sources})
        self._render_chat()

    def _on_send(self):
        if not self.chat_input.isEnabled() or self._chat_thread is not None:
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_input.clear()

        sources, passages = [], []
        if self._articles_repo is not None:
            for hit in self._articles_repo.search(question, limit=3):
                article = self._articles_repo.get_article(hit.pageid)
                if article is None:
                    continue
                sources.append((hit.pageid, hit.title))
                passages.append((hit.title, relevant_passage(article.body, question)))

        history = [(m["role"], m["text"]) for m in self._chat_view if m["text"]]
        self._begin_exchange(question, sources)
        messages = build_messages(question, passages, history)

        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        self._chat_thread = QThread(self)
        self._chat_worker = ChatStreamWorker(self._ollama, self._model, messages)
        self._chat_worker.moveToThread(self._chat_thread)
        self._chat_thread.started.connect(self._chat_worker.run)
        self._chat_worker.token.connect(self._on_chat_token)
        self._chat_worker.finished.connect(self._on_chat_finished)
        self._chat_worker.error.connect(self._on_chat_error)
        self._chat_thread.start()

    def _on_chat_token(self, chunk):
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["text"] += chunk
            self._render_chat()

    def _on_chat_finished(self, full_text):
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["text"] = full_text or self._chat_view[-1]["text"]
        if self._chat_repo is not None and self._chat_session is not None:
            self._chat_repo.add_message(self._chat_session, "assistant",
                                        self._chat_view[-1]["text"])
        self._render_chat()
        self._teardown_chat_thread()

    def _on_chat_error(self, message):
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            partial = self._chat_view[-1]["text"]
            self._chat_view[-1]["text"] = (partial + f"\n\n[error: {message}]").strip()
            if self._chat_repo is not None and self._chat_session is not None:
                self._chat_repo.add_message(self._chat_session, "assistant",
                                            self._chat_view[-1]["text"])
        self._render_chat()
        self._teardown_chat_thread()

    def _teardown_chat_thread(self):
        if self._chat_thread is not None:
            self._chat_thread.quit()
            self._chat_thread.wait()
        self._chat_thread = None
        self._chat_worker = None
        self.chat_input.setEnabled(True)
        self.chat_send_btn.setEnabled(True)

    def _render_chat(self):
        parts = []
        for msg in self._chat_view:
            who = "You" if msg["role"] == "user" else "Meister"
            body = _html.escape(msg["text"]).replace("\n", "<br>")
            parts.append(f"<p><b>{who}:</b> {body}</p>")
            if msg["sources"]:
                links = " · ".join(
                    f'<a href="guide:{pid}">{_html.escape(title)}</a>'
                    for pid, title in msg["sources"]
                )
                parts.append(f'<p style="color:#9a7b53">Sources: {links}</p>')
        self.chat_view.setHtml("\n".join(parts))

    def _on_chat_anchor(self, url):
        ref = url.toString()
        if ref.startswith("guide:"):
            try:
                pageid = int(ref.split(":", 1)[1])
            except ValueError:
                return
            self._open_guide(pageid)

    def _open_guide(self, pageid):
        if self._articles_repo is None:
            return
        article = self._articles_repo.get_article(pageid)
        if article is None:
            return
        self.guides_detail.setPlainText(article.body)
        if self._tabs is not None:
            self._tabs.setCurrentIndex(self._guides_index)

    def _on_new_chat(self):
        self._chat_session = None
        self._chat_view = []
        self._render_chat()
        if self._chat_repo is not None:
            self._chat_session = self._chat_repo.create_session()
            self._refresh_history()

    def _on_load_session(self, index):
        session_id = self.chat_history.itemData(index)
        if session_id is None or self._chat_repo is None:
            return
        self._chat_session = session_id
        self._chat_view = [
            {"role": m.role, "text": m.content, "sources": []}
            for m in self._chat_repo.get_messages(session_id)
        ]
        self._render_chat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest tests/test_window_chat.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run full suite**

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_chat.py
git commit -m "feat: chat send/stream with citations and persisted sessions"
```

---

## Task 10: Wire main.py + README

**Files:**
- Modify: `meister_guide/main.py`
- Modify: `README.md`

- [ ] **Step 1: Build ChatRepo + OllamaClient and pass to the overlay**

In `meister_guide/main.py`, add imports near the other db/ai imports:

```python
from meister_guide.db.chat import ChatRepo
from meister_guide.ai.ollama_client import OllamaClient
```

Where the repos are built and the overlay is constructed, add the chat repo + client and pass them in. The current block ends with the `OverlayWindow(...)` call from Phase 3; change it to:

```python
    articles_repo = ArticlesRepo(conn)
    chat_repo = ChatRepo(conn)
    ollama_client = OllamaClient()

    overlay = OverlayWindow(settings, games_repo.list_games(),
                            articles_repo=articles_repo,
                            db_path=default_db_path(),
                            chat_repo=chat_repo,
                            ollama_client=ollama_client)
```

- [ ] **Step 2: Document the Chat tab in README.md**

Add a section after the "Guides (offline wiki)" section:

```markdown
## Meister (AI chat)
The Chat tab answers Minecraft questions using a local [Ollama](https://ollama.com)
model. Install Ollama and pull a model (`ollama pull llama3`), then ask away —
Meister retrieves the 3 most relevant offline guide passages, streams an answer,
and lists the source guides (click one to open it in the Guides tab). If Ollama
isn't running you'll see a prompt to start it. Chats are saved; use **New chat**
to start fresh or the history dropdown to reopen a past conversation.
```

- [ ] **Step 3: Verify wiring (headless) + full suite**

Byte-compile and smoke-construct as `main` does:

```bash
py -3 -m py_compile meister_guide/main.py
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -c "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; from meister_guide.db.database import connect, init_db, default_db_path; from meister_guide.db.articles import ArticlesRepo; from meister_guide.db.chat import ChatRepo; from meister_guide.overlay.window import OverlayWindow
class C:
    def list_models(self): return []
app=QApplication([]); cn=connect(':memory:'); init_db(cn)
w=OverlayWindow(QSettings('MeisterGuide','T'), [], ArticlesRepo(cn), ':memory:', ChatRepo(cn), C())
print('chat tab built; status:', w.chat_status.text())"
```

Expected: prints a status like `No Ollama model installed. Run: ollama pull llama3` (empty model list), no exception.

Run: `QT_QPA_PLATFORM=offscreen py -3 -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Manual end-to-end verification (real app, needs Ollama)**

Run: `.\run.bat` (with Ollama running and a model pulled, and guides ingested).

Checklist:
1. Chat tab shows `Model: <name>`; if Ollama is off, shows the needs-Ollama message and the input is disabled.
2. Ask "how do creepers work?" → answer streams in token by token.
3. Source guide titles appear under the answer; clicking one opens it in the Guides tab.
4. **New chat** clears the transcript; the previous chat appears in the history dropdown and reopens with its messages.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/main.py README.md
git commit -m "feat: wire Meister chat into the app + document it"
```

---

## Self-Review

**Spec coverage:**
- Ollama client (`/api/tags`, streaming `/api/chat`, connection error) → Tasks 3, 4. ✓
- Model auto-detect + preference → Task 3 (`pick_model`), Task 8 (`_detect_ollama`). ✓
- RAG relevance-windowed plain-text passages → Tasks 1, 2; used in Task 9 `_on_send`. ✓
- Prompt with excerpts + history + question → Task 5. ✓
- ChatRepo sessions/messages → Task 6. ✓
- Streaming worker (token/finished/error, no DB) → Task 7. ✓
- Chat tab: transcript, input, send, New chat, history dropdown, states → Tasks 8, 9. ✓
- Clickable sources → Guides tab → Task 9 (`guide:` anchors, `_open_guide`). ✓
- Error states (Ollama down, no model, stream error, no guides) → Tasks 8, 9. ✓
- Main-thread retrieval + worker-only streaming → Task 9. ✓
- Wiring + docs → Task 10. ✓

**Placeholder scan:** none — every step has full code; the one manual step (Task 10 Step 4) is real-app verification with an explicit checklist.

**Type consistency:** `OllamaClient(base_url, http_get, http_post)`, `list_models()->list[str]`, `chat(model, messages)->Iterator[str]`, `pick_model(names)`, `relevant_passage(body, query, width)`, `build_messages(question, passages, history)`, `ChatRepo.create_session/add_message/set_title/list_sessions/get_messages`, `ChatStreamWorker(client, model, messages)` with `token/finished/error`, and the `self._chat_view` item shape `{"role","text","sources"}` are used consistently across tasks. `_begin_exchange(question, sources)` with `sources=list[(pageid,title)]` matches `_render_chat` and the `guide:<pageid>` anchor parsed by `_on_chat_anchor`.

**Note for executor:** Task 8 references handlers defined in Task 9 (`_on_send`, `_on_new_chat`, `_on_load_session`, `_on_chat_anchor`). Implement Task 8 then Task 9 before running the Task 8 smoke check at the end of Task 9, OR add temporary `pass` stubs for those four methods in Task 8 (replaced in Task 9) so the Task 8 smoke check runs. The detection smoke check in Task 8 Step 4 only needs `_detect_ollama`/`_set_chat_enabled`/`_refresh_history`, which Task 8 defines.
