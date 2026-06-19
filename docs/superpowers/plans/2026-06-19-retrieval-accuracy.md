# Retrieval Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the offline guide actually answer questions like "when do spiders spawn with potion effects" by (1) surfacing that the corpus is half-downloaded so the user finishes it, (2) selecting the passage region that contains the answer, and (3) ranking the topic-specific article above generic ones.

**Architecture:** Three tiers from the approved spec. A shared cluster-window finder (`best_window`) in `scraper/excerpt.py` does double duty: it places the RAG passage (Tier 2) and scores per-article topic coverage for re-ranking (Tier 3). A pure `guides_status_text` helper drives an honest completion state in the Guides tab (Tier 1). No schema or MediaWiki-API changes.

**Tech Stack:** Python 3.12, SQLite + FTS5, PySide6 (Qt), pytest. Run tests with `py -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-19-retrieval-accuracy-design.md`

**Branch:** `retrieval-accuracy` (already checked out; spec already committed). Note `meister_guide/overlay/window.py` has one uncommitted edit from investigation — the `effective_total = max(total, done)` progress-bar fix; Task 8 builds on it.

---

## File map

- `meister_guide/scraper/excerpt.py` — add `deinflect()` and `best_window()`; reimplement `window_bounds()` on top of `best_window`. (Text-utility module already imported by both `ai` and `db`.)
- `meister_guide/ai/ranking.py` — `_deinflect` delegates to the shared `deinflect`; `rerank()` gains an optional `coverage` boost.
- `meister_guide/ai/passage.py` — `relevant_passage()` uses cleaned terms + `best_window`, width 1500 → 2000.
- `meister_guide/db/articles.py` — `_terms_to_or_query` uses shared `deinflect`; `search_ranked()` computes per-candidate coverage and passes it to `rerank`.
- `meister_guide/guides_status.py` — NEW pure module: `guides_status_text()`.
- `meister_guide/overlay/window.py` — `_refresh_guides_status` uses the helper; constructor accepts state repos; `_on_ingest_progress` phase text.
- `meister_guide/main.py` — build and pass `ScrapeStateRepo`/`RedirectStateRepo` to the window.
- Tests: `tests/test_excerpt.py`, `tests/test_passage.py`, `tests/test_ranking.py`, `tests/test_articles_repo.py`, `tests/test_guides_status.py` (new).

---

## Task 1: Shared `deinflect` text helper (DRY consolidation)

**Files:**
- Modify: `meister_guide/scraper/excerpt.py`
- Modify: `meister_guide/ai/ranking.py:29-37`
- Modify: `meister_guide/db/articles.py:166-184`
- Test: `tests/test_excerpt.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_excerpt.py`:

```python
def test_deinflect_strips_plurals():
    from meister_guide.scraper.excerpt import deinflect
    assert deinflect("spiders") == "spider"
    assert deinflect("effects") == "effect"
    assert deinflect("torches") == "torch"   # 'es' rule
    assert deinflect("ash") == "ash"          # too short to strip
    assert deinflect("redstone") == "redstone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_excerpt.py::test_deinflect_strips_plurals -v`
Expected: FAIL — `ImportError: cannot import name 'deinflect'`.

- [ ] **Step 3: Add `deinflect` to `excerpt.py`**

Insert near the top of `meister_guide/scraper/excerpt.py` (after the `_WORD` definition):

```python
def deinflect(word: str) -> str:
    """Crude English de-inflection: strip a trailing 'es'/'s' so a plural query
    term lines up with a singular body/title form. Shared by ranking, the OR
    recall query, and the cluster-window finder so they all agree."""
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word
```

- [ ] **Step 4: Delegate the two existing copies to it**

In `meister_guide/ai/ranking.py`, replace the body of `_deinflect` (lines 29-37) with a delegation, and add the import at the top:

```python
from meister_guide.scraper.excerpt import deinflect as _deinflect
```

Delete the old `def _deinflect(word): ...` block entirely (the imported name replaces it; `title_boost` still calls `_deinflect`).

In `meister_guide/db/articles.py`, update the top imports to include `deinflect` and replace the inline de-inflection inside `_terms_to_or_query` (lines 174-179):

```python
from meister_guide.scraper.excerpt import make_excerpt, deinflect
```

```python
        for t in terms:
            candidates_t = [t]
            root = deinflect(t)
            if root != t:
                candidates_t.append(root)
            for candidate in candidates_t:
                if candidate not in seen:
                    seen.add(candidate)
                    parts.append(f'"{candidate}"*')
```

- [ ] **Step 5: Run tests**

Run: `py -m pytest tests/test_excerpt.py tests/test_ranking.py tests/test_articles_repo.py -v`
Expected: PASS (existing ranking/article tests still green; new deinflect test passes).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/scraper/excerpt.py meister_guide/ai/ranking.py meister_guide/db/articles.py tests/test_excerpt.py
git commit -m "refactor: consolidate de-inflection into shared excerpt.deinflect"
```

---

## Task 2: `best_window` cluster finder

**Files:**
- Modify: `meister_guide/scraper/excerpt.py`
- Test: `tests/test_excerpt.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_excerpt.py`:

```python
def test_best_window_picks_densest_cluster_not_intro():
    from meister_guide.scraper.excerpt import best_window
    intro = "A spider is a mob. "                 # only 'spider' near index 0
    filler = "filler " * 300                       # ~2100 chars
    answer = "In Hard difficulty spiders spawn with a status effect."
    body = intro + filler + answer
    terms = ["spiders", "spawn", "potion", "effects"]
    start, end, distinct = best_window(body, terms, 2000)
    assert body[start:end].find("Hard difficulty") != -1   # answer is inside
    assert distinct >= 3                                    # spider+spawn+effect

def test_best_window_single_term_centers_on_match():
    from meister_guide.scraper.excerpt import best_window
    body = "x" * 100 + "creeper" + "y" * 100
    start, end, distinct = best_window(body, ["creeper"], 60)
    assert start <= 100 < end
    assert distinct == 1
    assert end - start <= 60

def test_best_window_no_match_is_leading_window():
    from meister_guide.scraper.excerpt import best_window
    assert best_window("alpha beta", ["zzz"], 5) == (0, 5, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_excerpt.py -k best_window -v`
Expected: FAIL — `ImportError: cannot import name 'best_window'`.

- [ ] **Step 3: Implement `best_window`**

Add to `meister_guide/scraper/excerpt.py`:

```python
def _occurrences(lowered: str, roots: list) -> list:
    """All (pos, root_index) substring hits, sorted by pos. Capped per root so a
    ubiquitous term can't blow up cost on a long body."""
    hits = []
    for ri, root in enumerate(roots):
        if not root:
            continue
        start, found = 0, 0
        while found < 200:
            idx = lowered.find(root, start)
            if idx == -1:
                break
            hits.append((idx, ri))
            start = idx + len(root)
            found += 1
    hits.sort()
    return hits


def best_window(body: str, terms, width: int) -> tuple:
    """Return (start, end, distinct_count): the `width`-char window of `body`
    covering the most DISTINCT de-inflected `terms`. Falls back to the leading
    window when nothing matches. Terms are de-inflected and substring-matched, so
    a query 'effects' lands on body text 'effect'/'effects' alike. Used both to
    place the RAG passage and to score topic coverage in ranking."""
    roots, seen = [], set()
    for t in terms:
        r = deinflect(t.lower())
        if r and r not in seen:
            seen.add(r)
            roots.append(r)
    lowered = body.lower()
    hits = _occurrences(lowered, roots)
    if not hits:
        return 0, min(len(body), width), 0

    # Two-pointer over sorted hit positions: the width-span containing the most
    # distinct roots (tie-break: more total hits, then earliest).
    counts = {}
    distinct = 0
    left = 0
    best_distinct, best_total, best_lo, best_hi = 0, 0, hits[0][0], hits[0][0]
    for right in range(len(hits)):
        _, root_r = hits[right]
        counts[root_r] = counts.get(root_r, 0) + 1
        if counts[root_r] == 1:
            distinct += 1
        while hits[right][0] - hits[left][0] > width:
            _, root_l = hits[left]
            counts[root_l] -= 1
            if counts[root_l] == 0:
                distinct -= 1
            left += 1
        total = right - left + 1
        lo, hi = hits[left][0], hits[right][0]
        if (distinct, total, -lo) > (best_distinct, best_total, -best_lo):
            best_distinct, best_total, best_lo, best_hi = distinct, total, lo, hi

    mid = (best_lo + best_hi) // 2
    start = max(0, mid - width // 2)
    end = min(len(body), start + width)
    start = max(0, end - width)
    return start, end, best_distinct
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_excerpt.py -k best_window -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/excerpt.py tests/test_excerpt.py
git commit -m "feat: best_window cluster finder for passage selection"
```

---

## Task 3: Reimplement `window_bounds` on top of `best_window`

**Files:**
- Modify: `meister_guide/scraper/excerpt.py:11-25`
- Test: `tests/test_excerpt.py` (existing tests guard behavior)

- [ ] **Step 1: Add a guard test for multi-term placement**

Add to `tests/test_excerpt.py`:

```python
def test_window_bounds_multi_term_prefers_cluster():
    from meister_guide.scraper.excerpt import window_bounds
    body = "spider intro. " + ("z" * 400) + " spider spawn effect cluster."
    start, end = window_bounds(body, "spider spawn effect", 120)
    assert "cluster" in body[start:end]   # not the lone 'spider' in the intro
```

- [ ] **Step 2: Run it to verify it fails**

Run: `py -m pytest tests/test_excerpt.py::test_window_bounds_multi_term_prefers_cluster -v`
Expected: FAIL — current `window_bounds` anchors on the first single match (intro), so "cluster" is not in the window.

- [ ] **Step 3: Reimplement `window_bounds`**

Replace `window_bounds` (lines 11-25) in `meister_guide/scraper/excerpt.py` with a thin wrapper that keeps the `(start, end)` contract:

```python
def window_bounds(body: str, query: str, width: int) -> tuple:
    """Return (start, end) of a `width`-char window over the densest cluster of
    query terms (or the leading window when nothing matches). Thin wrapper over
    best_window so excerpt highlighting and RAG passage selection share placement."""
    terms = _WORD.findall(query.lower())
    start, end, _ = best_window(body, terms, width)
    return start, end
```

- [ ] **Step 4: Run the full excerpt suite**

Run: `py -m pytest tests/test_excerpt.py -v`
Expected: PASS — including the pre-existing `test_window_bounds_centers_on_match`, `test_window_bounds_no_match_is_leading_window`, `test_window_around_match_with_ellipsis`, `test_no_match_returns_leading_text`, and the new multi-term test.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/scraper/excerpt.py tests/test_excerpt.py
git commit -m "refactor: window_bounds delegates to best_window (cluster-aware)"
```

---

## Task 4: Cluster passage + wider window in `relevant_passage`

**Files:**
- Modify: `meister_guide/ai/passage.py`
- Test: `tests/test_passage.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_passage.py`:

```python
def test_passage_includes_answer_below_intro():
    from meister_guide.ai.passage import relevant_passage
    intro = "A spider is a common mob. "
    filler = "filler " * 300                 # ~2100 chars, pushes answer past 1500
    answer = "In Hard difficulty, spiders spawn with a random status effect."
    body = intro + filler + answer
    # The raw question's stopwords (when/do/with) must not drag the window to 0.
    passage = relevant_passage(body, "when do spiders spawn with potion effects")
    assert "Hard difficulty" in passage
    assert "status effect" in passage

def test_passage_default_width_is_2000():
    from meister_guide.ai.passage import relevant_passage
    body = "creeper " * 1000
    passage = relevant_passage(body, "creeper")
    # ~2000-char window, not the old 1500.
    assert 1800 <= len(passage.strip("…")) <= 2000
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest tests/test_passage.py -k "below_intro or width_is_2000" -v`
Expected: FAIL — current `relevant_passage` uses width 1500 and `window_bounds` anchored on the intro.

- [ ] **Step 3: Reimplement `relevant_passage`**

Replace the contents of `meister_guide/ai/passage.py` with:

```python
"""Plain-text relevance window for RAG context (model input).

Sibling of scraper.excerpt.make_excerpt, but returns plain text (no HTML
escaping or <b> highlighting) since it feeds the model, not a QLabel. Uses the
cleaned content terms (not raw question words) so question stopwords don't drag
the window onto the article intro."""
from meister_guide.scraper.excerpt import best_window
from meister_guide.ai.query import clean_query


def relevant_passage(body: str, query: str, width: int = 2000) -> str:
    terms = clean_query(query)
    start, end, _ = best_window(body, terms, width)
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet}{suffix}"
```

- [ ] **Step 4: Run to verify pass**

Run: `py -m pytest tests/test_passage.py -v`
Expected: PASS (new tests + any existing passage tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/passage.py tests/test_passage.py
git commit -m "feat: cluster-based RAG passage, widen window to 2000"
```

---

## Task 5: `rerank` coverage boost (ranking favors specific over generic)

**Files:**
- Modify: `meister_guide/ai/ranking.py:57-71`
- Test: `tests/test_ranking.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ranking.py`. NOTE: the file already defines a `Hit` namedtuple and a `_hit(title)` helper (pageid hardcoded to 1) used by existing tests — do NOT redefine `_hit`. Add a distinct `_covhit(pageid, title)` that reuses the existing `Hit` namedtuple (rerank only needs `.pageid` and `.title`):

```python
def _covhit(pageid, title):
    return Hit(pageid, title, "", None)


def test_coverage_boost_lifts_specific_over_generic():
    terms = ["spider", "spawn", "potion", "effect"]
    # Generic "Effect" has the better bm25 rank (more negative) but low coverage;
    # the specific article covers more distinct query terms.
    candidates = [(-9.0, _covhit(1, "Effect")), (-3.0, _covhit(2, "Cave Spider"))]
    coverage = {1: 2, 2: 3}
    ordered = rerank(candidates, terms, limit=2, coverage=coverage)
    assert ordered[0].pageid == 2   # Cave Spider wins on coverage

def test_rerank_without_coverage_is_unchanged():
    terms = ["spider", "spawn", "potion", "effect"]
    candidates = [(-9.0, _covhit(1, "Effect")), (-3.0, _covhit(2, "Cave Spider"))]
    ordered = rerank(candidates, terms, limit=2)   # no coverage arg
    assert ordered[0].pageid == 1   # bm25 (more negative) wins the title tie
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest tests/test_ranking.py -k coverage -v`
Expected: FAIL — `rerank()` has no `coverage` parameter (`TypeError`).

- [ ] **Step 3: Add the coverage boost**

In `meister_guide/ai/ranking.py`, add a constant near the other penalty constants:

```python
_COVERAGE_WEIGHT = 800.0   # full distinct-term coverage ~= a partial title match
```

Replace `rerank` (lines 57-71) with:

```python
def rerank(candidates, terms, limit=3, coverage=None):
    """`candidates`: list of (bm25_rank, hit). `coverage`: optional dict
    {hit.pageid: distinct query terms present in the hit's best passage window}.

    score = title_boost + coverage_boost − noise_penalty + (−bm25_rank)
    Title boost and noise penalty dominate; coverage_boost lifts a topic-specific
    article over a generic one when titles tie; bm25 only breaks remaining ties."""
    n = len(terms) or 1
    scored = []
    for rank, hit in candidates:
        cov = coverage.get(hit.pageid, 0) if coverage else 0
        cov_boost = _COVERAGE_WEIGHT * (cov / n)
        score = (title_boost(hit.title, terms) + cov_boost
                 - noise_penalty(hit.title) + (-rank))
        scored.append((score, hit))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [hit for _, hit in scored[:limit]]
```

- [ ] **Step 4: Run to verify pass**

Run: `py -m pytest tests/test_ranking.py -v`
Expected: PASS — new coverage tests plus all pre-existing ranking tests (unchanged because `coverage` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ranking.py tests/test_ranking.py
git commit -m "feat: coverage boost in rerank (specific beats generic)"
```

---

## Task 6: Wire coverage into `search_ranked`

**Files:**
- Modify: `meister_guide/db/articles.py:102-153`
- Test: `tests/test_articles_repo.py`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_articles_repo.py`. The file already provides a `_repo(tmp_path)` helper (creates `connect(tmp_path/"a.db")` + `init_db` + `ArticlesRepo`) — use it, with the standard `tmp_path` pytest fixture:

```python
def test_search_ranked_prefers_topic_specific_article(tmp_path):
    repo = _repo(tmp_path)
    # Generic page: dense in the effect/potion words (strong bm25) but no spider.
    repo.add_article(1, "Effect",
                     "Effect potion effect effect potion brewing effect potion. " * 20,
                     None, "u1")
    # Specific page: contains the actual answer cluster below an intro.
    repo.add_article(2, "Spider",
                     "A spider is a mob. " + ("filler " * 200) +
                     "In Hard difficulty spiders spawn with a random status effect.",
                     None, "u2")
    hits = repo.search_ranked("when do spiders spawn with potion effects", limit=2)
    assert hits[0].title == "Spider"
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest tests/test_articles_repo.py::test_search_ranked_prefers_topic_specific_article -v`
Expected: FAIL — without coverage, generic "Effect" (better bm25) ties/wins.

- [ ] **Step 3: Compute and pass coverage in `search_ranked`**

In `meister_guide/db/articles.py`, update the import (Task 1 already added `deinflect`; now also import `best_window`):

```python
from meister_guide.scraper.excerpt import make_excerpt, deinflect, best_window
```

In `search_ranked`, change the candidate-building loop (lines ~142-153) to also accumulate coverage and pass it to `rerank`:

```python
        candidates = []
        coverage = {}
        for rowid, rank in best_rank.items():
            row = self._conn.execute(
                "SELECT pageid, title, body_zlib, url FROM articles WHERE id = ?",
                (rowid,),
            ).fetchone()
            if row is None:
                continue
            body = zlib.decompress(row[2]).decode("utf-8")
            hit = SearchHit(row[0], row[1], make_excerpt(body, raw_query), row[3])
            # Topic coverage = distinct query terms inside the best passage window
            # (same width as the RAG passage), reused by rerank to favor specifics.
            _, _, cov = best_window(body, terms, 2000)
            coverage[hit.pageid] = cov
            candidates.append((rank, hit))
        return rerank(candidates, terms, limit, coverage=coverage)
```

- [ ] **Step 4: Run to verify pass**

Run: `py -m pytest tests/test_articles_repo.py -v`
Expected: PASS — the new test plus all existing article-repo tests.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_repo.py
git commit -m "feat: feed passage coverage into search_ranked re-ranking"
```

---

## Task 7: `guides_status_text` pure helper (honest completion state)

**Files:**
- Create: `meister_guide/guides_status.py`
- Test: `tests/test_guides_status.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guides_status.py`:

```python
from meister_guide.guides_status import guides_status_text


def test_no_guides():
    assert guides_status_text(0, articles_done=False, redirects_done=False) == \
        "No guides yet — click Update guides"

def test_incomplete_download():
    assert guides_status_text(17916, articles_done=False, redirects_done=False) == \
        "Incomplete — 17,916 downloaded · click Update to resume"

def test_articles_done_redirects_pending():
    assert guides_status_text(20000, articles_done=True, redirects_done=False) == \
        "Almost done — click Update to link related topics"

def test_complete():
    assert guides_status_text(20000, articles_done=True, redirects_done=True) == \
        "Complete · 20,000 articles"
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest tests/test_guides_status.py -v`
Expected: FAIL — `ModuleNotFoundError: meister_guide.guides_status`.

- [ ] **Step 3: Create the module**

Create `meister_guide/guides_status.py`:

```python
"""Pure helper: turn corpus counts + ingest completion flags into the Guides-tab
status line. Kept Qt-free and dependency-free so it is trivially unit-testable —
the overshoot bug hid that the download was unfinished, so completeness must be
stated honestly from the resume-token state, not implied by a full progress bar."""


def guides_status_text(article_count: int, articles_done: bool,
                       redirects_done: bool) -> str:
    if article_count <= 0:
        return "No guides yet — click Update guides"
    if not articles_done:
        return f"Incomplete — {article_count:,} downloaded · click Update to resume"
    if not redirects_done:
        return "Almost done — click Update to link related topics"
    return f"Complete · {article_count:,} articles"
```

- [ ] **Step 4: Run to verify pass**

Run: `py -m pytest tests/test_guides_status.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add meister_guide/guides_status.py tests/test_guides_status.py
git commit -m "feat: guides_status_text honest completion helper"
```

---

## Task 8: Wire completion state into the window + entry point

**Files:**
- Modify: `meister_guide/overlay/window.py` (`__init__` around line 79-80; `_refresh_guides_status` 732-739; `_on_ingest_progress` 548-566)
- Modify: `meister_guide/main.py:14,46-70`

This task is Qt wiring (not unit-tested); verification is the full suite staying green plus a manual launch in Task 9.

- [ ] **Step 1: Accept state repos in the window constructor**

In `meister_guide/overlay/window.py`, add the import near the other `meister_guide` imports:

```python
from meister_guide.guides_status import guides_status_text
```

In `OverlayWindow.__init__`, where `self._articles_repo` / `self._db_path` are set (lines 79-80), accept and store two new optional keyword args. Add to the `__init__` signature `scrape_state_repo=None, redirect_state_repo=None`, and store:

```python
        self._articles_repo = articles_repo
        self._db_path = db_path
        self._scrape_state_repo = scrape_state_repo
        self._redirect_state_repo = redirect_state_repo
```

- [ ] **Step 2: Drive `_refresh_guides_status` from the helper**

Replace `_refresh_guides_status` (lines 732-739) with:

```python
    def _refresh_guides_status(self):
        if self._articles_repo is None:
            self.guides_status.setText("")
            return
        n = self._articles_repo.count()
        articles_done = True
        redirects_done = True
        if self._scrape_state_repo is not None:
            articles_done = (self._scrape_state_repo.load().continue_token is None
                             and n > 0)
        if self._redirect_state_repo is not None:
            rs = self._redirect_state_repo.load()
            redirects_done = rs.continue_token is None and rs.done > 0
        self.guides_status.setText(
            guides_status_text(n, articles_done, redirects_done)
        )
```

- [ ] **Step 3: Make running progress phase-honest**

In `_on_ingest_progress` (the version already carrying `effective_total`), change only the `else` (total unknown / redirect-linking phase) branch text so it never reads like a bare final count — replace `self.guides_status.setText(f"{done:,}")` with:

```python
            self.guides_status.setText(f"Linking related topics… ({done:,})")
```

Leave the `effective_total` computation, the `0..effective_total` bar, the "Catching up…" branch, and the `f"{done:,}/{effective_total:,}"` branch unchanged.

- [ ] **Step 4: Build and pass the state repos in `main.py`**

In `meister_guide/main.py`, update the articles import (line 14) and add the redirect-state import:

```python
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.db.redirects import RedirectStateRepo
```

After `articles_repo = ArticlesRepo(conn)` (line 51) add:

```python
    scrape_state_repo = ScrapeStateRepo(conn)
    redirect_state_repo = RedirectStateRepo(conn)
```

Add the two kwargs to the `OverlayWindow(...)` call (lines 64-70):

```python
    overlay = OverlayWindow(settings, games_repo.list_games(),
                            articles_repo=articles_repo,
                            db_path=default_db_path(),
                            chat_repo=chat_repo,
                            ollama_client=ollama_client,
                            settings_repo=settings_repo,
                            scrape_state_repo=scrape_state_repo,
                            redirect_state_repo=redirect_state_repo,
                            hotkey=hotkey)
```

- [ ] **Step 5: Run the full suite (regression)**

Run: `py -m pytest -q`
Expected: PASS — all prior tests plus the new ones (well above the 159 baseline).

- [ ] **Step 6: Commit**

```bash
git add meister_guide/overlay/window.py meister_guide/main.py
git commit -m "feat: honest guide completion state in Guides tab"
```

---

## Task 9: Regression + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Full automated suite**

Run: `py -m pytest -q`
Expected: PASS, zero failures.

- [ ] **Step 2: Manual launch — completion state**

Run: `py -m meister_guide.main` (or the project's normal launch). Open the Guides tab.
Expected: status reads `Incomplete — 17,916 downloaded · click Update to resume` (because the live DB still holds a resume token), NOT a bare `17,916 articles`.

- [ ] **Step 3: Manual — resume + overshoot gone (optional, network + time)**

Click **Update guides**. Expected: the progress bar fills toward the estimate and, once `done` passes it, the bar pins near 100% with text like `18,200/18,200` — never an inverted `17,915/16,693`. Let it run; when the article walk finishes it shows `Linking related topics… (N)`, then on completion the idle status reads `Complete · N articles`. (Full download is large; this step confirms behavior, not necessarily completion in one sitting.)

- [ ] **Step 4: Manual — original failing question (after a substantial download past "S")**

In chat, ask "when do spiders spawn with potion effects". Expected (once the Spider article has been downloaded): the answer references Hard difficulty / random status effect, sourced from the Spider article.

- [ ] **Step 5: Final state**

No commit needed (Task 8 was the last code commit). Branch `retrieval-accuracy` now contains the spec commit plus Tasks 1-8. Ready for review/merge per the finishing-a-development-branch skill.

---

## Self-review

**Spec coverage:**
- RC-0 (corpus completeness + honest state) → Tasks 7, 8 (helper + wiring), plus the `effective_total` progress fix folded in (Task 8, Step 3) and verified in Task 9.
- RC-A (passage windowing) → Tasks 2, 3, 4 (`best_window`, `window_bounds`, `relevant_passage` width 2000).
- RC-B (ranking specific>generic) → Tasks 5, 6 (`rerank` coverage + `search_ranked` wiring).
- De-inflection vocabulary match ("effects"→"effect") → Task 1 shared `deinflect`, used by `best_window`.
- Acceptance (spider question answerable) → Task 9, Steps 2-4.

**Placeholder scan:** none — every code step shows complete code; no TBD/TODO.

**Type/name consistency:** `deinflect` (Task 1) used by `best_window` (Task 2), `window_bounds` (Task 3), `_terms_to_or_query` (Task 1). `best_window` returns `(start, end, distinct_count)` and is consumed consistently by `window_bounds` (drops count), `relevant_passage` (drops count), and `search_ranked` (uses count → `coverage`). `rerank(candidates, terms, limit, coverage=None)` matches its call in `search_ranked`. `guides_status_text(article_count, articles_done, redirects_done)` matches its call in `_refresh_guides_status`. `SearchHit.pageid` is the coverage key in both `search_ranked` and `rerank`.
