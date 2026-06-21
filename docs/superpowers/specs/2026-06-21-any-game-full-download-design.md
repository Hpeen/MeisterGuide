# Full wiki downloads for any game (design)

**Date:** 2026-06-21
**Status:** Approved, ready for planning

## Problem

The Wiki tab's "Update guides" performs a full-wiki bulk download, but it only
works for Minecraft: the worker builds a `WikiClient()` pointed at the default
`minecraft.wiki` API, the article display URLs are hardcoded to `minecraft.wiki`,
and the resume-state tables (`scrape_state`, `redirect_state`) are single-row, so
they can only track one game's download. A second game's walk would clobber
Minecraft's resume token (and vice versa). This change makes a full, resumable
download work for **any** game that has a wiki URL, mirroring the per-game pattern
already used by `articles`, `redirects`, on-demand fetch, and category seeding.

## Decisions (locked during brainstorming)

- **Per-game resume state.** `scrape_state` and `redirect_state` become per-game.
  The existing single row is preserved and assigned to Minecraft.
- **Unbounded download + size estimate.** A full download has no page cap. Before
  the long walk, the worker reports the wiki's page count so the status can show
  an estimate (e.g. "Subnautica wiki has ~6,200 pages. Downloading…", with a "this
  will take a while" note past ~25,000). No blocking confirm dialog — it proceeds.
- **Per-game state via a guarded table rebuild.** The state tables carry
  `id INTEGER PRIMARY KEY CHECK (id = 1)`, which structurally forbids more than one
  row, so a plain ADD COLUMN cannot work. A one-time guarded migration rebuilds
  the two small state tables keyed by `game_id`, copying the existing row to
  Minecraft. (This is the faithful form of the approved "per-game state" approach;
  the rebuild is forced by the CHECK constraint, and it preserves existing data.)

## Non-goals

- A page cap / batched "click again for more" flow (rejected: a full download
  must be resumable, not manual). A pre-download confirm/cancel dialog. Parallel
  downloads of multiple games at once (one ingest worker at a time, unchanged).
  Fixing wikis that lack the TextExtracts API (same existing limitation as
  on-demand/seed; such a wiki simply yields no article text). Rewriting already
  stored Minecraft article URLs.

## Components

### 1. Schema — per-game state tables (`db/schema.py`)

New definitions for fresh DBs, keyed by game:

```sql
CREATE TABLE IF NOT EXISTS scrape_state (
    game_id INTEGER PRIMARY KEY REFERENCES games(id),
    continue_token TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```
```sql
CREATE TABLE IF NOT EXISTS redirect_state (
    game_id INTEGER PRIMARY KEY REFERENCES games(id),
    continue_token TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

`CREATE TABLE IF NOT EXISTS` is a no-op on an already-existing (old-schema) table,
so existing DBs keep the old single-row table until the migration rebuilds it.

### 2. Migration — rebuild legacy state tables (`db/database.py`)

Extend `migrate_game_ids(conn)` (which already resolves Minecraft's id and runs
after `seed_defaults`). After the existing articles/redirects backfill, for each of
`scrape_state` and `redirect_state`:

- If the table has **no `game_id` column** (legacy single-row schema), rebuild it:
  1. `CREATE TABLE <t>_new (…game_id-keyed schema…)`
  2. `INSERT INTO <t>_new (game_id, …) SELECT <mc_id>, … FROM <t> WHERE id = 1`
     (only the existing row, if present)
  3. `DROP TABLE <t>; ALTER TABLE <t>_new RENAME TO <t>`

Idempotent: once `game_id` exists, the rebuild is skipped. Wrapped so the whole
backfill commits together. The rebuild lives in `migrate_game_ids` (not `init_db`)
because it needs Minecraft's id, and `init_db` runs before games are seeded.

### 3. State repos — keyed by game (`db/articles.py`, `db/redirects.py`)

`ScrapeStateRepo` and `RedirectStateRepo` take `game_id`:

```
load(game_id) -> ScrapeState        # SELECT … WHERE game_id = ?; default if none
save(state, game_id, commit=True)   # upsert ON CONFLICT(game_id)
```

Same shape for `RedirectStateRepo` (no `total`). The `ScrapeState` / `RedirectState`
dataclasses are unchanged. `game_id` is a required argument (no implicit
single-row default), so every call site is explicit.

### 4. Ingest orchestrator (`scraper/ingest.py`, `scraper/redirect_ingest.py`)

- `run_ingest(client, articles_repo, state_repo, conn, progress_cb=None,
  should_cancel=None, game_id=None, base="", total=None)`:
  - State calls pass `game_id`: `state_repo.load(game_id)` / `save(state, game_id)`.
  - `total` resolution: use the saved state's `total` on resume; else the `total`
    override if provided; else `client.article_count()`.
  - Article display URLs come from `base`: replace the hardcoded
    `_url_for(title)` (`"https://minecraft.wiki/w/" + …`) with
    `page_url(base, title)` from `scraper/urls.py`. URLs are display-only.
- `run_redirect_ingest(...)`: thread `game_id` to its `RedirectStateRepo`
  `load(game_id)` / `save(..., game_id)`. Redirects store no URL, so no `base`.

### 5. Worker (`scraper/worker.py::IngestWorker`)

Generalize to any wiki, mirroring `OnDemandFetchWorker` / `CategorySeedWorker`:

```
IngestWorker(db_path, game_id=None, api_url=None, page_url_base="", client=None)
    signals: progress(int,int), counted(int), finished(), error(str)
```

- `run()` builds `client = self._client or WikiClient(api_url=self._api_url)`
  (falls back to the default API when `api_url` is None, preserving current
  Minecraft behavior).
- Before the walk: `total = client.article_count()` (guarded; `None`/0 on error),
  `self.counted.emit(total or 0)`, then `run_ingest(..., game_id=self._game_id,
  base=self._page_url_base, total=total)` followed by `run_redirect_ingest(...,
  game_id=self._game_id)`.
- `prune_noise`, the cancel flag, the own-connection pattern, and teardown are
  unchanged.

### 6. Window (`overlay/window.py`)

- `_on_update_guides`: act on the picked game (`_guides_target_game()`), for **any**
  game with a wiki URL:
  - No game → return.
  - Game with no `wiki_url` → status: "This game has no wiki URL yet. Add one in
    Settings first." (mirrors the seed control), no download.
  - Otherwise start the download. Factor the worker/thread creation into a
    `_start_ingest(game)` helper (it builds `IngestWorker(db_path, game_id=game.id,
    api_url=api_url_for(game.wiki_url), page_url_base=game.wiki_url)`, connects
    `progress`/`counted`/`finished`/`error`, disables the button, shows the
    progress bar, starts). `_on_update_guides` does the guards then calls
    `_start_ingest(game)`. The helper is a clean seam: tests monkeypatch it to
    assert the chosen game without spawning a real thread. The Minecraft-only gate
    is removed.
- New `counted` handler: set status to
  `f"{game.name} wiki has ~{total:,} pages. Downloading…"`, appending
  " This will take a while." when `total > 25000`. (When `total` is 0/unknown, a
  generic "Downloading…" is shown.)
- `_on_ingest_progress` / `_on_ingest_done` / `_on_ingest_error` / `_teardown_ingest`
  are unchanged except they already work per active worker.
- `_refresh_guides_status`: load `scrape_state` / `redirect_state` for the picked
  game (`_guides_target_game().id`) and drop the Minecraft-only special-case, so
  any partially-downloaded game shows "Partly downloaded… click Update to finish."

### 7. Wiring (`main.py`)

`migrate_game_ids` already runs after `seed_defaults`; it now also performs the
state-table rebuild. No new call sites. The window already receives
`scrape_state_repo` / `redirect_state_repo`; their `load` calls in
`_refresh_guides_status` now pass `game_id`.

## Data flow

Pick game in the Wiki picker → Update → `IngestWorker` opens its own SQLite conn +
`WikiClient(api_url)` → `counted(total)` → status shows the estimate → walk all
article batches (per-game resume token, per-batch commit) → redirect/alias pass →
`finished`. Hiding the overlay keeps it running; quitting cancels (existing
behavior).

## Error handling

- No wiki URL → friendly message, no download (guarded before the thread starts).
- `article_count()` failure → `counted(0)`, generic "Downloading…", walk still runs
  (the per-batch `progress` carries the real total once known).
- Network/API errors → existing `WikiClient` retry/backoff, then `error` → status
  shows the reason; `_teardown_ingest` re-enables the button.
- A wiki without TextExtracts → batches yield no `extract`, nothing is stored, the
  run completes cleanly (documented existing limitation).

## Testing (TDD)

**State repos / migration**
- `ScrapeStateRepo` / `RedirectStateRepo`: `save`+`load` round-trip per `game_id`;
  two game_ids keep independent rows; `load` of an unknown game returns the default.
- Migration: a DB built with the legacy single-row schema (with a stored
  continue_token) is rebuilt so the row is readable via `load(minecraft_id)` with
  the token intact, and a second game's `save/load` works afterward; running the
  migration twice is a no-op.

**Ingest**
- `run_ingest` writes/reads state under the given `game_id` and stores article URLs
  built from `base` (e.g. a non-Minecraft base yields that host in the URL).
- Two games ingested into one DB keep separate resume tokens.

**Worker**
- `IngestWorker` builds a `WikiClient` for the given `api_url` (inject a fake
  client to avoid the network) and emits `counted` with the client's article
  count before `finished`.

**Window** (monkeypatch `_start_ingest` so no real thread/network runs)
- A non-Minecraft game **with** a wiki URL: `_on_update_guides` calls
  `_start_ingest` with that game.
- A game **without** a wiki URL: `_on_update_guides` sets the "add a wiki URL"
  status and does not call `_start_ingest`.
- The `counted` handler renders the estimate string (and the large-wiki note past
  25k).

**Regression**
- Existing Minecraft ingest tests keep passing with the new `game_id`/`base`
  parameters (Minecraft base + id supplied).

## Build approach

One feature branch (`any-game-full-download`), TDD per task, subagent-driven with
per-task spec + quality review and a final whole-branch review, then
`finishing-a-development-branch`. Run tests with `py -m pytest -q`. Because this
touches a schema migration, the migration task includes an explicit test against a
hand-built legacy-schema DB.
