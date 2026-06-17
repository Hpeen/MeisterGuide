# Design — Phase 5: Better Answers (retrieval-first RAG quality)

**Date:** 2026-06-17
**Status:** Approved (design), ready to plan
**Builds on:** Phase 3 (`ArticlesRepo` + FTS5 guides) and Phase 4 (Meister chat:
Ollama client, `relevant_passage`, `build_messages`, the Chat tab).

## Problem

Phase 4 shipped a working chat, but answers are weak — and tracing the live
pipeline (17,149 articles ingested) showed the cause is **retrieval, not the
model**:

- "how do I make a nether portal?" → top 3 hits were a Bedrock version
  changelog and two *A Minecraft Movie* pages.
- "how do creepers work?" → top 3 were all Bedrock beta changelogs.
- Even the bare query "creeper" ranked the real *Creeper* article (pageid 628)
  3rd, behind "Creeper (disambiguation)" and "Creeper Head".

Two root causes:
1. **Question words pollute the query.** "how do I make a" is fed into the
   keyword index and rewards changelog/movie pages that repeat those words.
2. **Noise pages outrank canonical articles.** Disambiguation pages, version /
   changelog pages, history subpages, and movie/event pages match keywords
   heavily but are useless as answer sources.

No model can answer well from a beta changelog. Fix retrieval first, then lean
on a stronger model for readability.

## Goal

Make Meister retrieve the *correct* article for a question, then generate the
answer with the strongest installed local model. Stays fully offline, adds no
new dependencies, and requires no re-ingest of the guide database.

## Locked decisions (from brainstorming)

- **Success criterion:** right source + grounded answer first, readability
  second.
- **Approach A (heuristic FTS re-ranking)**, not embeddings/vector search.
  Embeddings (and a hybrid re-rank) are deferred — the observed failures are
  "the wrong article wins," which title-boosting + noise-filtering + query
  cleaning fix cleanly and cheaply.
- **Model:** auto-pick the *strongest* completion-capable installed model
  (e.g. `qwen2.5:32b`) instead of the naive "first llama3", with a safe
  fallback.
- The Guides-tab search behaviour is unchanged; only the **chat** retrieval
  path is improved.

## Components

Each unit is pure and testable in isolation where possible.

### 1. `meister_guide/ai/query.py` — query cleaning (pure, new)
- `clean_query(text) -> list[str]`: lowercase, strip punctuation, drop a small
  curated stop/question-word set ("how", "do", "does", "did", "i", "you", "to",
  "a", "an", "the", "make", "made", "work", "works", "get", "is", "are", "of",
  "in", "on", "for", "what", "why", "when", "where", "can", "should", "my",
  etc.), drop tokens shorter than 2 chars, de-duplicate preserving order.
  `"how do I make a nether portal?"` → `["nether", "portal"]`.
  If cleaning removes everything (e.g. all stop words), fall back to the raw
  word tokens so a query is never empty.

### 2. `meister_guide/ai/ranking.py` — noise classification + re-ranker (pure, new)
- `noise_penalty(title) -> float`: returns a non-negative penalty.
  - Disambiguation pages (`title` ends with `"(disambiguation)"`): a very large
    penalty so they sink below any real article (de-facto excluded, but handled
    uniformly through scoring rather than a special-case skip).
  - Version/changelog pages — titles matching things like
    `^(Java|Bedrock|Legacy Console|Pocket) Edition`, a version-number pattern
    (`\d+\.\d+`), or ending in `/Development versions`: heavy penalty.
  - History/texture-history subpages (title contains `" history"` or
    `"/…history"`): heavy penalty.
  - Movie/event pages (`"A Minecraft Movie"`, `"Live Event"`): heavy penalty.
  - Everything else: `0.0`.
  Patterns are deliberately conservative (anchored / specific) so ordinary
  article titles score `0.0`. Every branch gets a test, including
  counter-examples that must NOT be penalised (e.g. "Creeper", "Nether",
  "Crafting Table", "History" as a standalone gameplay topic if such exists —
  guarded by requiring the `" history"` substring with a leading space).
- `title_boost(title, terms) -> float`: boost from overlap between the cleaned
  query `terms` and the title's lowercased word set. Exact full match (every
  term present) earns the largest boost; partial overlap scales down; a title
  that is *exactly* the joined terms earns an extra bump. No match → `0.0`.
- `rerank(candidates, terms, limit=3) -> list[SearchHit]`: `candidates` is a
  list of `(rank, SearchHit)` pairs, where `rank` is the SQLite FTS5 bm25 rank
  (more-negative = better). Compute
  `final = (−rank) + title_boost(title, terms) − noise_penalty(title)` and
  return the top `limit` hits (highest `final` first). Pure: takes
  already-fetched candidates, returns a reordered list of `SearchHit`s. The bm25
  term is weighted modestly so a strong title match / noise penalty can override
  raw keyword frequency (constants tuned against the documented failing cases).

### 3. `meister_guide/db/articles.py` — chat retrieval path
- Add `search_ranked(raw_query, limit=3, candidate_pool=15) -> list[SearchHit]`:
  `terms = clean_query(raw_query)`; build the FTS query via
  `_to_fts_query(" ".join(terms))`; fetch up to `candidate_pool` rows selecting
  both `rowid` and the FTS5 `rank` column (`SELECT rowid, rank FROM articles_fts
  WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?`); materialise each into a
  `SearchHit` paired with its `rank`; hand the `(rank, hit)` list to
  `ranking.rerank(..., terms, limit)`; return the result. The existing
  `search()` (Guides tab) and `SearchHit` shape are untouched — `rank` lives
  only inside `search_ranked`'s local pairs.

### 4. `meister_guide/ai/ollama_client.py` — strongest-model auto-pick
- Extend model discovery to use `/api/tags` `details.parameter_size`
  (e.g. `"32.8B"`) and `capabilities` (e.g. `["completion"]`,
  `["completion","tools"]`, `["vision","completion"]`).
- New `pick_best_model(models) -> str | None` where `models` is the raw list of
  dicts from `/api/tags`: keep only models whose `capabilities` include
  `"completion"` and are **not** vision/embedding-only; parse `parameter_size`
  to a float (`"32.8B"`→32.8, `"8.0B"`→8.0, missing→0); return the name with the
  largest size. Ties / no size info → fall back to the existing `pick_model`
  name-preference (llama3* then first).
- `list_models()` keeps returning names (Guides/other callers unaffected); add
  `list_model_info() -> list[dict]` returning the raw entries, and have the Chat
  tab's `_detect_ollama` use `list_model_info()` + `pick_best_model`.
  `OllamaUnavailable` handling is unchanged.

### 5. `meister_guide/ai/prompt.py` — prompt tuning (readability)
- Tighten `SYSTEM_PREAMBLE`: instruct Meister to answer **using the supplied
  guide excerpts**, give a short step-by-step when the question is "how do I…",
  stay faithful to the excerpts, and clearly say when the excerpts don't cover
  the question instead of inventing. Keep it concise. The `messages` array shape
  is unchanged, so existing `prompt` tests adjust only for wording.

### 6. Chat tab wiring (`meister_guide/overlay/window.py`)
- `_on_send` calls `articles_repo.search_ranked(question, limit=3)` instead of
  `search(question, limit=3)`.
- `_detect_ollama` picks the model via `pick_best_model(list_model_info())`.
- No UI/threading changes; citations already show the chosen sources.

## Data flow

```
Send(question)
  terms   = clean_query(question)                     # ["nether","portal"]
  cands   = ArticlesRepo FTS top-15 for terms (+bm25 rank)
  hits    = ranking.rerank(cands, terms, limit=3)     # title-boost − noise
  passages= [(h.title, relevant_passage(body, question)) for h in hits]
  model   = pick_best_model(list_model_info())        # qwen2.5:32b
  messages= build_messages(question, passages, history)
  stream …
```

## Error handling
- Unchanged from Phase 4: Ollama down / no model / stream error / cancel all
  behave as before. `pick_best_model` returning `None` → the existing "install a
  model" state.
- If `clean_query` empties the query, fall back to raw tokens so search still
  runs.
- If re-ranking filters everything out (all candidates heavily penalised), fall
  back to the top FTS hits so the user still gets *something*.

## Testing
- `query.clean_query`: question→terms, stop-word removal, punctuation, empty
  fallback, de-dup.
- `ranking.noise_penalty`: each junk class penalised; real article titles score
  0 (Creeper, Nether, Crafting Table, …).
- `ranking.title_boost`: exact match > partial > none.
- `ranking.rerank`: the documented failing cases — feeding realistic candidate
  sets, *Creeper* beats "Creeper (disambiguation)"/"Creeper Head"; a topic
  article beats version changelogs.
- `articles.search_ranked` (in-memory SQLite seeded with a canonical article +
  decoy noise titles): returns the canonical article first.
- `ollama_client.pick_best_model`: largest completion model wins; vision/
  embedding-only skipped; missing-size fallback to name preference.
- `prompt`: message array shape intact after wording change.
- Existing Guides-tab `search` tests still pass (path untouched).

## Out of scope (deferred)
- Redirect ingestion (needs a scraper change + re-walk of ~17k articles).
- Embeddings / vector search / hybrid re-rank (Approach B/C).
- Model-picker UI, temperature/params, Claude API backend (Settings phase).

## Post-phase deliverables (user request)
When Phase 5 is complete: write a Phase 5 devlog (the established playful
first-person voice) **and** a standalone whole-project description suitable for
posting on the Stardance challenge as a catch-up.
