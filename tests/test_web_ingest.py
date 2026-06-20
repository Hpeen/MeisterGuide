from meister_guide.scraper.web_ingest import run_web_fetch
from meister_guide.scraper.urls import web_pageid
from meister_guide.db.database import connect, init_db
from meister_guide.db.articles import ArticlesRepo


class FakeSearch:
    def __init__(self, results):
        self._results = results
        self.searched = None

    def search(self, query, count=3):
        self.searched = (query, count)
        return list(self._results)


def _repo(tmp_path):
    conn = connect(tmp_path / "web.db")
    init_db(conn)
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (7, 'G', '[]')")
    conn.commit()
    return ArticlesRepo(conn)


def _fetch_fn(pages):
    # pages: dict url -> (title, text)
    def fetch(url):
        return pages.get(url, ("", ""))
    return fetch


def test_ingests_results_scoped_to_game_with_source_url(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Tame a wolf", "https://x/wolf")])
    fetch = _fetch_fn({"https://x/wolf": ("Tame a wolf", "Give it a bone." * 50)})
    n = run_web_fetch(search, fetch, repo, game_id=7, query="tame wolf")
    assert n == 1
    assert repo.count(game_id=7) == 1
    art = repo.get_article(web_pageid("https://x/wolf"))
    assert art.url == "https://x/wolf"
    assert "bone" in art.body


def test_skips_pages_under_min_chars(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Thin", "https://x/thin")])
    fetch = _fetch_fn({"https://x/thin": ("Thin", "too short")})
    n = run_web_fetch(search, fetch, repo, 7, "q", min_chars=200)
    assert n == 0
    assert repo.count(game_id=7) == 0


def test_caps_at_limit(tmp_path):
    repo = _repo(tmp_path)
    results = [(f"T{i}", f"https://x/{i}") for i in range(10)]
    pages = {u: (t, "body " * 100) for t, u in results}
    n = run_web_fetch(FakeSearch(results), _fetch_fn(pages), repo, 7, "q", limit=3)
    assert n == 3
    assert repo.count(game_id=7) == 3


def test_idempotent_on_rerun(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetch = _fetch_fn({"https://x/wolf": ("Wolf", "body " * 100)})
    assert run_web_fetch(search, fetch, repo, 7, "q") == 1
    assert run_web_fetch(search, fetch, repo, 7, "q") == 0   # synthetic pageid dedupe
    assert repo.count(game_id=7) == 1


def test_no_results_makes_no_fetch(tmp_path):
    repo = _repo(tmp_path)
    fetched = []
    def fetch(url):
        fetched.append(url)
        return ("t", "body " * 100)
    n = run_web_fetch(FakeSearch([]), fetch, repo, 7, "q")
    assert n == 0
    assert fetched == []


def test_should_cancel_stops_before_fetch(tmp_path):
    repo = _repo(tmp_path)
    search = FakeSearch([("Wolf", "https://x/wolf")])
    fetched = []
    def fetch(url):
        fetched.append(url)
        return ("t", "body " * 100)
    n = run_web_fetch(search, fetch, repo, 7, "q", should_cancel=lambda: True)
    assert n == 0
    assert fetched == []        # cancelled before any fetch
    assert repo.count(game_id=7) == 0
