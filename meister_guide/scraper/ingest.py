"""Drive the WikiClient into the DB: per-batch transactions, resume token, and
progress/cancel hooks. No Qt here so it stays unit-testable."""
from meister_guide.db.articles import ScrapeState  # re-export for callers
from meister_guide.scraper.wiki_client import InvalidContinueError


def _url_for(title: str) -> str:
    return "https://minecraft.wiki/w/" + title.replace(" ", "_")


def run_ingest(client, articles_repo, state_repo, conn,
               progress_cb=None, should_cancel=None):
    """Ingest all article batches from `client` into the repos.

    Resumes from the saved continue token, commits once per batch (so a crash
    loses at most one batch), and stops cleanly if should_cancel() turns true.

    If the saved resume token is rejected as stale/invalid (e.g. it predates a
    query-parameter change, or expired), restart enumeration from the beginning
    once — add_article is idempotent, so already-stored articles are skipped."""
    total = state_repo.load().total
    if total is None:
        try:
            total = client.article_count()
        except Exception:
            total = None

    try:
        _ingest_from(state_repo.load().continue_token, state_repo.load().done,
                     client, articles_repo, state_repo, conn, total,
                     progress_cb, should_cancel)
    except InvalidContinueError:
        # Drop the stale token and re-walk from the start (idempotent).
        restart_done = articles_repo.count()
        state_repo.save(ScrapeState(None, restart_done, total))
        _ingest_from(None, restart_done, client, articles_repo, state_repo,
                     conn, total, progress_cb, should_cancel)


def _ingest_from(token, done, client, articles_repo, state_repo, conn, total,
                 progress_cb, should_cancel):
    for articles, next_token in client.iter_batches(start_token=token):
        if should_cancel and should_cancel():
            return
        for art in articles:
            if articles_repo.add_article(art.pageid, art.title, art.text,
                                         art.revid, _url_for(art.title),
                                         commit=False):
                done += 1
        state_repo.save(ScrapeState(next_token, done, total), commit=False)
        conn.commit()
        if progress_cb:
            progress_cb(done, total)

    # Reached the end: clear the resume token, keep the final count.
    state_repo.save(ScrapeState(None, done, total))
