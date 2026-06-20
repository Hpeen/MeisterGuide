from PySide6.QtWidgets import QApplication
from meister_guide.scraper.worker import WebFetchWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeSearch:
    def __init__(self, results):
        self._results = results
    def search(self, query, count=3):
        return list(self._results)


def _seed_game(db):
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'G', '[]')")
    conn.commit()
    conn.close()


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "w.db"
    _seed_game(db)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetch = lambda url: ("Wolf", "body " * 100)
    worker = WebFetchWorker(str(db), game_id=7, query="wolf", api_key="k",
                            client=search, fetch_fn=fetch)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def search(self, q, count=3):
            raise RuntimeError("offline")
    worker = WebFetchWorker(str(tmp_path / "e.db"), game_id=7, query="q",
                            api_key="k", client=Boom(), fetch_fn=lambda u: ("", ""))
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert counts == []
    assert errors and "offline" in errors[0]


def test_worker_cancel_skips_ingest(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "c.db"
    _seed_game(db)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    worker = WebFetchWorker(str(db), game_id=7, query="wolf", api_key="k",
                            client=search, fetch_fn=lambda u: ("Wolf", "body " * 100))
    worker.cancel()
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [0]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 0
