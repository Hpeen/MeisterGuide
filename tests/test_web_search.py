from meister_guide.scraper.web_search import BraveSearchClient


def test_sends_token_header_and_query_params():
    seen = {}
    def fake_get(url, headers, params):
        seen["url"] = url
        seen["headers"] = headers
        seen["params"] = params
        return {"web": {"results": [
            {"title": "Tame a wolf", "url": "https://x/wolf"},
        ]}}
    client = BraveSearchClient("brv-123", http_get=fake_get)
    client.search("how to tame a wolf", count=3)
    assert seen["headers"]["X-Subscription-Token"] == "brv-123"
    assert seen["params"]["q"] == "how to tame a wolf"
    assert seen["params"]["count"] == 3
    assert "api.search.brave.com" in seen["url"]


def test_parses_title_url_pairs():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": "A", "url": "https://x/a"},
            {"title": "B", "url": "https://x/b"},
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert client.search("q") == [("A", "https://x/a"), ("B", "https://x/b")]


def test_respects_count_limit():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": f"T{i}", "url": f"https://x/{i}"} for i in range(10)
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert len(client.search("q", count=2)) == 2


def test_skips_results_without_url_and_falls_back_title_to_url():
    def fake_get(url, headers, params):
        return {"web": {"results": [
            {"title": "no url here"},                 # dropped (no url)
            {"url": "https://x/c"},                    # title falls back to url
        ]}}
    client = BraveSearchClient("k", http_get=fake_get)
    assert client.search("q") == [("https://x/c", "https://x/c")]


def test_empty_when_no_results():
    client = BraveSearchClient("k", http_get=lambda u, h, p: {"web": {"results": []}})
    assert client.search("zzz") == []
