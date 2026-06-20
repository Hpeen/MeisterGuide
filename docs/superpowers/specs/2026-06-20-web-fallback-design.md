# SP2b — Web-search fallback (design)

**Date:** 2026-06-20
**Status:** Approved, ready for planning
**Predecessors:** SP2a on-demand wiki fetch (`docs/superpowers/specs/2026-06-19-on-demand-fetch-design.md`), SP3 category seed (`docs/superpowers/specs/2026-06-20-category-seed-design.md`)

## Problem

The hybrid knowledge model now fills gaps two ways: a full/seed corpus and SP2a's
on-demand wiki fetch on a chat miss. Both depend on the active game having a
usable wiki. Queries the wiki can't answer — or games with no `wiki_url` at all —
still come up empty. SP2b adds the final fallback: a **keyed web search + scrape**
that ingests the top results scoped to the game and answers through the existing
RAG path. This is the explicit non-goal that SP2a punted.

## Decisions (locked during brainstorming)

- **Source:** keyed search API + scrape (not keyless, not the Claude web-search
  tool). Keeps SP2b consistent with the SP2a/SP3 search→fetch→ingest→RAG pattern
  and backend-agnostic (works with Ollama or Claude).
- **Provider:** **Brave Search API** — single API key, REST endpoint, free tier.
- **Gating:** a "web fallback" preference that **defaults on once a Brave key is
  set** and can be paused via a Settings checkbox without deleting the key.
  Effective-enabled = key present AND pref not explicitly off.
- **Extraction dependency:** add **`trafilatura`** for main-text extraction.
- **Web page storage:** synthetic `pageid` derived from the URL (the `articles`
  schema requires `pageid INTEGER UNIQUE NOT NULL`).

## Non-goals

- Keyless/scraped-SERP search; the Claude web-search tool; multiple providers
  (Brave only — no provider abstraction, YAGNI).
- Changing the answer/RAG path: SP2b only adds a corpus source; answering is
  unchanged.
- Re-ranking web results against wiki results, freshness/expiry of stored web
  pages, or a web-page management UI. Out of scope.
- Redirects or noise-title heuristics for web pages (those are wiki-specific).

## Trigger chain (last resort)

In `window._on_send`, the miss path becomes a chain. For a chat send:

1. **Local hits** for the active game → answer now (unchanged).
2. **0 hits + game has `wiki_url`** → wiki fetch (SP2a, unchanged) → in the
   post-fetch step, if **still 0 hits and web fallback is enabled** → web fetch →
   answer.
3. **0 hits + no `wiki_url` + web fallback enabled** → web fetch directly →
   answer.
4. **Otherwise** → answer from the local corpus (unchanged; empty corpus yields
   the existing "no info" answer).

To keep this in one place, factor a helper:

```
_answer_or_web_fallback(question, history):
    sources, passages = _retrieve(question)
    if sources or not <web fallback enabled>:
        _begin_exchange + build_messages + _start_chat_worker   # answer now
    else:
        _start_web_fetch(question, history)                     # then answer in its done handler
```

- `_on_send` calls `_answer_or_web_fallback` for the no-wiki / not-fetchable
  branch (replacing today's direct-answer call there).
- `_on_fetch_done` (after the wiki fetch) calls `_answer_or_web_fallback` instead
  of always answering, so an empty wiki fetch escalates to web.
- `_start_web_fetch` mirrors `_start_fetch`: shows "Searching the web…", disables
  input, runs `WebFetchWorker` off-thread; both its `finished` and `error` paths
  route to `_on_web_fetch_done`, which re-retrieves and answers (empty → no
  passages, still answers — never crashes).

"Web fallback enabled" = `settings_repo.web_fallback_enabled()` (see Settings).

## Settings

Extend `meister_guide/db/settings.py::SettingsRepo`:

- Add defaults: `"brave_api_key": ""`, `"web_fallback": "1"`.
- `brave_api_key()` → `get("brave_api_key")`.
- `web_fallback_enabled()` → `bool(brave_api_key()) and get("web_fallback") != "0"`.
  (Defaults on when a key is present; the checkbox writes `"1"`/`"0"`.)

UI on the ⚙ Settings tab, near the Claude key block: a masked **Brave API key**
field and an **"Allow web search fallback"** checkbox. Saved by the existing
"Save backend settings" button (extend `_on_save_settings` to persist both). The
checkbox's initial checked state reflects `get("web_fallback") != "0"`.

## Components (parallel to the SP2a stack)

### 1. `scraper/web_search.py::BraveSearchClient`

```
BraveSearchClient(api_key, http_get=None)
    search(query, count=3) -> list[(title, url)]
```

- Calls `https://api.search.brave.com/res/v1/web/search` with header
  `X-Subscription-Token: <api_key>` and params `q`, `count`.
- Parses `web.results[]` → `(title, url)` pairs; returns `[]` on no results.
- Pure: `http_get(url, headers, params)` is injectable so tests run without
  network. The real default uses `requests.get(timeout=30)` and
  `raise_for_status()`. Surfaces API errors as exceptions for the worker to
  catch.

### 2. `scraper/web_fetch.py::fetch_main_text`

```
fetch_main_text(url, http_get=None) -> (title, text)
```

- Downloads the page HTML (`http_get` injectable; real default
  `requests.get(timeout=30, headers={"User-Agent": ...})`).
- Extracts main text with `trafilatura.extract(html)`; title via
  `trafilatura.extract_metadata(html).title` (fall back to the URL host if the
  extractor returns no title).
- Returns `("", "")` (or `(title, "")`) when extraction yields nothing, so the
  caller can skip it. Does not raise on empty extraction; only network errors
  propagate.

### 3. `scraper/web_ingest.py::run_web_fetch` (pure orchestrator)

```
run_web_fetch(search_client, fetch_fn, articles_repo, game_id, query,
              limit=3, min_chars=200, should_cancel=None) -> int
```

- `results = search_client.search(query, limit)`.
- For each `(title, url)` (up to `limit`):
  - poll `should_cancel()` → break.
  - `page_title, text = fetch_fn(url)`.
  - skip if `len(text.strip()) < min_chars` (boilerplate/empty pages).
  - `pageid = web_pageid(url)` (synthetic; see below).
  - `articles_repo.add_article(pageid, page_title or title or url, text,
    revid=None, url=url, game_id=game_id)` — idempotent by pageid.
  - count newly-inserted (True) rows.
- Return the count. `should_cancel` polled between the search call and each fetch
  (SP2a parity).

**Synthetic pageid** — add to `scraper/urls.py` (the shared helper module):

```
def web_pageid(url):
    """Stable positive int id for a web page (articles.pageid is UNIQUE NOT NULL
    INTEGER and wiki pageids are small (<1e8), so a ~60-bit hash never collides)."""
    import hashlib
    return int(hashlib.sha1(url.encode("utf-8")).hexdigest()[:15], 16)
```

### 4. `scraper/worker.py::WebFetchWorker`

Sibling of `OnDemandFetchWorker`:

```
WebFetchWorker(db_path, game_id, query, api_key, limit=3, client=None, fetch_fn=None)
    finished(int)   # articles ingested
    error(str)
    cancel()
```

- `run()`: own SQLite conn + `init_db`; builds `BraveSearchClient(api_key)` (or
  injected `client`) and uses `fetch_main_text` (or injected `fetch_fn`); calls
  `run_web_fetch(...)` with `should_cancel=lambda: self._cancel`; emits
  `finished(n)` or `error(str(err))`; closes conn in `finally`.

### 5. `window.py` integration

- `__init__`: add `self._web_thread = None`, `self._web_worker = None`.
- Import `WebFetchWorker`.
- Add `_answer_or_web_fallback`, `_start_web_fetch`, `_on_web_fetch_done`,
  `_teardown_web_thread` (mirror the fetch-thread lifecycle, `wait(5000)`).
- Re-entry guard: `_on_send` already returns if `_fetch_thread`/`_chat_thread`
  are active; also return if `_web_thread is not None`.
- Cancel hooks: `hideEvent` and `shutdown` cancel `_web_worker` if present;
  `shutdown` also calls `_teardown_web_thread`.
- The cancelled-path handling matches the wiki fetch (`_chat_cancelled` guard,
  restore input).

## Error handling

- No key / web fallback disabled → the chain never enters web fetch; answers from
  local (unchanged behavior).
- Brave API error, network offline, or all scrapes empty → `WebFetchWorker`
  emits `error` (or `finished(0)`); `_on_web_fetch_done` still re-retrieves and
  answers (empty corpus → existing "no info" answer). No crash.
- Cancel (hide/quit) mid-chain aborts before the next network call and restores
  the chat input.

## Dependencies

- Add `trafilatura` (pulls `lxml`) to the project dependencies (e.g.
  `requirements.txt` / `pyproject` as the project already lists `requests`,
  `anthropic`). `requests` is already present. Brave needs no SDK (plain REST).

## Testing (TDD, mirrors SP2a ~20 tests)

- **`run_web_fetch`** (fake search client + fake `fetch_fn` + real SQLite repo):
  ingests results scoped to game with the source URL stored; skips pages under
  `min_chars`; `limit` cap; idempotent re-run (synthetic pageid dedupe); returns
  zero and makes no fetch when search is empty; `should_cancel` stops mid-walk;
  counts only newly-inserted rows.
- **`web_pageid`** (in `scraper/urls.py` tests): stable for the same URL, distinct
  for different URLs, positive, well above 1e8 (no wiki collision).
- **`BraveSearchClient.search`** (fake `http_get`): sends the subscription-token
  header and `q`/`count`; parses `web.results`; respects `count`; returns `[]`
  when empty.
- **`fetch_main_text`** (fake `http_get`): returns `(title, text)` for good HTML;
  returns empty text for unextractable HTML without raising.
- **`WebFetchWorker`** (injected fake client + fetch_fn): emits `finished(count)`;
  emits `error` on exception; `cancel()` honored.
- **`SettingsRepo`**: `brave_api_key` default ""; `web_fallback_enabled` True when
  key set and pref not "0", False when no key or pref "0".
- **Window** (offscreen): no-key/disabled → no web thread, answers locally;
  web-only path (no wiki_url) starts a web fetch; wiki→web chain (empty wiki
  fetch escalates) — handlers/lifecycle exercised directly per the existing
  `test_window_*` style; shutdown cancels an active web worker.

## Build approach

One feature branch (`web-fallback`), TDD per task, subagent-driven with two-stage
review (spec + quality) per task and a final whole-branch review, then
`finishing-a-development-branch`. Run tests with `py -m pytest -q`.
