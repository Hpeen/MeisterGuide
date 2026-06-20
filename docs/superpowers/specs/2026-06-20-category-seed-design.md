# SP3 — Per-game category seed (design)

**Date:** 2026-06-20
**Status:** Approved, ready for planning
**Predecessor:** SP2a on-demand fetch-on-miss (`docs/superpowers/specs/2026-06-19-on-demand-fetch-design.md`)

## Problem

The hybrid knowledge model (decided 2026-06-19) makes the full-wiki bulk scrape
*optional*. SP2a already fills per-query gaps on a chat miss. What's still
missing: a way to **pre-load the core pages of a newly-added game** so its corpus
isn't empty on first use, without committing to a full 16k+ article mirror (which
is slow precisely because MediaWiki's TextExtracts returns ~1 full extract per
request).

SP3 delivers a **bounded, user-triggered, per-game seed** driven by a wiki
**category** the user chooses. On-demand fetch (SP2a) continues to handle the
long tail.

## Non-goals

- **Full-wiki mirror per game.** Minecraft keeps its existing full walk +
  single-row `scrape_state`; SP3 does not generalize that machinery.
- **Per-game `scrape_state`/resume tokens.** Not needed — see below.
- **Redirect ingestion for seeded categories.** SP2a skips redirects on the
  on-demand path; SP3 does the same to stay bounded and simple.
- **General-web fallback.** That is SP2b, a separate cycle.
- **Guide-management / delete UI.** Deferred (old backlog item); out of scope.

## Key decision: no `scrape_state` migration

`scrape_state` and `redirect_state` are single-row tables (`CHECK (id = 1)`)
holding the resume token + progress for *one* corpus walk; Minecraft owns those
rows today. A bounded category seed does **not** need them: like
`run_on_demand_fetch`, it is a single run-to-completion operation, and
`add_article` is idempotent by `pageid`. If a seed is interrupted, re-running it
simply skips already-stored pages. This keeps Minecraft's full-walk path
completely untouched and makes SP3 a close parallel of SP2a.

## Architecture

SP3 mirrors the SP2a on-demand stack layer-for-layer:

| SP2a (exists) | SP3 (new) |
|---|---|
| `WikiClient.search_titles` / `fetch_by_titles` | `WikiClient.iter_category_members(category)` |
| `scraper/on_demand.py::run_on_demand_fetch(...)` (pure) | `scraper/seed.py::run_category_seed(...)` (pure) |
| `OnDemandFetchWorker` | `CategorySeedWorker` |
| chat-miss trigger in `window._on_send` | "Seed from category" controls on the ⚙ Settings tab |

### 1. `WikiClient.iter_category_members(category, recurse_level=1)`

Enumerate the article members of a category, one level deep.

- Normalize the input to a `Category:` title (accept both `Mobs` and
  `Category:Mobs`).
- `action=query&list=categorymembers&cmtitle=Category:<name>&cmlimit=...`,
  paginated via `cmcontinue`. Request both article members (`cmnamespace=0`) and
  subcategory entries (`cmnamespace=14`) — e.g. `cmnamespace="0|14"`.
- For each immediate subcategory found, enumerate *its* `cmnamespace=0` members
  (one level only — no further recursion, so no cycle risk).
- Return a **deduped list of article titles** (dedupe by title; pageid dedupe
  also happens later at `add_article`).
- Pure/testable: reuses the existing injected `_http_get`, `_fetch` (retry +
  maxlag), `_sleep`/`_delay` politeness, exactly like `iter_batches`.

### 2. `scraper/seed.py::run_category_seed(client, articles_repo, game_id, category, base="", cap=500, progress_cb=None, should_cancel=None)`

Pure (no Qt), unit-testable — the structural twin of `run_on_demand_fetch`.

1. `titles = client.iter_category_members(category)`; dedupe; truncate to `cap`.
2. `total = len(titles)`; emit `progress_cb(0, total)`.
3. For each title (in order):
   - Poll `should_cancel()` → break if cancelled.
   - Fetch the full extract for the title (`client.fetch_by_titles([title])` —
     one title per request because TextExtracts caps full extracts at ~1 per
     request).
   - Skip if `is_noise(title)`.
   - `articles_repo.add_article(pageid, title, text, revid, _page_url(base,
     title), game_id=game_id)` — idempotent; count only newly-inserted rows.
   - Emit `progress_cb(done_index, total)`.
4. Return the number of articles newly ingested.

Reuse `on_demand._page_url(base, title)` (or a shared helper) for the
display-only stored URL, so the page-URL base is per-game (no hardcoded
`minecraft.wiki`).

**Cost note (accepted trade-off):** a category of N pages ≈ N content requests.
Bounded by `cap=500`, user-initiated, with a progress bar and cancel — the same
trade-off the existing full walk already accepts.

### 3. `CategorySeedWorker` (in `scraper/worker.py`)

Direct sibling of `OnDemandFetchWorker`:

- `__init__(self, db_path, game_id, api_url, page_url_base, category, cap=500, client=None)`.
- `run()`: opens its **own** SQLite connection (connections aren't thread-safe
  to share), `init_db(conn)`, builds `WikiClient(api_url=self._api_url)` (or the
  injected client), calls `run_category_seed(...)` passing
  `should_cancel=lambda: self._cancel` and a `progress_cb` that emits the signal.
- Signals: `progress(int, int)` (done, total), `finished(int)` (count ingested),
  `error(str)`.
- `cancel()` sets a flag polled between pages (parity with
  `OnDemandFetchWorker.cancel`).

### 4. UI — ⚙ Settings tab

Below the existing "Add a game" block in `_build_settings_tab`, add a
**"Seed guides from a category"** section:

- Game picker `QComboBox` listing all games (id in `userData`), defaulting to the
  active game.
- Category `QLineEdit` (placeholder `e.g. Mobs`, accepts `Category:` prefix too).
- "Seed" `QPushButton`.
- A `QProgressBar` (hidden until running) + status `QLabel`.

Behaviour (`_on_seed_category`):

- Resolve the picked game; if it has no `wiki_url`, set status
  ("This game has no wiki URL — add one first") and return.
- If a seed is already running, ignore (single seed at a time, like ingest).
- Derive `api_url = api_url_for(game.wiki_url)` and `page_url_base = game.wiki_url`.
- Start a `QThread` + `CategorySeedWorker`; disable the Seed button + show the
  progress bar; wire `progress`/`finished`/`error` to handlers (mirrors the
  ingest-thread lifecycle: `_teardown` quits+waits the thread).
- On `finished`: tear down, show "Added N guides", refresh the games list /
  article counts and the Wiki-tab guides status if visible.
- On `error`: tear down, show the truncated first line of the error (same pattern
  as `_on_ingest_error`).
- Cancellation: `hide()`/shutdown cancel the worker (same hooks that cancel the
  fetch worker), so quitting mid-seed aborts promptly.

### 5. Edge cases

- Game without `wiki_url` → status message, no run.
- Empty / nonexistent category → `iter_category_members` returns `[]` → 0
  ingested, clear "No pages found in that category" status.
- Re-running the same seed → idempotent (already-stored pages skipped).
- Cap reached → stop at `cap`; status notes the corpus was capped.
- Offline / API error → surfaced via the `error` signal in the status label; no
  crash.
- A subcategory that is empty or itself only contains subcategories → its
  (zero) ns-0 members contribute nothing; no deeper recursion.

## Testing (TDD)

Parallels SP2a's ~20 tests:

- **`run_category_seed`** with a fake client: happy path; recursion-one-level
  pulls subcategory members; dedupe across category + subcategories; `cap`
  truncation; `is_noise` skip; idempotency on re-run; cancel mid-walk stops
  early; correct `progress_cb` calls; per-game `base` in stored URL.
- **`iter_category_members`** with a fake `http_get`: `cmcontinue` pagination;
  subcategory (ns 14) expansion to its ns-0 members; `Category:` normalization;
  one-level-only (no infinite recursion).
- **`CategorySeedWorker`** with an injected fake client: emits
  `finished(count)`; emits `error` on exception; `cancel()` honored.
- **UI wiring** (offscreen, light, as SP2a): no-`wiki_url` short-circuit;
  button/progress lifecycle; teardown.

## Build approach

Same workflow as SP2a: one feature branch (`category-seed`), TDD per task,
subagent-driven execution with two-stage review (spec + quality) per task and a
final whole-branch review, then `finishing-a-development-branch`. Run tests with
`py -m pytest -q`.
