from meister_guide.scraper.web_search import (
    DuckDuckGoSearchClient, make_search_client, BraveSearchClient,
)


def test_ddg_parses_title_href_pairs():
    def fake_search(query, count):
        return [{"title": "Tame a wolf", "href": "https://x/wolf", "body": "..."},
                {"title": "Bone", "href": "https://x/bone", "body": "..."}]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert client.search("wolf") == [
        ("Tame a wolf", "https://x/wolf"), ("Bone", "https://x/bone")]


def test_ddg_passes_query_and_count():
    seen = {}
    def fake_search(query, count):
        seen["query"], seen["count"] = query, count
        return []
    DuckDuckGoSearchClient(search_fn=fake_search).search("how to tame", count=2)
    assert seen == {"query": "how to tame", "count": 2}


def test_ddg_respects_count_limit():
    def fake_search(query, count):
        return [{"title": f"T{i}", "href": f"https://x/{i}"} for i in range(10)]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert len(client.search("q", count=3)) == 3


def test_ddg_skips_results_without_href_and_title_falls_back():
    def fake_search(query, count):
        return [{"title": "no href here"}, {"href": "https://x/c"}]
    client = DuckDuckGoSearchClient(search_fn=fake_search)
    assert client.search("q") == [("https://x/c", "https://x/c")]


def test_ddg_empty_when_no_results():
    client = DuckDuckGoSearchClient(search_fn=lambda q, c: [])
    assert client.search("zzz") == []


def test_make_search_client_brave_when_key():
    assert isinstance(make_search_client("brv-123"), BraveSearchClient)


def test_make_search_client_ddg_when_no_key():
    assert isinstance(make_search_client(""), DuckDuckGoSearchClient)
    assert isinstance(make_search_client(None), DuckDuckGoSearchClient)
