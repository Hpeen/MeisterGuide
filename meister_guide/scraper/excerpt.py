"""Build a short, HTML-escaped, query-highlighted excerpt from article text.

Contentless FTS5 has no snippet() (it stores no text), so we generate excerpts
ourselves from the decompressed body."""
import html
import re

_WORD = re.compile(r"\w+", re.UNICODE)


def make_excerpt(body: str, query: str, width: int = 240) -> str:
    terms = [t for t in _WORD.findall(query.lower()) if t]
    lowered = body.lower()

    first = -1
    for term in terms:
        idx = lowered.find(term)
        if idx != -1 and (first == -1 or idx < first):
            first = idx

    if first == -1:
        start, end = 0, min(len(body), width)
    else:
        start = max(0, first - width // 3)
        end = min(len(body), start + width)

    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""

    escaped = html.escape(snippet)
    for term in sorted(set(terms), key=len, reverse=True):
        escaped = re.sub(
            "(" + re.escape(html.escape(term)) + ")",
            r"<b>\1</b>",
            escaped,
            flags=re.IGNORECASE,
        )
    return f"{prefix}{escaped}{suffix}"
