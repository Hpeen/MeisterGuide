from meister_guide.scraper.on_demand import run_on_demand_fetch
from meister_guide.scraper.wiki_client import WikiArticle
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeClient:
    def __init__(self, titles, articles):
        self._titles = titles
        self._articles = articles
        self.searched = None
        self.fetched = None

    def search_titles(self, query, limit=5):
        self.searched = (query, limit)
        return self._titles

    def fetch_by_titles(self, titles):
        self.fetched = titles
        return self._articles


def _repo(tmp_path):
    conn = connect(tmp_path / "od.db")
    init_db(conn)
    # seed game row so FK constraint is satisfied when game_id=7 is used
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'TestGame', '[]')")
    conn.commit()
    return ArticlesRepo(conn)


def test_ingests_non_noise_scoped_to_game(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(
        ["Creeper", "Java Edition 1.16"],
        [WikiArticle(1, "Creeper", "boom", 5),
         WikiArticle(2, "Java Edition 1.16", "changelog", 6)],  # noise title
    )
    n = run_on_demand_fetch(client, repo, game_id=7, query="creeper",
                            base="https://minecraft.wiki")
    assert n == 1                       # the noise page is skipped
    assert repo.count(game_id=7) == 1
    art = repo.get_article(1)
    assert art.title == "Creeper"
    assert art.url == "https://minecraft.wiki/wiki/Creeper"


def test_returns_zero_and_no_fetch_when_no_search_results(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient([], [])
    assert run_on_demand_fetch(client, repo, game_id=7, query="zzz") == 0
    assert client.fetched is None       # never fetch when search found nothing


def test_limit_caps_titles_fetched(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["A", "B", "C", "D", "E"], [])
    run_on_demand_fetch(client, repo, game_id=7, query="x", limit=3)
    assert client.fetched == ["A", "B", "C"]


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Creeper"], [WikiArticle(1, "Creeper", "boom", 5)])
    assert run_on_demand_fetch(client, repo, 7, "creeper") == 1
    assert run_on_demand_fetch(client, repo, 7, "creeper") == 0   # dedupe by pageid
    assert repo.count(game_id=7) == 1


def test_page_url_handles_spaces_and_trailing_slash(tmp_path):
    repo = _repo(tmp_path)
    client = FakeClient(["Iron Golem"],
                        [WikiArticle(9, "Iron Golem", "guards", 1)])
    run_on_demand_fetch(client, repo, 7, "golem", base="https://minecraft.wiki/")
    assert repo.get_article(9).url == "https://minecraft.wiki/wiki/Iron_Golem"
