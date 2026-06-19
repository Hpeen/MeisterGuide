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
    """Return (start, end) of a `width`-char window centred on the earliest
    query-term match, or the leading window when nothing matches."""
    terms = [t for t in _WORD.findall(query.lower()) if t]
    lowered = body.lower()
    first = -1
    for term in terms:
        idx = lowered.find(term)
        if idx != -1 and (first == -1 or idx < first):
            first = idx
    if first == -1:
        return 0, min(len(body), width)
    start = max(0, first - width // 3)
    end = min(len(body), start + width)
    return start, end


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
