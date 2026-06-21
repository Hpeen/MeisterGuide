# Content fetch for wikis without TextExtracts (parse + trafilatura) — design

**Date:** 2026-06-21
**Status:** Approved, ready for planning

## Problem

The app fetches article text with the MediaWiki `prop=extracts` (TextExtracts)
API. minecraft.wiki has that extension, but **Fandom wikis do not** — verified
against Subnautica: `meta=siteinfo` reports no TextExtracts, and `prop=extracts`
returns pages with only `ns/pageid/title` and no `extract`. So the ingest drops
every page and stores **zero** articles. This breaks all three knowledge paths for
Fandom games (full download, on-demand fetch, category seed), since they share the
extracts-based fetch. Fandom hosts most game wikis, so the multi-game feature is
effectively unusable without this fix.

Raw content IS available on Fandom via `action=parse` (rendered HTML). Validated:
`action=parse&prop=text` for "Reaper Leviathan"/"Seamoth" returned 84k/114k chars
of HTML, and `trafilatura.extract(html, include_tables=True)` produced 4.7k/9.9k
chars of clean article text. trafilatura is already a bundled dependency (used by
the web-search fallback).

## Decisions (locked during brainstorming)

- **Auto-detect per wiki.** One `siteinfo` check per `WikiClient`: TextExtracts
  present → keep the light `prop=extracts` path (minecraft.wiki); absent → use
  `action=parse` → HTML → trafilatura (Fandom). Avoids ~10–20× heavier downloads
  for large TextExtracts wikis while fixing Fandom.
- **Contained in `WikiClient`.** Every consumer talks to the wiki only through
  `WikiClient` (`iter_batches`, `fetch_by_titles`, `article_count`, …), so the
  branch lives inside `WikiClient`. `ingest.py`, `on_demand.py`, `seed.py`,
  `worker.py`, `window.py` are unchanged.
- **Injectable extraction seam.** A constructor-injected `extract` callable
  (default lazy-imports trafilatura) so tests run offline without trafilatura,
  mirroring the existing `http_get`/`sleep` seams.

## Non-goals

- Re-fetching the existing Minecraft corpus (it stays; add_article is idempotent
  by pageid). Changing redirect/category/search enumeration (no body text). A
  wikitext-stripping path (we use rendered HTML + trafilatura, which is cleaner).
  Per-page caching of the siteinfo result across `WikiClient` instances.

## Components — all in `meister_guide/scraper/wiki_client.py`

### 1. Injectable extraction seam

Add an `extract=None` constructor param and a default:

```
def __init__(self, api_url=DEFAULT_API, http_get=None, delay=0.0,
             sleep=time.sleep, max_retries=5, backoff=1.0, extract=None):
    ...
    self._extract = extract or self._default_extract

@staticmethod
def _default_extract(html):
    import trafilatura
    return trafilatura.extract(html, include_comments=False,
                               include_tables=True) or ""
```

Network/library errors from the default propagate to `_fetch`-level handling or
are caught by the worker, same as today.

### 2. Capability detection — `has_textextracts()`

```
def has_textextracts(self):
    """True if the wiki has the TextExtracts extension (cached). On a detection
    failure, returns False so we use the universal parse path."""
```

- Caches on the instance (e.g. `self._has_extracts`, sentinel-initialized) so the
  `siteinfo` call happens once per `WikiClient`.
- Calls `_fetch({action:query, meta:siteinfo, siprop:extensions, maxlag:5})` and
  checks whether any extension's `name` equals `"TextExtracts"`.
- Wrap in try/except: on error, cache and return `False` (parse path).

### 3. Single-page parse fetch — `_parse_page(title)`

```
def _parse_page(self, title):
    """Fetch one page via action=parse, extract plain text with self._extract,
    and return a WikiArticle (or None if the page has no usable text)."""
```

- `_fetch({action:parse, format:json, page:title, prop:text,
  formatversion:2, redirects:1, maxlag:5})`.
- From `data["parse"]`: `pageid`, `title` (the resolved title), `revid`, and
  `text` (HTML; with `formatversion=2` it is a plain string).
- `text = self._extract(html)`; if empty/whitespace, return `None`.
- Return `WikiArticle(pageid, resolved_title, text, revid)`.
- A missing `parse` key (e.g. a nonexistent page returns an `error`) → `None`
  (a parse error for a single title shouldn't abort a bulk walk; `_fetch` already
  raises only for non-`badcontinue`/`maxlag` API errors — see error handling).

### 4. `iter_batches(start_token=None)` — branch on capability

- **TextExtracts present:** unchanged (today's `generator=allpages` +
  `prop=extracts` via `_params`, yielding `(articles, next_token)`).
- **Absent (parse path):** enumerate article-namespace titles with
  `list=allpages` (`apnamespace=0`, `aplimit=50`, `maxlag=5`, follow `apcontinue`),
  and for each returned title call `_parse_page`; collect the non-None
  `WikiArticle`s for that enumeration page and `yield (articles, next_token)`,
  where `next_token = json.dumps(data["continue"])` or `None`. Sleep `self._delay`
  between enumeration pages (as the extracts path does). `aplimit=50` keeps a batch
  to ~50 parse calls so per-batch commits stay frequent.

The `(list[WikiArticle], next_token|None)` contract and resume semantics are
identical, so `run_ingest` is unchanged. The resume token is the `allpages`
`apcontinue` for parse wikis (opaque JSON, stored per game) vs `gapcontinue` for
extracts wikis — never mixed, since a wiki is consistently one path.

### 5. `fetch_by_titles(titles)` — branch on capability

- **TextExtracts present:** unchanged (one `prop=extracts` request for all titles).
- **Absent:** `return [a for a in (self._parse_page(t) for t in titles)
  if a is not None]` (one `action=parse` per title).

Used by on-demand fetch and category seed; both keep working unchanged.

## Unaffected

`article_count` (siteinfo statistics — works on Fandom), `search_titles`
(`list=search`), `iter_redirect_mappings`, `iter_category_members` — none fetch
body text. `run_ingest`, `run_redirect_ingest`, `run_on_demand_fetch`,
`run_category_seed`, `IngestWorker`/`OnDemandFetchWorker`/`CategorySeedWorker`,
and the window are unchanged.

## Error handling

- `siteinfo` detection failure → `has_textextracts()` returns `False` → parse path
  (then real network errors surface through the normal retry/`_fetch` flow).
- Empty extracted text for a page → skipped (same as the extracts path dropping a
  page with no `extract`).
- A single page's `action=parse` returning an API error (e.g. missing page) →
  `_parse_page` returns `None`; the bulk walk and `fetch_by_titles` continue.
- trafilatura import/parse failure in the default `extract` → propagates to the
  worker's existing try/except (emits `error`, no crash). Documented dependency:
  trafilatura must be installed (already in `requirements.txt`).

## Testing (TDD) — `tests/test_wiki_client.py`

Inject `http_get` (canned JSON) and `extract` (a stub) so tests need no network or
trafilatura.

**Detection**
- `has_textextracts()` returns True when siteinfo lists a `TextExtracts` extension,
  False when it doesn't; the `http_get` is called only once across repeated calls
  (caching); returns False when the siteinfo call raises.

**Parse path**
- `_parse_page` builds a `WikiArticle(pageid, title, text, revid)` from a canned
  `action=parse` response, using the injected `extract`; returns `None` when the
  extracted text is empty; returns `None` when the response has no `parse` key.
- `fetch_by_titles` on a no-TextExtracts client (siteinfo stub → no extension)
  returns one `WikiArticle` per resolvable title via the parse path, skipping
  empties.
- `iter_batches` on a no-TextExtracts client walks `list=allpages`, parses each
  title, yields `(articles, next_token)` with the `apcontinue` token, and
  terminates when `continue` is absent.

**Regression**
- Existing `iter_batches` / `fetch_by_titles` extracts-path tests still pass. Note:
  because those methods now run detection first, each affected test's injected
  `http_get` must also answer the `meta=siteinfo&siprop=extensions` request with a
  TextExtracts-present response so the client takes the old extracts path. (Update
  the existing fakes accordingly — they currently only canned the extracts/batch
  responses.)

**Real-wiki validation (already done, document only):** `action=parse` +
`trafilatura` on live Subnautica pages yields clean multi-thousand-char text.

## Build approach

One feature branch (`fandom-parse-fetch`), TDD per task, subagent-driven with
per-task spec + quality review and a final whole-branch review, then
`finishing-a-development-branch`. Run tests with `py -m pytest -q`. After merge,
rebuild the exe (the build copies it into `Launch from here/`).
