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


def test_article_count_reads_statistics():
    def fake_get(params):
        assert params.get("meta") == "siteinfo"
        return {"query": {"statistics": {"articles": 16689, "pages": 296047}}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.article_count() == 16689


def test_request_gaplimit_is_aligned_to_extract_limit():
    # Full-text extracts return only 1 per request (TextExtracts caps exlimit=1
    # without exintro), so a large gaplimit just wastes metadata bandwidth.
    # gaplimit must be a small aligned value, not "max"/500.
    captured = []
    def fake_get(params):
        captured.append(dict(params))
        return {"query": {"pages": {"1": {"pageid": 1, "title": "A", "extract": "a"}}}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    next(client.iter_batches())
    assert captured[0]["gaplimit"] == 20


def test_default_delay_is_zero():
    # Politeness is enforced by maxlag, not a fixed per-request sleep; a 1s
    # default delay across ~16.7k single-article requests added hours.
    assert WikiClient(http_get=lambda p: {}).__dict__["_delay"] == 0


def test_iter_redirect_mappings_enumerates_and_resolves():
    def fake_get(params):
        if params.get("list") == "allpages":
            assert params.get("apfilterredir") == "redirects"
            return {"query": {"allpages": [
                {"pageid": 1, "title": "Wolf"},
                {"pageid": 2, "title": "Doggo"},
            ]}}
        if "titles" in params:
            assert params.get("redirects") == 1
            return {"query": {"redirects": [
                {"from": "Wolf", "to": "Wolf (mob)"},
                {"from": "Doggo", "to": "Wolf (mob)", "tofragment": "Breeding"},
            ]}}
        raise AssertionError(params)
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    batches = list(client.iter_redirect_mappings())
    assert len(batches) == 1
    mappings, token = batches[0]
    assert token is None
    assert ("Wolf", "Wolf (mob)") in mappings
    assert ("Doggo", "Wolf (mob)") in mappings


def test_iter_redirect_mappings_follows_continue_token():
    allpages = [
        {"query": {"allpages": [{"title": "Wolf"}]},
         "continue": {"apcontinue": "R", "continue": "-||"}},
        {"query": {"allpages": [{"title": "Redstone"}]}},
    ]
    resolves = {
        "Wolf": [{"from": "Wolf", "to": "Wolf (mob)"}],
        "Redstone": [{"from": "Redstone", "to": "Redstone Dust"}],
    }
    seen = []
    def fake_get(params):
        if params.get("list") == "allpages":
            seen.append(dict(params))
            return allpages.pop(0)
        return {"query": {"redirects": resolves[params["titles"]]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    batches = list(client.iter_redirect_mappings())
    assert [t for _, t in batches][0] == '{"apcontinue": "R", "continue": "-||"}'
    assert batches[-1][1] is None
    assert seen[1].get("apcontinue") == "R"   # carried the continuation
    all_maps = [m for ms, _ in batches for m in ms]
    assert ("Wolf", "Wolf (mob)") in all_maps
    assert ("Redstone", "Redstone Dust") in all_maps


def test_iter_redirect_mappings_skips_resolve_when_batch_empty():
    calls = []
    def fake_get(params):
        calls.append(params.get("list") or "resolve")
        if params.get("list") == "allpages":
            return {"query": {"allpages": []}}
        raise AssertionError("must not resolve an empty batch")
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert list(client.iter_redirect_mappings()) == [([], None)]
    assert calls == ["allpages"]


def test_badcontinue_raises_invalid_continue_error():
    # A stale/invalid resume token must be distinguishable from a generic API
    # error so the orchestrator can recover by restarting.
    from meister_guide.scraper.wiki_client import InvalidContinueError
    def fake_get(params):
        return {"error": {"code": "badcontinue", "info": "Invalid continue param."}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    import pytest
    with pytest.raises(InvalidContinueError):
        list(client.iter_batches())


def test_search_titles_returns_titles_in_namespace_0():
    def fake_get(params):
        assert params["action"] == "query"
        assert params["list"] == "search"
        assert params["srsearch"] == "how to tame a wolf"
        assert params["srnamespace"] == 0
        assert params["srlimit"] == 5
        return {"query": {"search": [
            {"title": "Wolf"}, {"title": "Bone"},
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.search_titles("how to tame a wolf") == ["Wolf", "Bone"]


def test_search_titles_respects_limit():
    seen = {}
    def fake_get(params):
        seen["srlimit"] = params["srlimit"]
        return {"query": {"search": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.search_titles("x", limit=3)
    assert seen["srlimit"] == 3


def test_search_titles_empty_when_no_results():
    client = WikiClient(http_get=lambda p: {"query": {"search": []}},
                        delay=0, sleep=lambda s: None)
    assert client.search_titles("zzzzz") == []


def test_fetch_by_titles_builds_titles_param_and_parses():
    def fake_get(params):
        assert params["titles"] == "Creeper|Cow"
        assert params["prop"] == "extracts"
        assert params["explaintext"] == 1
        return {"query": {"pages": {
            "1": {"pageid": 1, "title": "Creeper", "extract": "boom", "lastrevid": 5},
            "2": {"pageid": 2, "title": "Cow", "extract": "moo", "lastrevid": 6},
        }}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    arts = client.fetch_by_titles(["Creeper", "Cow"])
    assert sorted(a.title for a in arts) == ["Cow", "Creeper"]
    assert all(isinstance(a, WikiArticle) for a in arts)


def test_fetch_by_titles_empty_input_makes_no_request():
    calls = []
    def fake_get(params):
        calls.append(params)
        return {}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.fetch_by_titles([]) == []
    assert calls == []


def _siteinfo(extensions):
    return {"query": {"extensions": [{"name": n} for n in extensions]}}


def test_has_textextracts_true_when_extension_present():
    def get(params):
        assert params["meta"] == "siteinfo" and params["siprop"] == "extensions"
        return _siteinfo(["TextExtracts", "CirrusSearch"])
    client = WikiClient(http_get=get, delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is True


def test_has_textextracts_false_when_absent():
    client = WikiClient(http_get=lambda p: _siteinfo(["CirrusSearch"]),
                        delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is False


def test_has_textextracts_is_cached():
    calls = {"n": 0}
    def get(params):
        calls["n"] += 1
        return _siteinfo(["TextExtracts"])
    client = WikiClient(http_get=get, delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is True
    assert client.has_textextracts() is True
    assert calls["n"] == 1


def test_has_textextracts_false_on_detection_failure():
    def boom(params):
        raise RuntimeError("network down")
    client = WikiClient(http_get=boom, delay=0, sleep=lambda s: None, max_retries=2)
    assert client.has_textextracts() is False
