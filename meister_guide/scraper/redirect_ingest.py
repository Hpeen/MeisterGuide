"""Walk the wiki's redirects into the DB after the article ingest: for each
redirect (from_title -> to_title), look up the target article by title and store
an alias row so chat retrieval can match the redirect title. Per-batch commits,
resume token, and progress/cancel hooks. No Qt here so it stays unit-testable."""
from meister_guide.db.redirects import RedirectState
from meister_guide.scraper.wiki_client import InvalidContinueError


def run_redirect_ingest(client, redirects_repo, articles_repo, state_repo, conn,
                        progress_cb=None, should_cancel=None, game_id=None):
    """Ingest redirect aliases into `redirects_repo`. Targets that aren't stored
    articles (other namespaces, or unresolved double redirects) are skipped.
    Resumes from the saved token; restarts once if the token is rejected as
    stale (add_redirect is idempotent, so stored aliases are skipped)."""
    st = state_repo.load(game_id)
    try:
        _walk(st.continue_token, st.done, client, redirects_repo, articles_repo,
              state_repo, conn, progress_cb, should_cancel, game_id)
    except InvalidContinueError:
        restart_done = redirects_repo.count_by_game(game_id)
        state_repo.save(RedirectState(None, restart_done), game_id)
        _walk(None, restart_done, client, redirects_repo, articles_repo,
              state_repo, conn, progress_cb, should_cancel, game_id)


def _walk(token, done, client, redirects_repo, articles_repo, state_repo, conn,
          progress_cb, should_cancel, game_id=None):
    for mappings, next_token in client.iter_redirect_mappings(start_token=token):
        if should_cancel and should_cancel():
            return
        for from_title, to_title in mappings:
            target_pageid = articles_repo.pageid_by_title(to_title)
            if target_pageid is None:
                continue
            if redirects_repo.add_redirect(from_title, target_pageid,
                                           game_id=game_id, commit=False):
                done += 1
        state_repo.save(RedirectState(next_token, done), game_id, commit=False)
        conn.commit()
        if progress_cb:
            progress_cb(done)

    # Reached the end: clear the resume token, keep the final count.
    state_repo.save(RedirectState(None, done), game_id)
