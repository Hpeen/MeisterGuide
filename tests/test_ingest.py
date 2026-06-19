from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.ingest import run_ingest


class FakeClient:
    """Yields canned (articles, next_token) batches; records the start token."""
    def __init__(self, batches):
        self._batches = batches
        self.started_with = "UNSET"
    def iter_batches(self, start_token=None):
        self.started_with = start_token
        for b in self._batches:
            yield b
    def article_count(self):
        return 3


def _setup(tmp_path):
    conn = connect(tmp_path / "i.db")
    init_db(conn)
    return conn, ArticlesRepo(conn), ScrapeStateRepo(conn)


def test_run_ingest_populates_db_and_reports_progress(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [
        ([WikiArticle(1, "A", "alpha", 1), WikiArticle(2, "B", "beta", 1)], "tok1"),
        ([WikiArticle(3, "C", "gamma", 1)], None),
    ]
    seen = []
    run_ingest(FakeClient(batches), arts, state, conn,
               progress_cb=lambda d, t: seen.append((d, t)))
    assert arts.count() == 3
    assert seen[-1][0] == 3                 # done count reached total articles
    assert state.load().continue_token is None   # finished -> token cleared


def test_run_ingest_skips_noise_pages(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [
        ([WikiArticle(1, "Creeper", "a creeper", 1),
          WikiArticle(2, "Java Edition 1.20", "changelog", 1),
          WikiArticle(3, "Spider", "a spider", 1)], None),
    ]
    run_ingest(FakeClient(batches), arts, state, conn)
    assert arts.count() == 2                  # the versioned changelog page is skipped
    assert arts.get_article(2) is None        # "Java Edition 1.20" not stored
    assert arts.get_article(1) is not None    # "Creeper" kept
    assert arts.get_article(3) is not None    # "Spider" kept


def test_run_ingest_resumes_from_saved_token(tmp_path):
    conn, arts, state = _setup(tmp_path)
    from meister_guide.scraper.ingest import ScrapeState  # re-exported
    state.save(ScrapeState(continue_token="tok1", done=2, total=3))
    client = FakeClient([([WikiArticle(3, "C", "g", 1)], None)])
    run_ingest(client, arts, state, conn)
    assert client.started_with == "tok1"    # resumed, not restarted


def test_run_ingest_stops_when_cancelled(tmp_path):
    conn, arts, state = _setup(tmp_path)
    batches = [
        ([WikiArticle(1, "A", "a", 1)], "tok1"),
        ([WikiArticle(2, "B", "b", 1)], None),
    ]
    run_ingest(FakeClient(batches), arts, state, conn, should_cancel=lambda: True)
    assert arts.count() == 0                 # cancelled before first batch committed
    assert state.load().continue_token is None  # resume position left untouched


def test_run_ingest_recovers_from_stale_continue_token(tmp_path):
    from meister_guide.scraper.wiki_client import InvalidContinueError
    from meister_guide.scraper.ingest import ScrapeState
    conn, arts, state = _setup(tmp_path)
    state.save(ScrapeState(continue_token="STALE", done=7, total=2))

    class StaleTokenClient:
        def __init__(self):
            self.tokens = []
        def iter_batches(self, start_token=None):
            self.tokens.append(start_token)
            if start_token is not None:           # the stale token is rejected
                raise InvalidContinueError("badcontinue")
            yield ([WikiArticle(1, "A", "a", 1), WikiArticle(2, "B", "b", 1)], None)
        def article_count(self):
            return 2

    client = StaleTokenClient()
    run_ingest(client, arts, state, conn)
    assert client.tokens == ["STALE", None]      # tried stale, then restarted clean
    assert arts.count() == 2
    assert state.load().continue_token is None


def test_run_ingest_tags_articles_with_game_id(tmp_path):
    conn, arts, state = _setup(tmp_path)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (42, 'G42', '[]')")
    conn.commit()
    batches = [([WikiArticle(1, "Creeper", "a creeper", 1)], None)]
    run_ingest(FakeClient(batches), arts, state, conn, game_id=42)
    assert conn.execute("SELECT game_id FROM articles WHERE pageid=1").fetchone()[0] == 42
