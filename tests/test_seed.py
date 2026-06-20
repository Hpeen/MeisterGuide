from meister_guide.scraper.seed import run_category_seed
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    """iter_category_members returns canned titles; fetch_by_titles returns the
    canned article for each requested title (one per request, like TextExtracts)."""
    def __init__(self, titles, by_title):
        self._titles = titles
        self._by_title = by_title
        self.fetched = []

    def iter_category_members(self, category):
        return list(self._titles)

    def fetch_by_titles(self, titles):
        self.fetched.append(list(titles))
        out = []
        for t in titles:
            if t in self._by_title:
                out.append(self._by_title[t])
        return out


def _repo(tmp_path):
    conn = connect(tmp_path / "seed.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'TestGame', '[]')")
    conn.commit()
    return ArticlesRepo(conn)


def test_ingests_all_members_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Zombie"],
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
         "Zombie": WikiArticle(2, "Zombie", "groan", 6)},
    )
    n = run_category_seed(client, repo, game_id=7, category="Mobs",
                          base="https://mc.wiki")
    assert n == 2
    assert repo.count(game_id=7) == 2
    assert repo.get_article(1).url == "https://mc.wiki/wiki/Creeper"


def test_skips_noise_titles_without_fetching(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Java Edition 1.16"],   # second is a noise title
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5)},
    )
    n = run_category_seed(client, repo, 7, "Mobs")
    assert n == 1
    assert repo.count(game_id=7) == 1
    assert client.fetched == [["Creeper"]]   # never fetched the noise title


def test_caps_number_of_pages(tmp_path):
    repo = _repo(tmp_path)
    titles = [f"P{i}" for i in range(10)]
    by_title = {t: WikiArticle(i, t, "x", 1) for i, t in enumerate(titles)}
    client = FakeClient(titles, by_title)
    n = run_category_seed(client, repo, 7, "Mobs", cap=3)
    assert n == 3
    assert repo.count(game_id=7) == 3


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Creeper"], {"Creeper": WikiArticle(1, "Creeper", "boom", 5)})
    assert run_category_seed(client, repo, 7, "Mobs") == 1
    assert run_category_seed(client, repo, 7, "Mobs") == 0   # dedupe by pageid
    assert repo.count(game_id=7) == 1


def test_progress_reports_total_then_each_step(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Zombie"],
        {"Creeper": WikiArticle(1, "Creeper", "boom", 5),
         "Zombie": WikiArticle(2, "Zombie", "groan", 6)},
    )
    calls = []
    run_category_seed(client, repo, 7, "Mobs",
                      progress_cb=lambda d, t: calls.append((d, t)))
    assert calls[0] == (0, 2)
    assert calls[-1] == (2, 2)


def test_should_cancel_stops_mid_walk(tmp_path):
    repo = _repo(tmp_path)
    titles = ["Creeper", "Zombie", "Skeleton"]
    by_title = {t: WikiArticle(i, t, "x", 1) for i, t in enumerate(titles)}
    client = FakeClient(titles, by_title)
    # cancel after the first page is ingested
    seen = {"n": 0}
    def should_cancel():
        seen["n"] += 1
        return seen["n"] > 1
    n = run_category_seed(client, repo, 7, "Mobs", should_cancel=should_cancel)
    assert n == 1
    assert repo.count(game_id=7) == 1


def test_empty_category_ingests_nothing(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient([], {})
    assert run_category_seed(client, repo, 7, "Mobs") == 0
    assert client.fetched == []
