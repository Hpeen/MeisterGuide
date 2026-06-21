from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import IngestWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, batches):
        self._batches = batches
    def iter_batches(self, start_token=None):
        yield from self._batches
    def iter_redirect_mappings(self, start_token=None):
        return iter(())            # no redirects in this fixture
    def article_count(self):
        return 2


def test_worker_runs_ingest_and_emits_signals(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "w.db"
    client = FakeClient([([WikiArticle(1, "A", "a", 1), WikiArticle(2, "B", "b", 1)], None)])
    worker = IngestWorker(str(db), client=client)

    progress, finished, errors = [], [], []
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.finished.connect(lambda: finished.append(True))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert finished == [True]
    assert progress and progress[-1][0] == 2
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count() == 2


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def article_count(self): return 0
        def iter_batches(self, start_token=None):
            raise RuntimeError("kaboom")
    worker = IngestWorker(str(tmp_path / "e.db"), client=Boom())
    errors, finished = [], []
    worker.error.connect(lambda m: errors.append(m))
    worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert finished == []
    assert errors and "kaboom" in errors[0]


def test_worker_uses_api_url_and_emits_counted(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "c.db"
    conn = connect(db); init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (5,'G','[]')")
    conn.commit(); conn.close()

    client = FakeClient([([WikiArticle(1, "A", "a", 1)], None)])
    worker = IngestWorker(str(db), game_id=5, api_url="https://x/api.php",
                          page_url_base="https://x", client=client)
    counted, finished = [], []
    worker.counted.connect(lambda n: counted.append(n))
    worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert counted == [2]
    assert finished == [True]
    conn = connect(db); init_db(conn)
    url = conn.execute("SELECT url FROM articles WHERE pageid=1").fetchone()[0]
    assert url == "https://x/wiki/A"
