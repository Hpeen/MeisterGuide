"""Re-rank FTS5 candidates so the canonical topic article wins over noise
(version changelogs, disambiguation pages, history subpages, movie/event
pages). Pure functions — no DB, no I/O."""
import re

from meister_guide.scraper.excerpt import deinflect as _deinflect

_DISAMBIG_PENALTY = 100000.0   # sink below everything real
_NOISE_PENALTY = 5000.0        # version/history/movie pages
_COVERAGE_WEIGHT = 800.0       # full distinct-term coverage ~= a partial title match

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


def is_noise(title) -> bool:
    """True for pages the ranker already sinks (versioned edition/changelog
    pages, development-version & history subpages, movie/event, disambiguation).
    Single source of truth reused to skip these at ingest and prune them from an
    existing corpus — they never make useful answer sources and bloat the
    download (the wiki has thousands of per-version pages)."""
    return noise_penalty(title) > 0.0


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
