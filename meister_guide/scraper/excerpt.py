"""Build a short, HTML-escaped, query-highlighted excerpt from article text.

Contentless FTS5 has no snippet() (it stores no text), so we generate excerpts
ourselves from the decompressed body."""
import html
import re

_WORD = re.compile(r"\w+", re.UNICODE)


def deinflect(word: str) -> str:
    """Crude English de-inflection: strip a trailing 'es'/'s' so a plural query
    term lines up with a singular body/title form. Shared by ranking, the OR
    recall query, and the cluster-window finder so they all agree."""
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def window_bounds(body: str, query: str, width: int) -> tuple:
    """Return (start, end) of a `width`-char window over the densest cluster of
    query terms (or the leading window when nothing matches). Thin wrapper over
    best_window so excerpt highlighting and RAG passage selection share placement."""
    terms = _WORD.findall(query.lower())
    start, end, _ = best_window(body, terms, width)
    return start, end


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


def make_excerpt(body: str, query: str, width: int = 240) -> str:
    terms = [t for t in _WORD.findall(query.lower()) if t]
    start, end = window_bounds(body, query, width)
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""

    escaped = html.escape(snippet)
    unique_terms = sorted(set(terms), key=len, reverse=True)
    if unique_terms:
        pattern = "|".join(re.escape(html.escape(t)) for t in unique_terms)
        escaped = re.sub("(" + pattern + ")", r"<b>\1</b>", escaped,
                         flags=re.IGNORECASE)
    return f"{prefix}{escaped}{suffix}"
