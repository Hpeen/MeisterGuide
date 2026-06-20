"""Per-game category seed: enumerate a wiki category one level deep, fetch each
page's full extract, and ingest it scoped to the game. Pure (no Qt) so it stays
unit-testable; CategorySeedWorker wraps it for threading. Bounded by `cap` and
idempotent (add_article dedupes by pageid), so a re-run after an interruption
just skips already-stored pages."""
from meister_guide.ai.ranking import is_noise
from meister_guide.scraper.urls import page_url


def run_category_seed(client, articles_repo, game_id, category, base="",
                      cap=500, progress_cb=None, should_cancel=None):
    """Walk `category` (one level) -> for each title fetch its full extract ->
    skip noise -> add_article scoped to game_id. Returns the number of articles
    newly ingested. Titles are deduped and truncated to `cap`. should_cancel()
    is polled before each page so a quit/hide aborts promptly. progress_cb(done,
    total) is called once with (0, total) then once per title (including skipped
    noise titles) so the bar advances uniformly."""
    seen, titles = set(), []
    for title in client.iter_category_members(category):
        if title not in seen:
            seen.add(title)
            titles.append(title)
    titles = titles[:cap]
    total = len(titles)
    if progress_cb:
        progress_cb(0, total)
    n = 0
    for i, title in enumerate(titles, start=1):
        if should_cancel and should_cancel():
            break
        if is_noise(title):
            if progress_cb:
                progress_cb(i, total)
            continue
        for art in client.fetch_by_titles([title]):
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, page_url(base, art.title),
                                         game_id=game_id):
                n += 1
        if progress_cb:
            progress_cb(i, total)
    return n
