"""Plain-text relevance window for RAG context (model input).

Sibling of scraper.excerpt.make_excerpt, but returns plain text (no HTML
escaping or <b> highlighting) since it feeds the model, not a QLabel."""
from meister_guide.scraper.excerpt import window_bounds


def relevant_passage(body: str, query: str, width: int = 1500) -> str:
    start, end = window_bounds(body, query, width)
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet}{suffix}"
