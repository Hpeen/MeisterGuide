"""On-demand wiki fetch: on a chat retrieval miss, search the active game's wiki,
fetch the top pages, and ingest them scoped to the game so they're offline next
time. Pure (no Qt) so it stays unit-testable; OnDemandFetchWorker wraps it for
threading."""
from meister_guide.ai.ranking import is_noise


def _page_url(base, title):
    """Best-effort display URL for a fetched page. Stored url is display-only."""
    return (base or "").rstrip("/") + "/wiki/" + title.replace(" ", "_")


def run_on_demand_fetch(client, articles_repo, game_id, query, limit=3, base="",
                        should_cancel=None):
    """Search -> fetch top `limit` titles -> skip noise -> add_article scoped to
    game_id. Returns the number of articles newly ingested. Idempotent: pages
    already stored are skipped (add_article dedupes by pageid), so a re-run after
    the same miss is a no-op. should_cancel() is polled between the two blocking
    network calls so a quit/hide can abort promptly."""
    titles = client.search_titles(query, limit)
    if should_cancel and should_cancel():
        return 0
    arts = client.fetch_by_titles(titles[:limit]) if titles else []
    n = 0
    for a in arts:
        if should_cancel and should_cancel():
            break
        if is_noise(a.title):
            continue
        if articles_repo.add_article(a.pageid, a.title, a.text, a.revid,
                                     _page_url(base, a.title), game_id=game_id):
            n += 1
    return n
