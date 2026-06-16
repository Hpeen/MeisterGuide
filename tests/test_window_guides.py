from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.articles import SearchHit


class StubRepo:
    def search(self, text, limit=50):
        return [SearchHit(1, "<script>Bad & Title", "safe excerpt", "u")]

    def get_article(self, pageid):
        return None

    def count(self):
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
