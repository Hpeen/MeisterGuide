from meister_guide.scraper.web_fetch import fetch_main_text


def test_returns_title_and_text_from_extractor():
    def fake_get(url):
        return "<html>...</html>"
    def fake_extract(html):
        return ("Tame a Wolf", "Give a wolf a bone to tame it.")
    title, text = fetch_main_text("https://x/wolf", http_get=fake_get,
                                  extract=fake_extract)
    assert title == "Tame a Wolf"
    assert "bone" in text


def test_title_falls_back_to_host_when_extractor_gives_none():
    def fake_extract(html):
        return ("", "some body text")
    title, text = fetch_main_text("https://wiki.example.com/page",
                                  http_get=lambda u: "<html></html>",
                                  extract=fake_extract)
    assert title == "wiki.example.com"
    assert text == "some body text"


def test_empty_text_returned_without_raising():
    def fake_extract(html):
        return ("", "")
    title, text = fetch_main_text("https://x/empty",
                                  http_get=lambda u: "<html></html>",
                                  extract=fake_extract)
    assert text == ""        # caller decides to skip; no exception
