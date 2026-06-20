from PySide6.QtWidgets import QApplication
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.scraper.worker import CategorySeedWorker
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, by_title):
        self._titles, self._by_title = titles, by_title

    def iter_category_members(self, category):
        return list(self._titles)

    def fetch_by_titles(self, titles):
        return [self._by_title[t] for t in titles if t in self._by_title]


def _seed_game(db):
    conn = connect(db)
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'T', '[]')")
    conn.commit()
    conn.close()


def test_worker_ingests_and_emits_count(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "s.db"
    _seed_game(db)
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="https://x/api.php",
                                page_url_base="https://x", category="Mobs",
                                client=client)
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))

    worker.run()  # synchronous in-test (no thread)

    assert errors == []
    assert counts == [1]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 1


def test_worker_emits_progress(tmp_path):
    QApplication.instance() or QApplication([])
    db = tmp_path / "p.db"
    _seed_game(db)
    client = FakeClient(["Creeper", "Zombie"],
                        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
                         "Zombie": WikiArticle(2, "Zombie", "groan", 6)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=client)
    progress = []
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.run()
    assert progress[0] == (0, 2)
    assert progress[-1] == (2, 2)


def test_worker_emits_error_on_failure(tmp_path):
    QApplication.instance() or QApplication([])
    class Boom:
        def iter_category_members(self, category):
            raise RuntimeError("offline")
        def fetch_by_titles(self, titles):
            return []
    worker = CategorySeedWorker(str(tmp_path / "e.db"), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=Boom())
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
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    worker = CategorySeedWorker(str(db), game_id=7, api_url="x",
                                page_url_base="x", category="Mobs", client=client)
    worker.cancel()
    counts, errors = [], []
    worker.finished.connect(lambda n: counts.append(n))
    worker.error.connect(lambda m: errors.append(m))
    worker.run()
    assert errors == []
    assert counts == [0]
    conn = connect(db); init_db(conn)
    assert ArticlesRepo(conn).count(game_id=7) == 0
