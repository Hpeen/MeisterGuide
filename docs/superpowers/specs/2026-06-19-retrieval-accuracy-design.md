# Retrieval Accuracy — Design Spec

**Date:** 2026-06-19
**Status:** Approved, ready for implementation planning
**Scope:** Three tiers (RC-0 corpus completeness, RC-A passage windowing, RC-B ranking)

## Problem

User report: asking "when do spiders spawn with potion effects" returned no answer,
even though the answer (regular spiders can spawn with random status effects in Hard
difficulty) is wiki-documented. The offline guide feels inaccurate.

## Root-cause investigation (evidence)

Reproduced against the live DB (`%APPDATA%/MeisterGuide/meister.db`, 17,916 articles):

- **RC-0 — Corpus is half-downloaded (dominant cause).**
  `scrape_state` still holds a resume token (`gapcontinue="Enderman_Man"`,
  `done=17915`, `total=16693`). Coverage is alphabetically truncated: every page
  `<= "E"` is present (Creeper, Difficulty, Enderman); every page `> "E"` is absent
  (Mob, Skeleton, Spider, Zombie). The `redirects` table is empty (0 rows) because
  the redirect pass only runs *after* the article walk finishes. No retrieval change
  can surface an article that was never downloaded.
  The progress overshoot bug (`17,915 / 16,693`, and the idle "17,916 articles"
  label) makes the half-finished download *look* complete, which is why it was
  stopped early. The cosmetic bug and the accuracy complaint share one root.

- **RC-A — Passage window slices out the answer (real, secondary).**
  For an article that IS present and DOES contain the answer (Cave Spider, fact at
  byte offset 1659), `relevant_passage` anchors its 1500-char window on the earliest
  single-term match ("spider" at index ~5 → the intro), so the window is
  `body[0:1500]` and ends 159 chars before the answer. The model never receives it.
  `window_bounds` also includes stopwords from the raw query, dragging the anchor to
  index 0.

- **RC-B — Ranking surfaces generic over specific (real, secondary).**
  Top-3 for the spider query were *Cave Spider, Effect, Effect colors*. The generic
  "Effect" article (no Hard-difficulty rule) outranked anything spider-specific
  because `title_boost` gives a single-word title match ("Effect" vs term "effects")
  the same 250 as "Cave Spider", and bm25 then favored the effect-dense article.

## Design

### Tier 1 — Corpus completeness + honest completion state (RC-0)

- New pure helper `guides_status_text(article_count, scrape_state, redirect_state)`:
  - article resume token present → `"Incomplete — {n:,} downloaded · click Update to resume"`
  - article token cleared but redirect pass not done → `"Linking related topics…"` (resumable)
  - both done → `"Complete · {n:,} articles"`
- `_refresh_guides_status` uses the helper instead of the bare `"{n} articles"`.
- Running progress keeps the `effective_total = max(total, done)` inversion fix (so
  the bar cannot overflow), but status text reflects the phase ("Downloading…" vs
  "Linking…") and never implies "done" while a token exists. This supersedes and
  folds in the earlier inline edit to `_on_ingest_progress`.
- Resume stays **manual** (clicking Update guides resumes from the saved token — no
  surprise background network use). Honesty about incompleteness is the fix, not
  auto-resume.
- The helper is unit-testable (counts + token presence in, string out); Qt wiring
  stays thin.

### Tier 2 — Cluster-based passage window (RC-A)

- Clean the query to content terms (reuse `clean_query`) and add de-inflected
  variants (reuse `_deinflect` from `ranking.py`) so "potion **effects**" matches
  "status **effect**" and "**spiders**" matches "**spider**".
- New `best_window(body, terms, width)`: collect all term occurrence positions, pick
  the `width`-char window covering the **most distinct terms** (tie-break: most total
  hits, then earliest). Lands Cave Spider on the offset-1659 cluster instead of the
  intro.
- Widen RAG passage width (1500 → ~2000) for headroom.
- `make_excerpt` (Guides-tab preview) and `relevant_passage` (RAG) both move onto the
  shared helper (they are explicit siblings). HTML-highlight behavior in
  `make_excerpt` is preserved.

### Tier 3 — Ranking favors specific over generic (RC-B), reusing Tier 2

- `search_ranked` already decompresses every candidate body to build its excerpt, so
  computing each candidate's best-window distinct-term coverage is nearly free.
- Extend `rerank`:
  `score = title_boost + cluster_coverage_boost − noise_penalty + (−bm25_rank)`
  where `cluster_coverage_boost` rewards a candidate whose best window contains more
  *distinct* query terms. The spider article (window: spider+spawn+effect+difficulty)
  outscores "Effect" (window: effect+potion only).

## End-to-end validation (acceptance)

After Tier 1 finishes the download, the regular **Spider** article lands. Tier 3
ranks it above generic "Effect"; Tier 2 puts the Hard-difficulty sentence inside the
passage. The originally failing question becomes answerable.

## Constraints / non-goals

- No schema changes. No scraper/MediaWiki-API changes — the walk already resumes
  correctly; we stop hiding that it is unfinished.
- `window_bounds`/`make_excerpt` are shared with the Guides-tab preview; the change
  improves that preview too (intended), keeping HTML highlighting intact.
- Resumption logic is covered by fake-client unit tests. Actually finishing the live
  corpus is a runtime action the user performs; it cannot be fully proven offline.

## Testing strategy

- `guides_status_text`: pure-function unit tests over (count, scrape_state token,
  redirect_state done) combinations.
- `best_window`: unit tests asserting the window covers the densest distinct-term
  cluster, including the Cave-Spider-style "answer below the intro" case.
- `rerank` with cluster coverage: unit test that a topic-specific article outranks a
  generic single-word-title article for a multi-term query.
- Existing 159 tests must stay green.
