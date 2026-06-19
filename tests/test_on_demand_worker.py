from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import OnDemandFetchWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, articles):
        self._titles, self._articles = titles, articles

    def search_titles(self, query, limit=5):
        return self._titles

    def fetch_by_titles(self, titles):
        return self._articles


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "od.db"
    # seed game row so FK constraint is satisfied when game_id=7 is used
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'TestGame', '[]')")
    conn.commit()
    conn.close()

    client = FakeClient(["Creeper"], [WikiArticle(1, "Creeper", "boom", 5)])
    worker = OnDemandFetchWorker(str(db), game_id=7,
                                 api_url="https://x/api.php",
                                 page_url_base="https://x", query="creeper",
                                 client=client)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def search_titles(self, q, limit=5):
            raise RuntimeError("offline")
        def fetch_by_titles(self, t):
            return []
    worker = OnDemandFetchWorker(str(tmp_path / "e.db"), game_id=7,
                                 api_url="x", page_url_base="x", query="q",
                                 client=Boom())
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()

    assert counts == []
    assert errors and "offline" in errors[0]


def test_worker_cancel_skips_ingest(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "c.db"
    # seed the games row (FK) exactly like test_worker_ingests_and_emits_count does
    conn = connect(db); init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'T', '[]')")
    conn.commit(); conn.close()
    client = FakeClient(["Creeper"], [WikiArticle(1, "Creeper", "boom", 5)])
    worker = OnDemandFetchWorker(str(db), game_id=7, api_url="x",
                                 page_url_base="x", query="creeper",
                                 client=client)
    worker.cancel()
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [0]                  # finished cleanly with nothing ingested
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 0
