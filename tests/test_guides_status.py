from meister_guide.guides_status import guides_status_text


def test_no_guides():
    assert guides_status_text(0, articles_done=False, redirects_done=False) == \
        "No guides yet — click Update guides"

def test_incomplete_download():
    assert guides_status_text(17916, articles_done=False, redirects_done=False) == \
        "Incomplete — 17,916 downloaded · click Update to resume"

def test_articles_done_redirects_pending():
    assert guides_status_text(20000, articles_done=True, redirects_done=False) == \
        "Almost done — click Update to link related topics"

def test_complete():
    assert guides_status_text(20000, articles_done=True, redirects_done=True) == \
        "Complete · 20,000 articles"
