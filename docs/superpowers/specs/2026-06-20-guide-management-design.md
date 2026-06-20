# Downloaded-guide management UI (design)

**Date:** 2026-06-20
**Status:** Approved, ready for planning
**Related:** SP1 multi-wiki foundation (`game_id` scoping), SP3 category seed (Settings-tab UI it sits beside)

## Problem

Games accumulate stored guides (from the Minecraft full seed, SP3 category seeds,
SP2a on-demand fetches, and SP2b web fallback). There's no way to see how much a
game has stored or to delete it — to free space, re-seed fresh, or remove a game
added by mistake. This is the old backlog item "pick a game, see/delete its
stored guides," now unblocked by the multi-wiki `game_id` scoping.

## Decisions (locked during brainstorming)

- **Two operations:** "Clear guides" (delete a game's stored guides, keep the
  game) and "Remove game" (delete the game row + its guides).
- **Minecraft is protected from removal** (the seeded default), but its guides
  can be cleared.
- **Per-game bulk** granularity — no per-article deletion (YAGNI; corpora are
  thousands of pages).
- **UI:** a game-picker combo + live count label + two buttons on the ⚙ Settings
  tab (consistent with the SP3 seed block right above it), not a full list.
- **Clearing Minecraft also resets** the single-row `scrape_state` /
  `redirect_state`.

## Non-goals

- Per-article browse/delete; disk-byte size reporting (show counts only);
  exporting/backing up guides; undo. Out of scope.

## Operations & rules

- **Clear guides (per game):** delete all `articles` + `redirects` rows for that
  `game_id` (and their FTS index rows); keep the `games` row. If the cleared game
  is Minecraft, also reset `scrape_state` and `redirect_state` to empty so the
  Guides tab stops reporting a stale "done" count over an emptied corpus and a
  future "Update guides" starts clean.
- **Remove game (per game):** Clear the game's guides (as above), then delete the
  `games` row via `GamesRepo.delete`. **Disabled for Minecraft.**
- Both operations are destructive and prompt a confirmation dialog first (mirrors
  `overlay/chat_manager.py`'s confirm pattern). On cancel, nothing happens.

## Data layer

New methods, mirroring the per-row contentless-FTS delete already used by
`ArticlesRepo.prune_noise` (contentless FTS5 needs the original column values
supplied to delete an index row).

### `ArticlesRepo.delete_by_game(game_id) -> int`

```
For each (id, title, body_zlib) in articles WHERE game_id = ?:
    decompress body
    INSERT INTO articles_fts(articles_fts, rowid, title, body) VALUES('delete', id, title, body)
    DELETE FROM articles WHERE id = ?
commit; return count deleted
```

### `RedirectsRepo.delete_by_game(game_id) -> int`

```
For each (id, title) in redirects WHERE game_id = ?:
    INSERT INTO redirects_fts(redirects_fts, rowid, title) VALUES('delete', id, title)
    DELETE FROM redirects WHERE id = ?
commit; return count deleted
```

### State reset (Minecraft clear)

Use the existing repos: `ScrapeStateRepo.save(ScrapeState(None, 0, None))` and
`RedirectStateRepo.save(RedirectState(None, 0))`. The window already holds
`_scrape_state_repo` / `_redirect_state_repo`. Reset only when the cleared game
is Minecraft (only Minecraft uses these single-row tables).

`GamesRepo.delete(game_id)` already exists and is reused for Remove.

## UI

On the ⚙ Settings tab, a **"Manage guides"** block below the seed block:

- `self.manage_game` — `QComboBox` of all games (id in `userData`), defaults to
  the active game.
- `self.manage_count` — a `QLabel` showing the picked game's stored counts, e.g.
  `"123 guides · 45 aliases"` (article count via `ArticlesRepo.count(game_id=)`,
  alias count via a new `RedirectsRepo.count_by_game(game_id)`).
- `self.manage_clear_btn` — "Clear guides".
- `self.manage_remove_btn` — "Remove game".
- `self.manage_status` — a `QLabel` (Disclaimer style) for result/error text.

Behaviour:

- Picking a game (`currentIndexChanged`) refreshes `manage_count` and enables
  `manage_remove_btn` only when the picked game is **not** Minecraft.
- `_refresh_manage_games()` repopulates the combo (preserving selection, default
  active game); a no-op if the combo isn't built yet (`hasattr` guard). Called on
  build, and from `_on_add_game` / `set_games` / after Clear / after Remove —
  alongside the existing `_refresh_seed_games()` calls.
- **Clear** (`_on_clear_guides`): confirm dialog; on confirm, `delete_by_game` on
  both repos (and reset Minecraft state if applicable), refresh the count label,
  the Wiki-tab guides status, the seed combo, and show
  `"Cleared N guides."` in `manage_status`.
- **Remove** (`_on_remove_game`): guard out Minecraft; confirm dialog; on confirm,
  clear its guides, `GamesRepo.delete`, reload `self._games` from `games_repo`,
  rebuild the game menu + seed combo + manage combo; if the removed game was
  `active_game`, set `active_game = None` and refresh the header pill; status
  `"Removed <name>."`.
- A confirm helper mirrors `chat_manager.py` (a `QMessageBox.question` Yes/No).

## Edge cases

- **No `games_repo` / `articles_repo`** (e.g. minimal test window): the block's
  handlers guard on `self._games_repo is None` / `self._articles_repo is None`
  and no-op, consistent with `_on_add_game`.
- **Active game removed:** `active_game` reset to None, pill updated; detection
  may re-set it later (unchanged behavior).
- **Active game cleared:** just refresh `_refresh_guides_status()`.
- **Empty corpus clear:** `delete_by_game` returns 0; status "Cleared 0 guides.";
  no error.
- **FTS consistency:** after `delete_by_game`, a chat/guides search for a deleted
  title returns nothing, and another game's identical-substring title still
  matches (the index rows are removed per-row, not globally).

## Testing (TDD)

- **`ArticlesRepo.delete_by_game`**: deletes only the target game's rows; leaves
  other games' rows intact; the contentless `articles_fts` stays consistent
  (`search`/`search_ranked` no longer returns a deleted title, still returns a
  kept game's title); returns the count; idempotent (second call returns 0).
- **`RedirectsRepo.delete_by_game`** + **`count_by_game`**: same scoping; alias
  search via `search_ranked` no longer resolves a deleted alias; count correct.
- **Window (offscreen)**: combo lists games; count label reflects the picked
  game; `manage_remove_btn` disabled for Minecraft, enabled otherwise; Clear
  calls `delete_by_game` on both repos and (for Minecraft) resets scrape/redirect
  state, then updates status/count; Remove deletes the game, reloads games,
  resets `active_game` if it was active; both ops are gated by the confirm helper
  (inject/stub the confirm to avoid a modal in tests); no-`games_repo` no-op.

## Build approach

One feature branch (`guide-management`), TDD per task, subagent-driven with
two-stage review (spec + quality) per task and a final whole-branch review, then
`finishing-a-development-branch`. Run tests with `py -m pytest -q`.
