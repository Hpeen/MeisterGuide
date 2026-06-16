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


def test_iter_batches_follows_continue_token():
    page1 = {
        "query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}},
        "continue": {"gapcontinue": "B", "continue": "gapcontinue||"},
    }
    page2 = {
        "query": {"pages": {"2": {"pageid": 2, "title": "B", "extract": "b"}}},
    }
    responses = [page1, page2]
    seen_params = []
    def fake_get(params):
        seen_params.append(dict(params))
        return responses.pop(0)
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)

    batches = list(client.iter_batches())
    assert [t for _, t in batches][:1] == ['{"gapcontinue": "B", "continue": "gapcontinue||"}']
    assert batches[-1][1] is None
    all_titles = [a.title for batch, _ in batches for a in batch]
    assert all_titles == ["A", "B"]
    # second request carried the continuation params
    assert seen_params[1].get("gapcontinue") == "B"
