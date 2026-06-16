from meister_guide.scraper.wiki_client import WikiClient, WikiArticle


def _one_batch_response():
    return {
        "query": {"pages": {
            "101": {"pageid": 101, "title": "Creeper", "extract": "It explodes.", "lastrevid": 9},
            "102": {"pageid": 102, "title": "Cow", "extract": "It moos.", "lastrevid": 8},
            "103": {"pageid": 103, "title": "Empty"},  # no extract -> skipped
        }}
        # no "continue" key -> last batch
    }


def test_iter_batches_parses_articles_and_stops():
    calls = []
    def fake_get(params):
        calls.append(params)
        return _one_batch_response()
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)

    batches = list(client.iter_batches())
    assert len(batches) == 1
    articles, next_token = batches[0]
    assert next_token is None
    titles = sorted(a.title for a in articles)
    assert titles == ["Cow", "Creeper"]          # "Empty" skipped (no extract)
    assert isinstance(articles[0], WikiArticle)
    assert len(calls) == 1
