# Free web-search provider (DuckDuckGo) + online-first repositioning (design)

**Date:** 2026-06-20
**Status:** Approved, ready for planning
**Extends:** SP2b web-search fallback (`docs/superpowers/specs/2026-06-20-web-fallback-design.md`)

## Problem

SP2b shipped web fallback gated behind a **Brave** API key. As of February 2026
Brave removed its free tier (now a metered, card-required plan), so SP2b is not
usable for free. This change adds a **keyless DuckDuckGo provider** so web
fallback works with zero setup, makes web fallback **on by default**, and
**repositions the app** so reaching the web is the default story and offline is a
named *mode* rather than the headline.

## Decisions (locked during brainstorming)

- **Provider selection: auto by key.** A Brave key → use Brave; no key → use
  keyless DuckDuckGo. No provider dropdown (YAGNI).
- **Web fallback default ON.** The "Allow web search fallback" checkbox becomes a
  pause switch, not an opt-in. Gating no longer requires a key.
- **Reposition copy:** offline becomes "a mode," not the main focus — applied to
  the footer tagline and the web-fallback control help text. The backend combo
  is left as-is (already online-first).
- **Dependency:** add `ddgs` (the maintained successor to `duckduckgo_search`),
  lazy-imported like `trafilatura`.

## Non-goals

- Provider dropdown / forcing DuckDuckGo while a Brave key is on file (remove the
  key to switch). Multiple keyless providers. Re-ranking web vs wiki results.
  README/marketing-site copy (only in-app strings are in scope).

## Components

### 1. `scraper/web_search.py::DuckDuckGoSearchClient`

Same interface as `BraveSearchClient` so it's a drop-in for `run_web_fetch`:

```
DuckDuckGoSearchClient(search_fn=None)
    search(query, count=3) -> list[(title, url)]
```

- Default `search_fn` lazy-imports `ddgs`:
  `from ddgs import DDGS; return DDGS().text(query, max_results=count)` — a list of
  dicts with `title` / `href` / `body`.
- `search` maps each result to `(r.get("title") or href, href)`, skips entries
  with no `href`, and caps at `count`.
- `search_fn` is injectable so tests need neither `ddgs` nor a network (mirrors
  Brave's `http_get` and trafilatura's `extract` seams). Network/library errors
  propagate for the worker to catch.

### 2. `scraper/web_search.py::make_search_client(brave_api_key)`

```
def make_search_client(brave_api_key):
    return BraveSearchClient(brave_api_key) if brave_api_key else DuckDuckGoSearchClient()
```

A single place that encodes "auto by key." Returns a client exposing
`.search(query, count)`.

### 3. `WebFetchWorker` (worker.py) — one-line change

`run()` builds the client via the factory instead of hardcoding Brave:

```
client = self._client or make_search_client(self._api_key)
```

The `api_key` constructor param stays (empty string → DuckDuckGo). The injected
`client`/`fetch_fn` test seams are unchanged. `window._start_web_fetch` still
passes `self._settings_repo.brave_api_key()` (empty when unset → DDG).

### 4. Gating — `SettingsRepo`

- `web_fallback` default stays `"1"` (already the default) → **ON**.
- `web_fallback_enabled()` drops the key requirement:

```
def web_fallback_enabled(self):
    """Web fallback is on unless the user paused it. Default on. The provider is
    chosen by make_search_client (Brave if a key is set, else free DuckDuckGo)."""
    return self.get("web_fallback") != "0"
```

- `brave_api_key()` stays — it now only *selects the provider*, never gates.
- `window._web_enabled()` is unchanged (already defers to
  `web_fallback_enabled()`), so it's now true by default.

### 5. Repositioning copy (window.py)

**Footer** (`_refresh_footer`): make the "reaching out" flag also reflect web
fallback, and reword so offline reads as a mode:

```
online = (backend == BACKEND_CLAUDE or (backend == BACKEND_AUTO and key)
          or (self._settings_repo is not None
              and self._settings_repo.web_fallback_enabled()))
self.footer_note.setText(
    "online · web-augmented" if online
    else "offline mode · runs locally")
```

**Web-fallback controls** (`_build_settings_tab`):
- Brave key field help text → `"optional — leave blank to use free DuckDuckGo"`.
- Checkbox label stays `"Allow web search fallback"` (now ticked by default via
  the existing `get("web_fallback") != "0"` initial state).

Backend combo strings unchanged.

### 6. Dependency

Add to `requirements.txt` after the `trafilatura` line:

```
ddgs>=6.0  # web-fallback (SP2b) free keyless DuckDuckGo search; lazy-imported
```

## Error handling

- `ddgs` not installed or DuckDuckGo rate-limits/errors → the search call raises;
  `WebFetchWorker` catches it and emits `error`; `_on_web_fetch_done` still
  re-retrieves and answers from the local corpus (empty → existing "no info"
  answer). No crash. Same resilience as the Brave path.
- Caveat (documented, accepted): DuckDuckGo via `ddgs` is an unofficial scraped
  endpoint and can rate-limit or break; Brave remains the reliable keyed upgrade.

## Testing (TDD)

**New**
- `DuckDuckGoSearchClient.search` (inject `search_fn`): parses `title`/`href`
  pairs; caps at `count`; skips results with no `href`; title falls back to href;
  empty list when no results.
- `make_search_client`: returns a `BraveSearchClient` when a key is given, a
  `DuckDuckGoSearchClient` when the key is empty/None.

**Updated (SP2b gating semantics changed)**
- `tests/test_settings_web.py`: web fallback is **on by default**; enabled
  regardless of key; off only when pref is `"0"`; `brave_api_key()` still
  defaults empty. (Replaces the old key-gated assertions.)
- `tests/test_window_web.py`: `_web_enabled()` is true by default with **no key**;
  false when `web_fallback` pref is `"0"`. The existing chain tests
  (hits-answer-without-web, miss-with-web-enabled-starts-web, web-disabled-answers)
  still hold; adjust any that relied on a key to enable.
- `tests/test_shell_window.py`: footer reads `"online · web-augmented"` when web
  fallback is on (default) or an online chat backend is active, and
  `"offline mode · runs locally"` when the backend is local **and** web fallback
  is paused.

**Unchanged**
- `WebFetchWorker` tests still inject a `client`, so they don't exercise the
  factory; `make_search_client` is covered directly.

## Build approach

One feature branch (`free-web-search`), TDD per task, subagent-driven with
two-stage review (spec + quality) per task and a final whole-branch review, then
`finishing-a-development-branch`. Run tests with `py -m pytest -q`.
