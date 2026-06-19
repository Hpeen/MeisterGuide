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
