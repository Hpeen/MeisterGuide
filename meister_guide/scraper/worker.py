"""QThread worker that runs the ingest off the UI thread. It opens its OWN
SQLite connection inside run() because SQLite connections are not safe to share
across threads."""
from PySide6.QtCore import QObject, Signal

from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.db.redirects import RedirectsRepo, RedirectStateRepo
from meister_guide.scraper.wiki_client import WikiClient
from meister_guide.scraper.ingest import run_ingest
from meister_guide.scraper.redirect_ingest import run_redirect_ingest
from meister_guide.scraper.on_demand import run_on_demand_fetch
from meister_guide.ai.ranking import is_noise


class IngestWorker(QObject):
    progress = Signal(int, int)   # done, total (total may be 0 if unknown)
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_path, game_id=None, client=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._client = client
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        conn = None
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient()
            articles_repo = ArticlesRepo(conn)
            # One-time cleanup: drop any noise pages (versioned/changelog/disambig)
            # stored before noise filtering existed. Cheap once the corpus is clean.
            articles_repo.prune_noise(is_noise)
            run_ingest(
                client,
                articles_repo,
                ScrapeStateRepo(conn),
                conn,
                progress_cb=lambda d, t: self.progress.emit(d, t or 0),
                should_cancel=lambda: self._cancel,
                game_id=self._game_id,
            )
            if self._cancel:
                return
            # Redirect aliases run second: they resolve against the articles just
            # stored, so popular redirect-only topics ("Wolf", "Redstone") become
            # reachable in chat. Progress is a running count (total unknown).
            run_redirect_ingest(
                client,
                RedirectsRepo(conn),
                articles_repo,
                RedirectStateRepo(conn),
                conn,
                progress_cb=lambda d: self.progress.emit(d, 0),
                should_cancel=lambda: self._cancel,
                game_id=self._game_id,
            )
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit()


class OnDemandFetchWorker(QObject):
    """Runs a single on-demand wiki fetch off the UI thread. Opens its OWN
    SQLite connection inside run() (SQLite connections aren't thread-safe to
    share) and builds a WikiClient pointed at the active game's API endpoint."""
    finished = Signal(int)   # number of articles ingested
    error = Signal(str)

    def __init__(self, db_path, game_id, api_url, page_url_base, query,
                 client=None):
        super().__init__()
        self._db_path = db_path
        self._game_id = game_id
        self._api_url = api_url
        self._page_url_base = page_url_base
        self._query = query
        self._client = client

    def run(self):
        conn = None
        try:
            conn = connect(self._db_path)
            init_db(conn)
            client = self._client or WikiClient(api_url=self._api_url)
            n = run_on_demand_fetch(client, ArticlesRepo(conn), self._game_id,
                                    self._query, base=self._page_url_base)
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit(n)
