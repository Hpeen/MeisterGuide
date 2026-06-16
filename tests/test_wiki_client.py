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


def test_retries_transient_error_then_succeeds():
    calls = {"n": 0}
    def flaky_get(params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503 Service Unavailable")
        return {"query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}}}
    slept = []
    client = WikiClient(http_get=flaky_get, delay=0, sleep=lambda s: slept.append(s))

    batches = list(client.iter_batches())
    assert calls["n"] == 2            # retried once
    assert slept                      # backed off before retry
    assert batches[0][0][0].title == "A"


def test_maxlag_error_is_retried():
    calls = {"n": 0}
    def lagging_get(params):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": {"code": "maxlag", "info": "Waiting for a server"}}
        return {"query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}}}
    client = WikiClient(http_get=lagging_get, delay=0, sleep=lambda s: None)
    list(client.iter_batches())
    assert calls["n"] == 2


def test_gives_up_after_max_retries():
    def always_fail(params):
        raise RuntimeError("network down")
    client = WikiClient(http_get=always_fail, delay=0, sleep=lambda s: None,
                        max_retries=3)
    import pytest
    with pytest.raises(RuntimeError):
        list(client.iter_batches())


def test_non_maxlag_api_error_raises():
    def erroring_get(params):
        return {"error": {"code": "badvalue", "info": "Unrecognized value"}}
    client = WikiClient(http_get=erroring_get, delay=0, sleep=lambda s: None,
                        max_retries=3)
    import pytest
    with pytest.raises(RuntimeError):
        list(client.iter_batches())
