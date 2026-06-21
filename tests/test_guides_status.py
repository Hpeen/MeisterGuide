from meister_guide.guides_status import guides_status_text


def test_no_guides():
    assert guides_status_text(0, articles_done=False, redirects_done=False) == \
        "No guides downloaded yet."

def test_incomplete_download():
    assert guides_status_text(17916, articles_done=False, redirects_done=False) == \
        "Partly downloaded: 17,916 guides so far. Click Update to finish."

def test_articles_done_redirects_pending():
    assert guides_status_text(20000, articles_done=True, redirects_done=False) == \
        "Almost done. Click Update to link related topics."

def test_complete():
    assert guides_status_text(20000, articles_done=True, redirects_done=True) == \
        "All set: 20,000 guides."
