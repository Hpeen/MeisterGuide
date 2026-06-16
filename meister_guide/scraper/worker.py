"""QThread worker that runs the ingest off the UI thread. It opens its OWN
SQLite connection inside run() because SQLite connections are not safe to share
across threads."""
from PySide6.QtCore import QObject, Signal

from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo
from meister_guide.scraper.wiki_client import WikiClient
from meister_guide.scraper.ingest import run_ingest


class IngestWorker(QObject):
    progress = Signal(int, int)   # done, total (total may be 0 if unknown)
    finished = Signal()
    error = Signal(str)

    def __init__(self, db_path, client=None):
        super().__init__()
        self._db_path = db_path
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
            run_ingest(
                client,
                ArticlesRepo(conn),
                ScrapeStateRepo(conn),
                conn,
                progress_cb=lambda d, t: self.progress.emit(d, t or 0),
                should_cancel=lambda: self._cancel,
            )
        except Exception as err:
            self.error.emit(str(err))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished.emit()
