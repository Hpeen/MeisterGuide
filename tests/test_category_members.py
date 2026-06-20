from meister_guide.scraper.wiki_client import WikiClient


def test_normalizes_bare_name_to_category_title():
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.iter_category_members("Mobs")
    assert seen[0]["cmtitle"] == "Category:Mobs"
    assert seen[0]["list"] == "categorymembers"


def test_accepts_category_prefixed_name():
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    client.iter_category_members("Category:Items")
    assert seen[0]["cmtitle"] == "Category:Items"


def test_empty_category_name_returns_empty_without_request():
    calls = []
    def fake_get(params):
        calls.append(params)
        return {"query": {"categorymembers": []}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("  ") == []
    assert calls == []


def test_returns_direct_article_members_only_when_no_subcats():
    def fake_get(params):
        return {"query": {"categorymembers": [
            {"pageid": 1, "ns": 0, "title": "Creeper"},
            {"pageid": 2, "ns": 0, "title": "Zombie"},
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["Creeper", "Zombie"]


def test_recurses_one_level_into_subcategories():
    def fake_get(params):
        if params["cmtitle"] == "Category:Mobs":
            # top level: one article + one subcategory (ns 14)
            assert params["cmnamespace"] == "0|14"
            return {"query": {"categorymembers": [
                {"pageid": 1, "ns": 0, "title": "Creeper"},
                {"pageid": 99, "ns": 14, "title": "Category:Hostile mobs"},
            ]}}
        if params["cmtitle"] == "Category:Hostile mobs":
            # subcategory: articles only (ns 0)
            assert params["cmnamespace"] == "0"
            return {"query": {"categorymembers": [
                {"pageid": 2, "ns": 0, "title": "Zombie"},
                {"pageid": 100, "ns": 14, "title": "Category:Nether mobs"},  # ignored
            ]}}
        raise AssertionError(params["cmtitle"])
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    # Zombie pulled from the subcategory; the deeper Nether subcategory is NOT walked.
    assert client.iter_category_members("Mobs") == ["Creeper", "Zombie"]


def test_dedupes_titles_across_category_and_subcategory():
    def fake_get(params):
        if params["cmtitle"] == "Category:Mobs":
            return {"query": {"categorymembers": [
                {"pageid": 1, "ns": 0, "title": "Creeper"},
                {"pageid": 14, "ns": 14, "title": "Category:Sub"},
            ]}}
        return {"query": {"categorymembers": [
            {"pageid": 1, "ns": 0, "title": "Creeper"},  # duplicate of top level
        ]}}
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["Creeper"]


def test_follows_cmcontinue_pagination():
    page1 = {"query": {"categorymembers": [{"pageid": 1, "ns": 0, "title": "A"}]},
             "continue": {"cmcontinue": "B", "continue": "-||"}}
    page2 = {"query": {"categorymembers": [{"pageid": 2, "ns": 0, "title": "B"}]}}
    responses = [page1, page2]
    seen = []
    def fake_get(params):
        seen.append(dict(params))
        return responses.pop(0)
    client = WikiClient(http_get=fake_get, delay=0, sleep=lambda s: None)
    assert client.iter_category_members("Mobs") == ["A", "B"]
    assert seen[1].get("cmcontinue") == "B"   # carried the continuation
