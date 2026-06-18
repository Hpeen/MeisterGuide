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


def _deinflect(word):
    """Crude English de-inflection (strip trailing 'es'/'s'), matching the rule
    used by the retrieval recall pass so title scoring and recall agree: a plural
    query term ('creepers') must match the singular title word ('Creeper')."""
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def title_boost(title, terms):
    """Boost from overlap between cleaned query `terms` and the title's words.
    Exact set match scores highest, then 'all terms present', then partial.
    Both sides are de-inflected so plural/singular forms still line up."""
    if not terms:
        return 0.0
    title_words = {_deinflect(w) for w in re.findall(r"\w+", title.lower())}
    norm_terms = [_deinflect(t) for t in terms]
    matched = sum(1 for t in norm_terms if t in title_words)
    if matched == 0:
        return 0.0
    boost = 1000.0 * (matched / len(norm_terms))   # full coverage -> 1000
    if title_words == set(norm_terms):             # title IS exactly the query
        boost += 1000.0
    return boost


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
