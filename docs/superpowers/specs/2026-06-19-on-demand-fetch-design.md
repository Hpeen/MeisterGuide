# SP2a — On-Demand Wiki Fetch-on-Miss — Design Spec

**Date:** 2026-06-19
**Status:** Approved scope, ready for planning
**Part of:** the Hybrid knowledge-model pivot. SP1 (multi-wiki foundation) is merged.
This is **SP2a** — the wiki path of the user's chosen "wiki-first, web-fallback" model.
The general-web fallback is **SP2b** (next cycle, explicit non-goal here).

## Why

A newly added game (Subnautica) has an empty corpus, so every question is a local
miss. SP2a fills the gap live: on a retrieval miss, search the active game's wiki,
fetch the top pages, **ingest them (scoped to the game, so they're offline next
time)**, then answer from them. The app drives the fetch against the wiki's
MediaWiki API (deterministic, ingestable) — the LLM is not asked to browse the web.

## Scope

**In SP2a:**
- `WikiClient.search_titles(query, limit)` — MediaWiki `list=search`.
- `WikiClient.fetch_by_titles(titles)` — `prop=extracts` for specific titles.
- `run_on_demand_fetch(client, articles_repo, game_id, query, limit=3)` — pure,
  testable: search → fetch → skip noise → `add_article(game_id=…)`; returns the
  number ingested.
- A thin `OnDemandFetchWorker` (QThread) wrapping it (network off the UI thread).
- `_on_send` miss branch: on **0 local hits** for the active game (and the game has
  a wiki), fetch first, then re-retrieve and answer.

**Out (explicit non-goals):**
- General-web search + scrape fallback → **SP2b**.
- Weak-hit triggering (only zero-hits triggers a fetch).
- Per-game bulk download → SP3.

## Current state (facts to build on)

- `_on_send` (window.py) is synchronous up to the LLM call: it runs
  `search_ranked(question, limit=3, game_id=self._active_game_id())`, builds
  `passages` via `relevant_passage`, captures prior `history`, calls
  `_begin_exchange(question, sources)` (appends a user turn + an empty assistant
  placeholder, persists the user message), then `build_messages` →
  `_start_chat_worker` (async `ChatStreamWorker` streams into the placeholder).
- `WikiClient` already has `_fetch(params)` (retry/maxlag) and `_articles_from(data)`
  (→ `WikiArticle(pageid, title, text, revid)`); `__init__` takes `api_url`.
- `is_noise(title)` (ranking) is reused at ingest to skip junk.
- `api_url_for(wiki_url)` (db.games) derives the API endpoint per game.
- `ArticlesRepo.add_article(..., game_id=…)` is idempotent by pageid (dedupe is free).

## Design

### 1. WikiClient: query search + fetch-by-title
- `search_titles(query, limit=5)` → `_fetch({action:query, list:search, srsearch:query,
  srlimit:limit, srnamespace:0})` → return `[title, …]` from `query.search[].title`.
- `fetch_by_titles(titles)` → `_fetch({action:query, titles:"A|B|C", prop:extracts,
  explaintext:1, exlimit:"max"})` → reuse `_articles_from` → `[WikiArticle, …]`.
  (TextExtracts may cap extracts per request; ≤3 titles is fine — accept whatever
  comes back. Pure: HTTP injected like the existing client tests.)

### 2. Orchestration (pure, no Qt)
```
run_on_demand_fetch(client, articles_repo, game_id, query, limit=3) -> int:
    titles = client.search_titles(query, limit)
    arts   = client.fetch_by_titles(titles[:limit]) if titles else []
    n = 0
    for a in arts:
        if is_noise(a.title): continue
        if articles_repo.add_article(a.pageid, a.title, a.text, a.revid,
                                     _page_url(base, a.title), game_id=game_id):
            n += 1
    return n
```
Lives in a new `meister_guide/scraper/on_demand.py` (sibling of `ingest.py`).
`_page_url(base, title)` is best-effort (`base.rstrip('/') + '/wiki/' + title.replace(' ','_')`);
the stored `url` is display-only.

### 3. Worker (thin Qt wrapper)
`OnDemandFetchWorker(QObject)` mirroring `IngestWorker`: opens its OWN sqlite
connection in `run()`, builds a `WikiClient(api_url=…)`, calls
`run_on_demand_fetch(...)`, emits `finished(int)` (count) or `error(str)`.
Constructed with `(db_path, game_id, api_url, page_url_base, query, client=None)`.

### 4. Window wiring (`_on_send`)
- Add a guard so a fetch thread, like the chat thread, blocks re-entry.
- Capture `history` BEFORE any turn is appended.
- Decide miss: `articles_repo` set, the active game resolves to a wiki (`wiki_url`
  → `api_url_for`), and `search_ranked(question, limit=1, game_id=…)` is empty.
- Miss path: `_begin_exchange(question, [])` (placeholder), set chat status
  "Searching the wiki…", disable input, start `OnDemandFetchWorker`. On
  `finished`/`error` → `_on_fetch_done(question, history)`: re-run retrieval (now
  finds the fetched pages), set the placeholder assistant turn's `sources`, build
  messages, `_start_chat_worker`.
- Hit path (and not-fetchable): unchanged from today.
- Factor the retrieval (search_ranked + passage building) into a `_retrieve(question)`
  helper used by both the hit path and `_on_fetch_done`.

### 5. Edge cases
- **Offline / API error:** worker emits `error` → still call `_on_fetch_done` →
  retrieval finds nothing new → answer with no passages (LLM general knowledge /
  "not in the guide"). No crash, no blocking.
- **No wiki_url for the active game:** miss path is skipped; answer as today.
- **Zero search results:** `run_on_demand_fetch` returns 0; same as offline.
- **Dedupe:** `add_article` idempotent by pageid; re-fetch is a no-op.
- **Cancellation:** if the overlay hides mid-fetch, tear down the fetch thread like
  the chat thread (`shutdown`).

## Testing strategy
- `WikiClient.search_titles` / `fetch_by_titles`: injected fake `http_get` returning
  canned `list=search` and `prop=extracts` JSON (mirror existing `test_wiki_client`).
- `run_on_demand_fetch`: fake client (search returns titles, fetch returns
  `WikiArticle`s incl. one noise title) → asserts non-noise ingested with the right
  `game_id`, noise skipped, count returned, idempotent on re-run.
- `OnDemandFetchWorker`: like `test_ingest_worker` — fake client, real temp DB,
  assert rows land with `game_id`.
- `_on_send` miss branch: verified by offscreen smoke (inject a fake fetch worker /
  client) — the heavy logic is in the pure function, so window code stays thin.
- Full suite stays green.

## Risks
- Async sequencing in `_on_send` (fetch → then chat) must not double-append turns or
  drop the `history`-before-append ordering. Mitigation: factor `_retrieve`, capture
  history first, reuse the existing placeholder assistant turn for streaming.
- TextExtracts per-request caps: fetching 3 titles may need ≤3 requests; acceptable
  latency for an on-demand path (status shown).
