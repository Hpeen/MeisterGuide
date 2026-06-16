"""Drive the WikiClient into the DB: per-batch transactions, resume token, and
progress/cancel hooks. No Qt here so it stays unit-testable."""
from meister_guide.db.articles import ScrapeState  # re-export for callers


def _url_for(title: str) -> str:
    return "https://minecraft.wiki/w/" + title.replace(" ", "_")


def run_ingest(client, articles_repo, state_repo, conn,
               progress_cb=None, should_cancel=None):
    """Ingest all article batches from `client` into the repos.

    Resumes from the saved continue token, commits once per batch (so a crash
    loses at most one batch), and stops cleanly if should_cancel() turns true."""
    state = state_repo.load()
    total = state.total
    if total is None:
        try:
            total = client.article_count()
        except Exception:
            total = None
    done = state.done

    for articles, next_token in client.iter_batches(start_token=state.continue_token):
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
