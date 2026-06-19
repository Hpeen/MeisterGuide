# SP1 — Multi-Wiki Foundation — Design Spec

**Date:** 2026-06-19
**Status:** Approved scope, ready for implementation planning
**Part of:** the Hybrid knowledge-model pivot (SP1 of SP1→SP2→SP3). See `project-status` memory.

## Why

The bulk full-wiki scrape is slow/janky and downloads mostly-unused pages. The
chosen direction is a **hybrid** model: pick a wiki → answer from a few fetched
pages on demand → remember them. SP1 lays the foundation so the corpus and
retrieval are **partitioned per game/wiki**. SP2 (separate) adds on-demand
fetch-on-miss; SP3 (separate) reframes bulk download as an optional per-game seed.

## Scope

**In SP1:**
- `game_id` on `articles` and `redirects`, with a startup migration that backfills
  the existing corpus to Minecraft.
- Writes (`add_article`, `add_redirect`) carry `game_id`.
- `search_ranked` (and redirect-alias resolution) scoped to the active game.
- Guides-tab article count/status scoped to the active game.
- Add-game UI (name + wiki URL + process names) via `GamesRepo`.
- `api_url` helper derived from `games.wiki_url` (foundation for SP2 fetching).

**Out of SP1 (explicit non-goals):**
- On-demand fetch-on-miss + remember → **SP2**.
- Per-game bulk download / `scrape_state` per game → **SP3**. `scrape_state` is
  left single-row; the existing bulk "Update guides" stays Minecraft-only.
- Generalizing the *bulk* scraper to arbitrary wikis (only the lightweight
  `api_url` helper lands now; real fetching is SP2).

## Current state (facts to build on)

- `articles(id, pageid UNIQUE, title, body_zlib, revid, url)` and
  `redirects(id, title UNIQUE, target_pageid)` — **no game_id**. `articles_fts` /
  `redirects_fts` are contentless FTS5 (rowid = the table's `id`).
- `games(id, name, process_names, wiki_url, …)` already exists with full CRUD in
  `GamesRepo`; Minecraft is seeded (`seed_defaults`). `wiki_url` = `https://minecraft.wiki`.
- `WikiClient.__init__` already accepts `api_url` (default minecraft.wiki) — already
  parameterized.
- `search_ranked` runs two FTS passes (AND + de-inflected OR) over `articles_fts`
  and `redirects_fts`, joining to `articles` by rowid; re-ranks with coverage.
- The window tracks `self.active_game` (a `Game` or None) via the game-pill menu /
  detector; chat retrieval calls `self._articles_repo.search_ranked(question, …)`.

## Design

### 1. Schema + migration
- Add `game_id INTEGER REFERENCES games(id)` to `articles` and `redirects`.
- For a fresh DB, the column is in the `CREATE TABLE`. For an existing DB, a
  migration runs in `init_db` (or a `migrate(conn)` it calls):
  - Guard with `PRAGMA table_info(articles)` — only `ALTER TABLE … ADD COLUMN`
    when `game_id` is absent (idempotent, safely re-runnable).
  - Backfill: `UPDATE articles SET game_id = :minecraft_id WHERE game_id IS NULL`
    (same for `redirects`). `minecraft_id` = the seeded Minecraft row's id
    (looked up by the built-in Minecraft name; games are seeded before migration).
- No data is deleted; the 36k Minecraft corpus is preserved and attributed.
- **Ordering (correctness):** the backfill needs Minecraft's id, but today
  `main.py` calls `init_db(conn)` *before* `games_repo.seed_defaults()`. Split the
  work: `init_db` does the schema part (create-with-`game_id` for fresh DBs, and
  the guarded `ALTER TABLE … ADD COLUMN` for existing ones) with the column
  nullable; then a separate **post-seed backfill** (`migrate_game_ids(conn)` or a
  `GamesRepo` method) runs *after* `seed_defaults()` to set `game_id` on the
  NULL rows to the Minecraft id. Both steps are idempotent.

### 2. Writes carry game_id
- `ArticlesRepo.add_article(pageid, title, text, revid, url, game_id, commit=True)`.
- `RedirectsRepo.add_redirect(title, target_pageid, game_id, commit=True)`.
- The Minecraft bulk path (`run_ingest` / `IngestWorker`) passes Minecraft's
  `game_id`. `IngestWorker` gains a `game_id` param; the window resolves Minecraft's
  id and passes it when starting "Update guides".

### 3. Retrieval scoped to the active game
- `search_ranked(raw_query, game_id, limit=3, …)`: each FTS pass joins to
  `articles` and filters `AND a.game_id = ?`; the redirect-alias pass filters the
  resolved article's `game_id` too. So cross-game contamination is impossible.
- The window passes `self.active_game.id` (falling back to the Minecraft seed game
  when `active_game` is None, preserving today's behavior).

### 4. Guides-tab scoping
- `ArticlesRepo.count(game_id=None)` — total when `None`, else per game.
- `_refresh_guides_status` counts the active game and feeds `guides_status_text`.
- "Update guides" (bulk) is enabled only when the active game is Minecraft (the
  only game with a wired bulk corpus in SP1); disabled otherwise with a tooltip
  noting on-demand updates are coming. (Per-game bulk = SP3.)

### 5. Add-game UI + api_url helper
- A small form in the ⚙ Settings tab: **Name**, **Wiki URL**, **Process name(s)**
  (comma-separated), with an Add button calling `GamesRepo.add(...)`. The list
  refreshes the game-pill menu.
- `api_url` helper (pure): `wiki_url.rstrip('/') + "/api.php"` — covers minecraft.wiki
  and Fandom. Lives on the `Game` model or a small function; consumed by SP2.

## Testing strategy
- **Migration:** on an old-shape DB (no `game_id`), `init_db` adds the column and
  backfills to Minecraft; re-running is a no-op; fresh DBs already have it.
- **Game-scoped writes/search:** two games with same-keyword articles; a query
  under game A never returns game B's article; redirect aliases respect game_id.
- **count(game_id):** total vs per-game.
- **api_url helper:** minecraft.wiki and a Fandom URL, trailing-slash handling.
- Add-game form verified by launching (offscreen smoke where practical).
- Existing 179 tests stay green (back-compat: `game_id` params default sensibly or
  callers updated in the same change).

## Risks
- **Migration on the user's live 36k DB.** Mitigations: PRAGMA-guarded + idempotent;
  tested against an old-shape fixture; backfill is a single UPDATE; no destructive
  ops. Recommend verifying against a *copy* of the live DB before shipping.
- Back-compat of `search_ranked` / `add_article` signatures — update all call sites
  in the same change; keep `game_id` required where it must be, defaulted where safe.
