# Free DuckDuckGo Web Search + Online-First Repositioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make web fallback work for free (keyless DuckDuckGo) and on by default, auto-upgrading to Brave when a key is set, and reposition the app's copy so reaching the web is the default story and offline is a named mode.

**Architecture:** Add a `DuckDuckGoSearchClient` with the same `(title, url)` interface as `BraveSearchClient`, plus a `make_search_client(brave_api_key)` factory that picks Brave-with-key-else-DDG; `WebFetchWorker` uses the factory. `SettingsRepo.web_fallback_enabled()` drops the key requirement (default on). The footer tagline and the Brave key field help are reworded for the online-first positioning.

**Tech Stack:** Python, PySide6 (Qt), `ddgs` (keyless DuckDuckGo, lazy-imported), `requests`/Brave, pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-free-web-search-design.md`

**Test runner:** `py -m pytest -q` (use `py`, not `python`).

---

## File Structure

- **Modify** `meister_guide/scraper/web_search.py` — `DuckDuckGoSearchClient` + `make_search_client`.
- **Modify** `meister_guide/scraper/worker.py` — `WebFetchWorker` builds its client via `make_search_client`.
- **Modify** `requirements.txt` — add `ddgs`.
- **Modify** `meister_guide/db/settings.py` — `web_fallback_enabled()` no longer needs a key.
- **Modify** `meister_guide/overlay/window.py` — footer repositioning + key-field help text.
- **Create** `tests/test_web_search_ddg.py`.
- **Rewrite** `tests/test_settings_web.py` (gating semantics changed).
- **Update** `tests/test_window_web.py` and `tests/test_shell_window.py` (default-on + footer copy).

---

## Task 1: DuckDuckGo client + provider factory + worker wiring

**Files:**
- Modify: `meister_guide/scraper/web_search.py`
- Modify: `meister_guide/scraper/worker.py`
- Modify: `requirements.txt`
- Test: `tests/test_web_search_ddg.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_search_ddg.py`:

```python
from meister_guide.scraper.web_search import (
    DuckDuckGoSearchClient, make_search_client, BraveSearchClient,
)


def test_ddg_parses_title_href_pairs():
    def fake_search(query, count):
        return [{"title": "Tame a wolf", "href": "https://x/wolf", "body": "..."},
                {"title": "Bone", "href": "https://x/bone", "body": "..."}]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert client.search("wolf") == [
        ("Tame a wolf", "https://x/wolf"), ("Bone", "https://x/bone")]


def test_ddg_passes_query_and_count():
    seen = {}
    def fake_search(query, count):
        seen["query"], seen["count"] = query, count
        return []
    DuckDuckGoSearchClient(search_fn=fake_search).search("how to tame", count=2)
    assert seen == {"query": "how to tame", "count": 2}


def test_ddg_respects_count_limit():
    def fake_search(query, count):
        return [{"title": f"T{i}", "href": f"https://x/{i}"} for i in range(10)]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert len(client.search("q", count=3)) == 3


def test_ddg_skips_results_without_href_and_title_falls_back():
    def fake_search(query, count):
        return [{"title": "no href here"}, {"href": "https://x/c"}]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert client.search("q") == [("https://x/c", "https://x/c")]


def test_ddg_empty_when_no_results():
    client = DuckDuckGoSearchClient(search_fn=lambda q, c: [])
    assert client.search("zzz") == []


def test_make_search_client_brave_when_key():
    assert isinstance(make_search_client("brv-123"), BraveSearchClient)


def test_make_search_client_ddg_when_no_key():
    assert isinstance(make_search_client(""), DuckDuckGoSearchClient)
    assert isinstance(make_search_client(None), DuckDuckGoSearchClient)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_web_search_ddg.py -q`
Expected: FAIL with `ImportError: cannot import name 'DuckDuckGoSearchClient'`.

- [ ] **Step 3: Implement the DDG client + factory**

In `meister_guide/scraper/web_search.py`, append (after the `BraveSearchClient` class):

```python
class DuckDuckGoSearchClient:
    """Keyless web search via the `ddgs` library (DuckDuckGo). Pure: the search
    call is injectable so tests run without ddgs or a network. Same (title, url)
    interface as BraveSearchClient, so it's a drop-in for run_web_fetch.

    Caveat: ddgs scrapes an unofficial endpoint and can rate-limit or break;
    Brave (keyed) is the reliable upgrade."""
    def __init__(self, search_fn=None):
        self._search_fn = search_fn or self._default_search

    def _default_search(self, query, count):
        from ddgs import DDGS
        return DDGS().text(query, max_results=count)

    def search(self, query, count=3):
        """Return up to `count` (title, url) pairs for `query`. Raises on a
        library/network error (the worker catches it)."""
        results = self._search_fn(query, count) or []
        out = []
        for r in results[:count]:
            url = r.get("href")
            if url:
                out.append((r.get("title") or url, url))
        return out


def make_search_client(brave_api_key):
    """Pick the web-search provider: Brave when a key is set (more reliable),
    else the free keyless DuckDuckGo client."""
    if brave_api_key:
        return BraveSearchClient(brave_api_key)
    return DuckDuckGoSearchClient()
```

- [ ] **Step 4: Wire the factory into `WebFetchWorker`**

In `meister_guide/scraper/worker.py`, change the web-search import line from:

```python
from meister_guide.scraper.web_search import BraveSearchClient
```

to:

```python
from meister_guide.scraper.web_search import make_search_client
```

Then in `WebFetchWorker.run()`, change:

```python
            client = self._client or BraveSearchClient(self._api_key)
```

to:

```python
            client = self._client or make_search_client(self._api_key)
```

- [ ] **Step 5: Add the dependency**

In `requirements.txt`, add this line immediately after the `trafilatura>=1.8 ...` line:

```
ddgs>=6.0  # web-fallback free keyless DuckDuckGo search; lazy-imported
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -m pytest tests/test_web_search_ddg.py tests/test_web_worker.py -q`
Expected: PASS (the 7 new tests + the existing worker tests still green — worker tests inject a `client`, so the factory change doesn't affect them).

- [ ] **Step 7: Commit**

```bash
git add meister_guide/scraper/web_search.py meister_guide/scraper/worker.py requirements.txt tests/test_web_search_ddg.py
git commit -m "feat: keyless DuckDuckGo search + make_search_client provider factory"
```

---

## Task 2: Web fallback on by default (gating no longer needs a key)

**Files:**
- Modify: `meister_guide/db/settings.py`
- Test (rewrite): `tests/test_settings_web.py`

- [ ] **Step 1: Rewrite the failing tests**

Replace the entire contents of `tests/test_settings_web.py` with:

```python
from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    return SettingsRepo(conn)


def test_brave_api_key_defaults_empty(tmp_path):
    assert _repo(tmp_path).brave_api_key() == ""


def test_web_fallback_on_by_default(tmp_path):
    # On out of the box — the free DuckDuckGo path needs no key.
    assert _repo(tmp_path).web_fallback_enabled() is True


def test_web_fallback_enabled_without_key(tmp_path):
    repo = _repo(tmp_path)
    assert repo.brave_api_key() == ""
    assert repo.web_fallback_enabled() is True


def test_web_fallback_paused_when_pref_zero(tmp_path):
    repo = _repo(tmp_path)
    repo.set("web_fallback", "0")
    assert repo.web_fallback_enabled() is False


def test_web_fallback_enabled_with_key(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    assert repo.web_fallback_enabled() is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_settings_web.py -q`
Expected: FAIL — `test_web_fallback_on_by_default` / `test_web_fallback_enabled_without_key` fail because the current `web_fallback_enabled()` still requires a Brave key.

- [ ] **Step 3: Implement**

In `meister_guide/db/settings.py`, replace the `web_fallback_enabled` method:

```python
    def web_fallback_enabled(self):
        """Web fallback is on when a Brave key is set and the pref isn't paused.
        Defaults on once a key exists; the Settings checkbox writes '1'/'0'."""
        return bool(self.brave_api_key()) and self.get("web_fallback") != "0"
```

with:

```python
    def web_fallback_enabled(self):
        """Web fallback is on unless the user paused it (default on). No key is
        required — make_search_client picks the provider: Brave if a key is set,
        otherwise the free keyless DuckDuckGo client."""
        return self.get("web_fallback") != "0"
```

(The `web_fallback` default is already `"1"` in `_DEFAULTS`, so the default is on. `brave_api_key()` is unchanged — it now only selects the provider.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_settings_web.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/settings.py tests/test_settings_web.py
git commit -m "feat: web fallback on by default, key-independent gating"
```

---

## Task 3: Online-first repositioning copy + dependent test updates

**Files:**
- Modify: `meister_guide/overlay/window.py`
- Test (update): `tests/test_window_web.py`
- Test (update): `tests/test_shell_window.py`

- [ ] **Step 1: Update the failing/affected tests**

In `tests/test_window_web.py`, replace the `test_miss_with_web_disabled_answers_anyway` function:

```python
def test_miss_with_web_disabled_answers_anyway(tmp_path):
    w, repo = _window(tmp_path)   # no key -> web disabled
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web
```

with (web fallback is now on by default, so it must be explicitly paused to test the no-web branch):

```python
def test_miss_with_web_disabled_answers_anyway(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("web_fallback", "0")   # paused -> no web fetch
    w._retrieve = lambda q: ([], [])
    answered, web = [], []
    w._answer_now = lambda *a, **k: answered.append(a)
    w._start_web_fetch = lambda *a, **k: web.append(a)
    w._answer_or_web_fallback("q", [], reuse_turn=False)
    assert answered and not web


def test_web_enabled_by_default_without_key(tmp_path):
    w, repo = _window(tmp_path)            # no Brave key
    assert w._web_enabled() is True        # free DuckDuckGo, on by default
    repo.set("web_fallback", "0")
    assert w._web_enabled() is False
```

In `tests/test_shell_window.py`, replace the `test_footer_copy_adapts_to_backend` function:

```python
def test_footer_copy_adapts_to_backend(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)
    w._refresh_footer()
    assert "no cloud" in w.footer_note.text().lower()
    repo.set("chat_backend", BACKEND_AUTO)
    repo.set("claude_api_key", "sk-x")
    w._refresh_footer()
    assert "online" in w.footer_note.text().lower()
```

with (offline tagline now requires both a local backend AND web fallback paused; a new test proves web fallback alone flips the footer):

```python
def test_footer_copy_adapts_to_backend(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)
    repo.set("web_fallback", "0")          # local chat AND web paused -> offline
    w._refresh_footer()
    assert "offline mode" in w.footer_note.text().lower()
    repo.set("chat_backend", BACKEND_AUTO)
    repo.set("claude_api_key", "sk-x")
    w._refresh_footer()
    assert "web-augmented" in w.footer_note.text().lower()


def test_footer_web_augmented_when_only_web_fallback_on(tmp_path):
    w, repo = _window(tmp_path)
    repo.set("chat_backend", BACKEND_OLLAMA)   # local chat backend
    repo.set("web_fallback", "1")              # but web fallback on (default)
    w._refresh_footer()
    assert "web-augmented" in w.footer_note.text().lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_window_web.py tests/test_shell_window.py -q`
Expected: FAIL — the footer assertions (`offline mode` / `web-augmented`) don't match the current footer strings, and `test_footer_web_augmented_when_only_web_fallback_on` fails because the current footer ignores web fallback.

- [ ] **Step 3: Reword the footer**

In `meister_guide/overlay/window.py`, in `_refresh_footer`, replace:

```python
        online = backend == BACKEND_CLAUDE or (backend == BACKEND_AUTO and key)
        self.footer_note.setText(
            "local-first · optional online" if online
            else "runs locally · no account · no cloud")
```

with:

```python
        online = (backend == BACKEND_CLAUDE or (backend == BACKEND_AUTO and key)
                  or (self._settings_repo is not None
                      and self._settings_repo.web_fallback_enabled()))
        self.footer_note.setText(
            "online · web-augmented" if online
            else "offline mode · runs locally")
```

- [ ] **Step 4: Reword the Brave key field help**

In `_build_settings_tab`, change the Brave key field placeholder from:

```python
            self.set_brave_key.setPlaceholderText(
                "brv-…  (enables web search when the wiki can't answer)")
```

to:

```python
            self.set_brave_key.setPlaceholderText(
                "brv-…  optional — leave blank to use free DuckDuckGo")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -m pytest tests/test_window_web.py tests/test_shell_window.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS — all tests green.

- [ ] **Step 7: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_web.py tests/test_shell_window.py
git commit -m "feat: online-first footer + key-field copy; web-augmented by default"
```

---

## Final verification

- [ ] Run `py -m pytest -q` — confirm the whole suite passes.
- [ ] Confirm no perpetually-dirty files were staged (`.planning/HANDOFF.json`, `devlogs/the-whole-build.md`, `Meister Guide overlay design/`, `DONOTTOUCH.txt`).
- [ ] Then proceed to `superpowers:finishing-a-development-branch`.

## Notes / rationale

- **Drop-in provider:** `DuckDuckGoSearchClient.search` returns the same `(title, url)` list as `BraveSearchClient`, so `run_web_fetch` and `WebFetchWorker` need no structural change beyond the factory call.
- **Injectable `search_fn`:** keeps the whole stack testable offline without `ddgs` installed (same seam pattern as Brave's `http_get` and trafilatura's `extract`).
- **Gating flip:** the only behavioral change is `web_fallback_enabled()` no longer requiring a key; the `web_fallback` pref already defaulted to `"1"`, so removing the key clause makes it on by default. The Settings checkbox (initial state `get("web_fallback") != "0"`) and `_on_save_settings` persistence are already correct and unchanged.
- **Footer now reflects web fallback:** the `online` flag ORs in `web_fallback_enabled()`, so a local chat backend with web fallback on still reads "web-augmented"; only a fully-local, web-paused config shows "offline mode."
- **`ddgs` is lazy-imported** in `_default_search` only, so importing `web_search` never requires it.
```
