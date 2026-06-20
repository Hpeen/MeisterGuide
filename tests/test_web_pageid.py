from meister_guide.scraper.urls import web_pageid


def test_stable_for_same_url():
    assert web_pageid("https://example.com/a") == web_pageid("https://example.com/a")


def test_distinct_for_different_urls():
    assert web_pageid("https://example.com/a") != web_pageid("https://example.com/b")


def test_positive_and_above_wiki_range():
    # wiki pageids are small (< 1e8); synthetic ids must never collide with them
    pid = web_pageid("https://example.com/page")
    assert pid > 100_000_000
    assert pid > 0
