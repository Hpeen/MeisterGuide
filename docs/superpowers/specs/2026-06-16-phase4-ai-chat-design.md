# Design — Phase 4: Meister AI Chat (Ollama + RAG)

**Date:** 2026-06-16
**Status:** Approved (design), ready to plan
**Builds on:** Phase 3 (`ArticlesRepo` + FTS5 guides), the overlay shell, and the
Phase 2 `chat_sessions`/`chat_messages` tables.

## Goal

A local AI assistant ("Meister") in the Chat tab: the user asks a question, the
app retrieves the 3 most relevant guide passages from the offline FTS5 index,
sends them plus the conversation to a local Ollama model, and streams the answer
back. Answers cite the guides used (clickable → Guides tab). Conversations are
persisted with a New-chat button and a session-history list. Clear states when
Ollama isn't running or no model is installed.

## Locked decisions (from brainstorming)

- **Backend:** Ollama at `http://localhost:11434`; streaming `POST /api/chat`;
  model discovery via `GET /api/tags`.
- **Model selection:** auto-detect installed models; prefer one named `llama3*`,
  else the first installed; none installed → "pull a model" state.
- **RAG context:** for each of the top-3 FTS hits, inject the title + a
  ~1500-char plain-text passage centred on the query match (a plain-text sibling
  of the UI excerpt). Keeps the prompt small enough for any local model.
- **Citations:** show the 3 source guide titles under each answer; clicking one
  opens it in the Guides tab.
- **Sessions:** persisted in `chat_sessions`/`chat_messages`; a "New chat" button
  starts a session; a history dropdown reopens past sessions.
- **Threading:** FTS retrieval + DB writes happen on the main thread (fast); only
  the Ollama stream runs on a `QThread` (token signals), so the overlay stays
  responsive.

## Components

Each unit has one responsibility and is testable in isolation. New package
`meister_guide/ai/`, plus `meister_guide/db/chat.py`.

### 1. `meister_guide/ai/ollama_client.py` — Ollama HTTP client (pure)
- `class OllamaUnavailable(Exception)` — raised when Ollama can't be reached.
- `OllamaClient(base_url="http://localhost:11434", http_get=None, http_post=None)`
  — HTTP callables injectable for tests; default to `requests` with a timeout.
- `list_models() -> list[str]`: `GET /api/tags`, return `m["name"]` for each
  model in `models`. Connection failure → `OllamaUnavailable`.
- `chat(model, messages) -> Iterator[str]`: `POST /api/chat` with
  `{"model", "messages", "stream": True}`; iterate response lines, JSON-decode
  each, yield `obj["message"]["content"]`, stop when `obj.get("done")` is true.
  Connection failure → `OllamaUnavailable`.
- `pick_model(names) -> str | None` (module function): first name starting with
  `"llama3"`, else `names[0]`, else `None`.

### 2. `meister_guide/scraper/excerpt.py` (refactor) + `meister_guide/ai/passage.py`
- Extract the window-finding from `make_excerpt` into
  `window_bounds(body, query, width) -> (start, end)` in `excerpt.py`;
  `make_excerpt` keeps its HTML-escape + `<b>` highlighting on top of it (no
  behaviour change — existing tests stay green).
- `ai/passage.py`: `relevant_passage(body, query, width=1500) -> str` — uses
  `window_bounds` and returns **plain text** (with `…` ellipses), for the model.

### 3. `meister_guide/ai/prompt.py` — prompt builder (pure)
- `build_messages(question, passages, history) -> list[dict]` where
  `passages` is `list[(title, text)]` and `history` is `list[(role, content)]`.
- Returns `[{"role":"system","content": <instructions + guide excerpts block>},
  *history, {"role":"user","content": question}]`. System prompt: identify as
  Meister, answer from the supplied Minecraft guide excerpts, say so if they
  don't cover the question. Excerpts formatted as `[Title]\n<passage>` blocks.

### 4. `meister_guide/db/chat.py` — `ChatRepo`
- Dataclasses `ChatSession(id, title, started_at)`, `ChatMessage(role, content)`.
- `create_session(game_id=None, title=None) -> int`;
  `add_message(session_id, role, content) -> int`;
  `set_title(session_id, title)`; `list_sessions() -> list[ChatSession]`
  (newest first); `get_messages(session_id) -> list[ChatMessage]` (chronological).

### 5. `meister_guide/ai/worker.py` — `ChatStreamWorker(QObject)`
- `__init__(client, model, messages)`; signals `token(str)`, `finished(str)`
  (full text), `error(str)`. `run()` iterates `client.chat(model, messages)`,
  emits each `token`, accumulates, emits `finished`; on `OllamaUnavailable`/any
  exception emits `error`. No DB (pure streaming).

### 6. Chat tab UI (`meister_guide/overlay/window.py`)
- Replace the placeholder Chat tab: a transcript view (`QTextBrowser`), an input
  `QLineEdit` + **Send** (Enter sends), a **New chat** button, and a
  **session-history** `QComboBox`.
- **Send flow** (main thread): retrieve `articles_repo.search(q, 3)` → build
  passages via `relevant_passage` → `prompt.build_messages(...)` with prior turns
  → persist the user message → append a user bubble + an empty assistant bubble →
  start `ChatStreamWorker` on a `QThread`. `token` appends to the assistant
  bubble live; `finished` persists the assistant message and renders the **3
  clickable source titles**; `error` shows the failure in the assistant bubble.
- **Sources** click → switch to the Guides tab and show that article
  (reuse the Guides detail panel via the stored `pageid`).
- **New chat** → `create_session()`, clear the transcript. First user message of
  a session sets its title (truncated). **History dropdown** → `list_sessions()`;
  selecting one loads `get_messages` into the transcript.
- **States:** on tab build (and before each Send) probe `list_models()`:
  `OllamaUnavailable` → disable input, show "Meister needs Ollama running at
  localhost:11434"; reachable but empty → "Install a model: `ollama pull
  llama3`"; otherwise store the picked model. If `articles_repo.count()==0`,
  still answer but prepend a "no guides loaded yet — answers may be limited" note.

## Data flow

```
Send(question)
  main: hits = ArticlesRepo.search(question, 3)
        passages = [(h.title, relevant_passage(get_article(h.pageid).body, question)) ...]
        messages = prompt.build_messages(question, passages, history)
        ChatRepo.add_message(session, "user", question)
        ChatStreamWorker(client, model, messages) on QThread
  token -> append to assistant bubble
  finished(text) -> ChatRepo.add_message(session, "assistant", text)
                 -> render clickable sources (hits' titles + pageids)
```

## Error handling
- **Ollama down:** `OllamaUnavailable` → input disabled + clear "needs Ollama"
  message; existing transcript/history still viewable.
- **No models installed:** "pull a model" hint, input disabled.
- **Stream fails mid-answer:** `error` signal → show partial text + an error line;
  the partial assistant message is still persisted so history is consistent.
- **No guides ingested:** answer ungrounded, with a one-line note nudging the user
  to run Update guides.
- **Empty/whitespace question:** ignored (no send).

## Testing
- `ollama_client`: fake `http_get`/`http_post` → `list_models` parses `/api/tags`;
  `chat` parses an NDJSON stream into content chunks and stops on `done`;
  connection error → `OllamaUnavailable`; `pick_model` preference order.
- `passage`: plain-text window around a match, ellipses, no-match fallback,
  width clamping; and `excerpt.make_excerpt` still passes after the refactor.
- `prompt`: message array shape — system-with-excerpts first, history in order,
  user question last.
- `chat_repo` (in-memory SQLite): session + message CRUD, ordering, title set.
- `worker`: fake client → `token`/`finished` sequence; error path emits `error`,
  not `finished`.
- Chat tab: headless smoke — construct with stub client + repos, send a question,
  assert streamed text lands in the transcript and clickable sources appear;
  "needs Ollama" state when the client raises.

## Out of scope (later)
- Model picker UI, temperature/params, Claude API backend (Phase 5 Settings).
- Embeddings/vector RAG (FTS5 keyword retrieval is the beta approach).
- Per-message regeneration, editing, or streaming-cancel (New chat suffices).
