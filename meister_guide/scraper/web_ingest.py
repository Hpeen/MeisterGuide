"""Web-search fallback: search the web, scrape the top results, and ingest them
scoped to the game so they answer through the normal RAG path. Pure (no Qt) so
it stays unit-testable; WebFetchWorker wraps it for threading. Idempotent: pages
are keyed by a synthetic URL-hash pageid, so a re-run skips already-stored pages."""
from meister_guide.scraper.urls import web_pageid


def run_web_fetch(search_client, fetch_fn, articles_repo, game_id, query,
                  limit=3, min_chars=200, should_cancel=None):
    """search -> per-URL fetch+extract -> skip too-short pages -> add_article
    scoped to game_id (url stored as the real result URL, revid None). Returns
    the number newly ingested. should_cancel() is polled before the search result
    is consumed and before each page fetch so a quit/hide aborts promptly."""
    results = search_client.search(query, limit)
    if should_cancel and should_cancel():
        return 0
    n = 0
    for title, url in results[:limit]:
        if should_cancel and should_cancel():
            break
        page_title, text = fetch_fn(url)
        if len((text or "").strip()) < min_chars:
            continue
        if articles_repo.add_article(web_pageid(url), page_title or title or url,
                                     text, None, url, game_id=game_id):
            n += 1
    return n
