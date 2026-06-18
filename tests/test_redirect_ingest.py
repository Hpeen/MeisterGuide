from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.redirects import RedirectsRepo, RedirectStateRepo, RedirectState
from meister_guide.scraper.redirect_ingest import run_redirect_ingest


class FakeRedirectClient:
    """Yields canned (mappings, next_token) batches; records the start token."""
    def __init__(self, batches):
        self._batches = batches
        self.started_with = "UNSET"

    def iter_redirect_mappings(self, start_token=None):
        self.started_with = start_token
        for b in self._batches:
            yield b


def _setup(tmp_path):
    conn = connect(tmp_path / "ri.db")
    init_db(conn)
    return conn, ArticlesRepo(conn), RedirectsRepo(conn), RedirectStateRepo(conn)


def test_stores_aliases_only_for_known_target_articles(tmp_path):
    conn, arts, reds, state = _setup(tmp_path)
    arts.add_article(7, "Wolf (mob)", "wolves", 1, "u")
    batches = [([
        ("Wolf", "Wolf (mob)"),
        ("Doggo", "Wolf (mob)"),
        ("Ghost", "Nonexistent Page"),   # target not stored -> skipped
    ], None)]
    seen = []
    run_redirect_ingest(FakeRedirectClient(batches), reds, arts, state, conn,
                        progress_cb=lambda d: seen.append(d))
    assert reds.count() == 2
    assert seen[-1] == 2
    assert state.load().continue_token is None


def test_resumes_from_saved_token(tmp_path):
    conn, arts, reds, state = _setup(tmp_path)
    state.save(RedirectState(continue_token="tok1", done=5))
    client = FakeRedirectClient([([], None)])
    run_redirect_ingest(client, reds, arts, state, conn)
    assert client.started_with == "tok1"


def test_stops_when_cancelled(tmp_path):
    conn, arts, reds, state = _setup(tmp_path)
    arts.add_article(7, "Wolf (mob)", "w", 1, None)
    batches = [
        ([("Wolf", "Wolf (mob)")], "tok1"),
        ([("Doggo", "Wolf (mob)")], None),
    ]
    run_redirect_ingest(FakeRedirectClient(batches), reds, arts, state, conn,
                        should_cancel=lambda: True)
    assert reds.count() == 0                       # cancelled before first commit


def test_recovers_from_stale_continue_token(tmp_path):
    from meister_guide.scraper.wiki_client import InvalidContinueError
    conn, arts, reds, state = _setup(tmp_path)
    arts.add_article(7, "Wolf (mob)", "w", 1, None)
    state.save(RedirectState(continue_token="STALE", done=3))

    class StaleClient:
        def __init__(self):
            self.tokens = []
        def iter_redirect_mappings(self, start_token=None):
            self.tokens.append(start_token)
            if start_token is not None:
                raise InvalidContinueError("badcontinue")
            yield ([("Wolf", "Wolf (mob)")], None)

    client = StaleClient()
    run_redirect_ingest(client, reds, arts, state, conn)
    assert client.tokens == ["STALE", None]        # tried stale, then restarted
    assert reds.count() == 1
    assert state.load().continue_token is None
