from meister_guide.scraper.urls import wiki_base, page_url


def test_wiki_base_strips_article_path():
    # A pasted page URL is normalized to the wiki base.
    assert wiki_base("https://subnautica.fandom.com/wiki/Subnautica_Wiki") == \
        "https://subnautica.fandom.com"
    assert wiki_base("https://minecraft.wiki/w/Creeper") == "https://minecraft.wiki"


def test_wiki_base_leaves_a_bare_base_untouched():
    assert wiki_base("https://subnautica.fandom.com") == "https://subnautica.fandom.com"
    assert wiki_base("https://minecraft.wiki/") == "https://minecraft.wiki"


def test_wiki_base_preserves_language_subpath():
    assert wiki_base("https://subnautica.fandom.com/de/wiki/Titel") == \
        "https://subnautica.fandom.com/de"


def test_wiki_base_does_not_strip_lookalike_path():
    # "/wikipedia" is not an article path (no slash after "wiki").
    assert wiki_base("https://example.com/wikipedia") == "https://example.com/wikipedia"


def test_wiki_base_handles_empty():
    assert wiki_base("") == ""
    assert wiki_base(None) == ""


def test_page_url_normalizes_a_page_url_base():
    # Even if the stored base is a full page URL, the display link is correct.
    assert page_url("https://subnautica.fandom.com/wiki/Subnautica_Wiki", "Seamoth") == \
        "https://subnautica.fandom.com/wiki/Seamoth"
    assert page_url("https://subnautica.fandom.com", "Reaper Leviathan") == \
        "https://subnautica.fandom.com/wiki/Reaper_Leviathan"
