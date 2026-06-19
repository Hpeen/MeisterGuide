from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.articles import SearchHit


class StubRepo:
    def search(self, text, limit=50):
        return [SearchHit(1, "<script>Bad & Title", "safe excerpt", "u")]

    def get_article(self, pageid):
        return None

    def count(self, game_id=None):
        return 1


def test_search_escapes_title_in_result_label():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), [], StubRepo(), ":memory:")
    w._on_search("title")
    label = w.guides_results.itemWidget(w.guides_results.item(0))
    text = label.text()
    assert "<script>" not in text          # raw tag must not survive
    assert "&lt;script&gt;" in text         # escaped instead
    assert "&amp;" in text                  # & escaped too


def test_progress_shows_catching_up_when_count_stalls():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), [], StubRepo(), ":memory:")
    w._on_ingest_progress(1280, 16693)            # first update -> normal
    assert w.guides_status.text() == "1,280/16,693"
    w._on_ingest_progress(1280, 16693)            # count stalled -> catching up
    assert "catching up" in w.guides_status.text().lower()
    w._on_ingest_progress(1281, 16693)            # advancing again -> normal
    assert "catching up" not in w.guides_status.text().lower()
    assert "1,281" in w.guides_status.text()
