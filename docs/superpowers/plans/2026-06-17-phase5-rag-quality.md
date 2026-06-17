# Phase 5: Better Answers (retrieval-first RAG quality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Meister's chat retrieve the *correct* wiki article for a question (not version changelogs / disambiguation pages) and generate the answer with the strongest installed local model.

**Architecture:** Keep SQLite FTS5. Add three small pure modules — query cleaning, noise/title-boost scoring, and a re-ranker — then a chat-only `search_ranked` on `ArticlesRepo` that pulls a candidate pool from FTS and re-ranks it. Auto-pick the largest completion-capable Ollama model. Tighten the system prompt. The Guides-tab search, the chat UI/threading, and the guide database are untouched.

**Tech Stack:** Python 3.12, PySide6, SQLite FTS5 (bm25), Ollama. Tests run headless with `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest`.

---

## File Structure

- Create: `meister_guide/ai/query.py` — `clean_query(text) -> list[str]` (pure).
- Create: `meister_guide/ai/ranking.py` — `noise_penalty`, `title_boost`, `rerank` (pure).
- Modify: `meister_guide/db/articles.py` — add `search_ranked(...)`; `search()` unchanged.
- Modify: `meister_guide/ai/ollama_client.py` — add `list_model_info()` + `pick_best_model(models)`.
- Modify: `meister_guide/ai/prompt.py` — tighten `SYSTEM_PREAMBLE`.
- Modify: `meister_guide/overlay/window.py` — `_on_send` uses `search_ranked`; `_detect_ollama` uses `pick_best_model(list_model_info())`.
- Tests: `tests/test_query.py`, `tests/test_ranking.py`, `tests/test_articles_repo.py` (add), `tests/test_ollama_client.py` (add), `tests/test_prompt.py` (add), `tests/test_window_chat.py` (adjust).

**Import direction:** `db/articles.py` imports from `ai/query.py` and `ai/ranking.py`. Those `ai` modules are pure and import nothing from `db`, so there is no cycle.

---

## Task 1: Query cleaning (`ai/query.py`)

**Files:**
- Create: `meister_guide/ai/query.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_query.py
from meister_guide.ai.query import clean_query


def test_strips_question_and_stop_words():
    assert clean_query("how do I make a nether portal?") == ["nether", "portal"]


def test_lowercases_and_drops_punctuation():
    assert clean_query("How do CREEPERS work??!") == ["creepers"]


def test_dedupes_preserving_order():
    assert clean_query("iron iron golem golem") == ["iron", "golem"]


def test_drops_one_char_tokens():
    assert clean_query("a b diamond") == ["diamond"]


def test_falls_back_to_raw_tokens_when_all_stopwords():
    # every token is a stop/short word -> don't return empty
    assert clean_query("how do you do") == ["how", "do", "you"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_query.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.ai.query'`

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/ai/query.py
"""Turn a free-text chat question into the content terms worth searching for,
so the FTS index isn't polluted by question/stop words ('how do I make a …')."""
import re

# Curated question + stop words. Small on purpose: only words that never help
# locate a Minecraft topic. Real nouns/verbs of interest are kept.
_STOP = {
    "how", "do", "does", "did", "done", "doing", "i", "you", "we", "they",
    "to", "a", "an", "the", "make", "makes", "made", "making", "work", "works",
    "working", "get", "gets", "getting", "is", "are", "was", "were", "be",
    "of", "in", "on", "for", "with", "and", "or", "what", "whats", "why",
    "when", "where", "who", "which", "can", "could", "should", "would", "will",
    "my", "me", "it", "this", "that", "best", "way", "ways", "use", "using",
    "need", "want", "about", "as", "at", "by", "from", "into",
}


def clean_query(text):
    """Return content terms: lowercased, no punctuation, no stop/short words,
    de-duplicated in order. Never returns empty — if cleaning removes
    everything, falls back to the de-duplicated raw tokens."""
    tokens = re.findall(r"\w+", (text or "").lower())

    def dedupe(words):
        seen, out = set(), []
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out

    terms = dedupe(t for t in tokens if len(t) >= 2 and t not in _STOP)
    return terms or dedupe(tokens)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_query.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/query.py tests/test_query.py
git commit -m "feat: clean chat queries down to content terms for retrieval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Noise penalty (`ai/ranking.py`)

**Files:**
- Create: `meister_guide/ai/ranking.py`
- Test: `tests/test_ranking.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking.py
from meister_guide.ai.ranking import noise_penalty


def test_real_article_titles_score_zero():
    for title in ["Creeper", "Nether", "Crafting Table", "Elytra", "Redstone"]:
        assert noise_penalty(title) == 0.0


def test_disambiguation_is_penalised_hardest():
    assert noise_penalty("Creeper (disambiguation)") > noise_penalty("Bedrock Edition 1.16.0")


def test_version_and_changelog_pages_penalised():
    assert noise_penalty("Bedrock Edition 1.16.0") > 0
    assert noise_penalty("Bedrock Edition beta 1.16.0.57") > 0
    assert noise_penalty("Java Edition 1.20") > 0
    assert noise_penalty("Bedrock Edition 1.2.0/Development versions") > 0


def test_history_and_movie_pages_penalised():
    assert noise_penalty("Bedrock Edition mob render history") > 0
    assert noise_penalty("A Minecraft Movie") > 0
    assert noise_penalty("A Minecraft Movie Live Event") > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meister_guide.ai.ranking'`

- [ ] **Step 3: Write minimal implementation**

```python
# meister_guide/ai/ranking.py
"""Re-rank FTS5 candidates so the canonical topic article wins over noise
(version changelogs, disambiguation pages, history subpages, movie/event
pages). Pure functions — no DB, no I/O."""
import re

_DISAMBIG_PENALTY = 100000.0   # sink below everything real
_NOISE_PENALTY = 5000.0        # version/history/movie pages

_VERSION_PREFIX = re.compile(r"^(java|bedrock|legacy console|pocket) edition\b")
_VERSION_NUMBER = re.compile(r"\d+\.\d+")


def noise_penalty(title):
    """Non-negative penalty: higher = less useful as an answer source."""
    low = title.lower()
    if low.endswith("(disambiguation)"):
        return _DISAMBIG_PENALTY
    if _VERSION_PREFIX.match(low) and _VERSION_NUMBER.search(low):
        return _NOISE_PENALTY
    if "development versions" in low:
        return _NOISE_PENALTY
    if " history" in low:               # leading space avoids "History of …"
        return _NOISE_PENALTY
    if "a minecraft movie" in low or "live event" in low:
        return _NOISE_PENALTY
    return 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ranking.py tests/test_ranking.py
git commit -m "feat: noise_penalty to down-rank changelog/disambiguation pages

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Title-match boost (`ai/ranking.py`)

**Files:**
- Modify: `meister_guide/ai/ranking.py`
- Test: `tests/test_ranking.py` (add)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking.py  (append)
from meister_guide.ai.ranking import title_boost


def test_exact_title_match_beats_partial_beats_none():
    exact = title_boost("Creeper", ["creeper"])
    partial = title_boost("Creeper Head", ["creeper"])
    none = title_boost("Wither", ["creeper"])
    assert exact > partial > none == 0.0


def test_all_terms_present_scores_high():
    assert title_boost("Nether Portal", ["nether", "portal"]) > \
        title_boost("Broken Nether Portal", ["nether", "portal"])


def test_no_terms_scores_zero():
    assert title_boost("Creeper", []) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -k title_boost -v`
Expected: FAIL with `ImportError: cannot import name 'title_boost'`

- [ ] **Step 3: Write minimal implementation**

Add to `meister_guide/ai/ranking.py`:

```python
def title_boost(title, terms):
    """Boost from overlap between cleaned query `terms` and the title's words.
    Exact set match scores highest, then 'all terms present', then partial."""
    if not terms:
        return 0.0
    title_words = set(re.findall(r"\w+", title.lower()))
    matched = sum(1 for t in terms if t in title_words)
    if matched == 0:
        return 0.0
    boost = 1000.0 * (matched / len(terms))   # full coverage -> 1000
    if title_words == set(terms):              # title IS exactly the query
        boost += 1000.0
    return boost
```

Note: "Nether Portal" with terms `["nether","portal"]` → title_words `{"nether","portal"}` == set(terms) → 1000 + 1000 = 2000. "Broken Nether Portal" → title_words has an extra word, matched 2/2 → 1000, not exact → 1000. So 2000 > 1000 as asserted.

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -v`
Expected: PASS (all ranking tests)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ranking.py tests/test_ranking.py
git commit -m "feat: title_boost to surface the canonical topic article

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Re-ranker (`ai/ranking.py`)

**Files:**
- Modify: `meister_guide/ai/ranking.py`
- Test: `tests/test_ranking.py` (add)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking.py  (append)
from collections import namedtuple
from meister_guide.ai.ranking import rerank

Hit = namedtuple("Hit", "pageid title excerpt_html url")


def _hit(title):
    return Hit(1, title, "", None)


def test_rerank_surfaces_creeper_over_noise():
    # (bm25 rank, hit). More-negative rank = better keyword score in FTS5.
    # The changelogs even have *better* bm25 here, but must still lose.
    candidates = [
        (-9.0, _hit("Bedrock Edition beta 1.16.0.57")),
        (-8.5, _hit("Creeper (disambiguation)")),
        (-3.0, _hit("Creeper")),
        (-2.0, _hit("Creeper Head")),
    ]
    ranked = rerank(candidates, ["creeper"], limit=3)
    assert ranked[0].title == "Creeper"
    assert "(disambiguation)" not in ranked[0].title
    assert all("Edition" not in h.title for h in ranked[:1])


def test_rerank_respects_limit():
    candidates = [(-1.0, _hit(f"Article {i}")) for i in range(10)]
    assert len(rerank(candidates, ["article"], limit=3)) == 3


def test_rerank_empty_returns_empty():
    assert rerank([], ["creeper"], limit=3) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -k rerank -v`
Expected: FAIL with `ImportError: cannot import name 'rerank'`

- [ ] **Step 3: Write minimal implementation**

Add to `meister_guide/ai/ranking.py`:

```python
def rerank(candidates, terms, limit=3):
    """`candidates`: list of (bm25_rank, hit). bm25_rank is the SQLite FTS5
    `rank` value (more-negative = better keyword match). Returns the best
    `limit` hits, highest combined score first.

    score = title_boost − noise_penalty + (−bm25_rank)
    Title boost and noise penalty are on a far larger scale than the bm25 term,
    so a strong title match or a noise page decides the order; bm25 only breaks
    ties within the same boost/noise tier."""
    scored = []
    for rank, hit in candidates:
        score = title_boost(hit.title, terms) - noise_penalty(hit.title) + (-rank)
        scored.append((score, hit))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [hit for _, hit in scored[:limit]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ranking.py -v`
Expected: PASS (all ranking tests)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ranking.py tests/test_ranking.py
git commit -m "feat: rerank FTS candidates by title-boost minus noise

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Chat retrieval path (`ArticlesRepo.search_ranked`)

**Files:**
- Modify: `meister_guide/db/articles.py`
- Test: `tests/test_articles_repo.py` (add)

Context: `SearchHit(pageid, title, excerpt_html, url)`. Existing `search(query, limit=50)` builds `_to_fts_query(query)` and `ORDER BY rank`. The schema stores `articles(id, pageid, title, body_zlib, url, …)` and a contentless `articles_fts` whose `rowid` == `articles.id`. `make_excerpt` and `zlib` are already imported in `articles.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_articles_repo.py  (append)
def test_search_ranked_surfaces_canonical_article_over_noise(tmp_path):
    from meister_guide.db.database import connect, init_db
    from meister_guide.db.articles import ArticlesRepo
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    repo = ArticlesRepo(conn)
    # canonical article + decoys that mention "creeper" a lot
    repo.add_article(1, "Creeper",
                     "A creeper is a hostile mob that creeps up and explodes. "
                     "Creeper creeper creeper.", 1, "u1")
    repo.add_article(2, "Creeper (disambiguation)",
                     "Creeper may refer to: creeper, creeper, creeper.", 1, "u2")
    repo.add_article(3, "Bedrock Edition beta 1.16.0.57",
                     "Changelog. Creeper creeper creeper creeper creeper.", 1, "u3")

    hits = repo.search_ranked("how do creepers work?", limit=3)
    assert hits, "expected at least one hit"
    assert hits[0].title == "Creeper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_articles_repo.py -k search_ranked -v`
Expected: FAIL with `AttributeError: 'ArticlesRepo' object has no attribute 'search_ranked'`

- [ ] **Step 3: Write minimal implementation**

At the top of `meister_guide/db/articles.py`, add imports near the other imports:

```python
from meister_guide.ai.query import clean_query
from meister_guide.ai.ranking import rerank
```

Add this method to `ArticlesRepo` (right after `search`):

```python
def search_ranked(self, raw_query, limit=3, candidate_pool=15):
    """Chat retrieval: clean the query to content terms, pull a pool of FTS
    candidates with their bm25 rank, then re-rank so the canonical article
    wins over changelog/disambiguation noise. Returns up to `limit` SearchHits.
    The Guides-tab `search()` is intentionally separate and unchanged."""
    terms = clean_query(raw_query)
    fts_query = self._to_fts_query(" ".join(terms))
    if not fts_query:
        return []
    rows = self._conn.execute(
        "SELECT rowid, rank FROM articles_fts WHERE articles_fts MATCH ? "
        "ORDER BY rank LIMIT ?",
        (fts_query, candidate_pool),
    ).fetchall()
    candidates = []
    for rowid, rank in rows:
        row = self._conn.execute(
            "SELECT pageid, title, body_zlib, url FROM articles WHERE id = ?",
            (rowid,),
        ).fetchone()
        if row is None:
            continue
        body = zlib.decompress(row[2]).decode("utf-8")
        hit = SearchHit(row[0], row[1], make_excerpt(body, raw_query), row[3])
        candidates.append((rank, hit))
    return rerank(candidates, terms, limit)
```

- [ ] **Step 4: Run the test (and the whole suite) to verify**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_articles_repo.py -v`
Expected: PASS (existing repo tests + the new one). The new method must not change `search()` behaviour, so the existing Guides-tab tests stay green.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/db/articles.py tests/test_articles_repo.py
git commit -m "feat: ArticlesRepo.search_ranked for chat retrieval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Strongest-model auto-pick (`ollama_client.py`)

**Files:**
- Modify: `meister_guide/ai/ollama_client.py`
- Test: `tests/test_ollama_client.py` (add)

Context: existing `list_models()` returns `[m["name"] …]` from `/api/tags`; `pick_model(names)` prefers `llama3*` then first. `/api/tags` entries look like `{"name": "qwen2.5:32b", "capabilities": ["completion","tools"], "details": {"parameter_size": "32.8B", …}}`. Vision models have `"capabilities": ["vision","completion"]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ollama_client.py  (append)
from meister_guide.ai.ollama_client import pick_best_model


def _m(name, size=None, caps=None):
    d = {"name": name, "details": {}}
    if size is not None:
        d["details"]["parameter_size"] = size
    if caps is not None:
        d["capabilities"] = caps
    return d


def test_pick_best_model_prefers_largest_completion_model():
    models = [
        _m("llama3:latest", "8.0B", ["completion"]),
        _m("qwen2.5:32b", "32.8B", ["completion", "tools"]),
        _m("llama3.2:latest", "3.2B", ["completion", "tools"]),
    ]
    assert pick_best_model(models) == "qwen2.5:32b"


def test_pick_best_model_skips_embedding_only():
    models = [
        _m("nomic-embed-text", "0.1B", ["embedding"]),
        _m("llama3:latest", "8.0B", ["completion"]),
    ]
    assert pick_best_model(models) == "llama3:latest"


def test_pick_best_model_falls_back_to_name_pref_without_sizes():
    models = [_m("mistral"), _m("llama3:latest")]  # no parameter_size
    assert pick_best_model(models) == "llama3:latest"   # llama3 preference


def test_pick_best_model_none_when_empty():
    assert pick_best_model([]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ollama_client.py -k pick_best_model -v`
Expected: FAIL with `ImportError: cannot import name 'pick_best_model'`

- [ ] **Step 3: Write minimal implementation**

Add to `meister_guide/ai/ollama_client.py` (after `pick_model`). Add `import re` at the top if not present:

```python
def _parse_size(text):
    """'32.8B' -> 32.8, '8.0B' -> 8.0, '7B' -> 7.0, missing -> 0.0.
    Unit suffix is ignored — all Ollama sizes are in billions of params."""
    if not text:
        return 0.0
    m = re.match(r"([\d.]+)", str(text).strip())
    return float(m.group(1)) if m else 0.0


def pick_best_model(models):
    """`models`: raw /api/tags entries. Pick the largest completion-capable
    text model (so qwen2.5:32b beats llama3). Skip embedding-only / non-
    completion models. If no size info is available, fall back to the
    name-preference in pick_model."""
    eligible = []
    for m in models:
        name = m.get("name")
        if not name:
            continue
        caps = m.get("capabilities") or []
        if caps and "completion" not in caps:
            continue
        size = _parse_size((m.get("details") or {}).get("parameter_size"))
        eligible.append((size, name))
    if not eligible:
        return None
    if all(size == 0.0 for size, _ in eligible):
        return pick_model([name for _, name in eligible])
    eligible.sort(key=lambda pair: pair[0], reverse=True)
    return eligible[0][1]
```

Also add the raw-info accessor (used by the UI in Task 8):

```python
    def list_model_info(self):
        """Raw /api/tags model entries (name + details + capabilities)."""
        data = self._http_get(self._base + "/api/tags")
        return data.get("models", [])
```

(Place `list_model_info` as a method inside `OllamaClient`, next to `list_models`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_ollama_client.py -v`
Expected: PASS (all ollama tests, old + 4 new)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: pick_best_model auto-selects strongest local model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Tighten the system prompt (`prompt.py`)

**Files:**
- Modify: `meister_guide/ai/prompt.py`
- Test: `tests/test_prompt.py` (add)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt.py  (append)
from meister_guide.ai.prompt import SYSTEM_PREAMBLE


def test_preamble_instructs_grounding_and_steps():
    low = SYSTEM_PREAMBLE.lower()
    assert "meister" in low
    assert "excerpt" in low          # must lean on the supplied guide excerpts
    assert "step" in low             # numbered steps for how-to questions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_prompt.py -k preamble -v`
Expected: FAIL on the `"step"` assertion (current preamble has no "step").

- [ ] **Step 3: Write minimal implementation**

Replace `SYSTEM_PREAMBLE` in `meister_guide/ai/prompt.py` with:

```python
SYSTEM_PREAMBLE = (
    "You are Meister, a friendly in-game Minecraft assistant. Answer the "
    "player's question using the guide excerpts below as your source of truth. "
    "When the question is about how to do or craft something, give clear "
    "numbered steps. Be concise and specific — use the exact block, item, and "
    "amount names from the excerpts. If the excerpts do not contain the answer, "
    "say so plainly instead of guessing."
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_prompt.py -v`
Expected: PASS (existing structure tests + new preamble test). The word "excerpts" appears in the preamble now, but the existing `test_build_messages_without_passages_has_no_excerpt_block` asserts the capitalised phrase `"Guide excerpts"` (the block header) is absent — the lowercase "excerpts" in the preamble does not match `"Guide excerpts"`, so that test stays green. Confirm it passes.

- [ ] **Step 5: Commit**

```bash
git add meister_guide/ai/prompt.py tests/test_prompt.py
git commit -m "feat: tighten system prompt for grounded, step-by-step answers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Wire the chat tab to the new retrieval + model pick (`window.py`)

**Files:**
- Modify: `meister_guide/overlay/window.py` (import line 14; `_on_send` ~line 241; `_detect_ollama` ~line 184–189)
- Test: `tests/test_window_chat.py` (adjust the stub client)

- [ ] **Step 1: Update the window-chat test stub and add a retrieval assertion**

In `tests/test_window_chat.py`, replace the `OkClient` class so it exposes `list_model_info` (the UI will now call that):

```python
class OkClient:
    def list_models(self):
        return ["llama3"]

    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]

    def chat(self, model, messages):
        return iter(())   # stream nothing so the worker finishes immediately
```

Add a test that `_on_send` routes through `search_ranked` (use a recording repo stub):

```python
def test_send_uses_ranked_retrieval(tmp_path, monkeypatch):
    w, chat = _window(tmp_path)
    calls = {}
    real = w._articles_repo.search_ranked
    def spy(q, limit=3):
        calls["q"] = q
        return real(q, limit=limit)
    monkeypatch.setattr(w._articles_repo, "search_ranked", spy)
    w.chat_input.setText("how do creepers work?")
    w._on_send()
    assert calls.get("q") == "how do creepers work?"
    w._teardown_chat_thread()   # stop the worker thread started by _on_send
```

- [ ] **Step 2: Run the window-chat tests to verify the new test fails**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest tests/test_window_chat.py -v`
Expected: FAIL — `_on_send` still calls `search`, so `search_ranked` spy isn't hit (`calls.get("q")` is `None`); and/or `_detect_ollama` `AttributeError` once we change it. (If it errors instead of asserting, that's still a failing test — proceed to implement.)

- [ ] **Step 3: Update the imports and the two call sites**

In `meister_guide/overlay/window.py` line 14, add `pick_best_model`:

```python
from meister_guide.ai.ollama_client import OllamaUnavailable, pick_model, pick_best_model
```

In `_detect_ollama`, replace the model-detection lines:

```python
        try:
            models = self._ollama.list_model_info()
        except OllamaUnavailable:
            self._set_chat_enabled(False,
                "Meister needs Ollama running at localhost:11434.")
            return
        self._model = pick_best_model(models)
```

(Keep the rest of `_detect_ollama` — the `if self._model is None` branch and the no-guides note — exactly as-is.)

In `_on_send`, change the retrieval call:

```python
            for hit in self._articles_repo.search_ranked(question, limit=3):
```

(Replaces `self._articles_repo.search(question, limit=3)`. The rest of the loop — `get_article`, `relevant_passage`, building `sources`/`passages` — is unchanged.)

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest -q`
Expected: PASS — all prior tests plus the new query/ranking/repo/ollama/prompt/window tests. (`pick_model` is still imported because the fallback in `pick_best_model` is internal; the window no longer calls `pick_model` directly, so if a linter flags the unused import, drop `pick_model` from the line. Verify by running the suite either way.)

- [ ] **Step 5: Commit**

```bash
git add meister_guide/overlay/window.py tests/test_window_chat.py
git commit -m "feat: chat tab uses ranked retrieval + strongest-model pick

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] Run the whole suite: `QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -3 -m pytest -q` — expect all green.
- [ ] Live trace against the real DB (manual, optional): run the retrieval trace from the spec's evidence and confirm "how do creepers work?" now returns the *Creeper* article first and no Bedrock changelogs in the top 3.
- [ ] Dispatch the final whole-implementation review (subagent-driven-development), then `superpowers:finishing-a-development-branch` to merge `phase-5-rag-quality` → `master`.
- [ ] Post-phase deliverables (user request): write the Phase 5 devlog (`devlogs/005-*.md`) and a standalone whole-project Stardance description.

## Out of scope (deferred — do NOT implement here)
- Redirect ingestion (needs a scraper change + re-walk of ~17k articles).
- Embeddings / vector search / hybrid re-rank.
- Model-picker UI, temperature/params, Claude API backend (Settings phase).
