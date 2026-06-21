from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.articles import SearchHit
from meister_guide.db.games import Game


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


def _two_games():
    return [Game(id=1, name="Minecraft", process_names=[], wiki_url="https://minecraft.wiki"),
            Game(id=2, name="Subnautica", process_names=[], wiki_url="https://subnautica.fandom.com")]


def test_guides_picker_lists_all_games():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(), ":memory:")
    names = [w.guides_game.itemText(i) for i in range(w.guides_game.count())]
    assert names == ["Minecraft", "Subnautica"]


def test_picker_drives_update_target_not_detection():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(),
                      ":memory:")
    started = []
    w._start_ingest = lambda game: started.append(game)
    # Pick Subnautica in the Wiki tab regardless of the detected/active game.
    w.guides_game.setCurrentIndex(w.guides_game.findText("Subnautica"))
    w._on_update_guides()
    # Subnautica has a wiki URL, so _start_ingest is called for it (not Minecraft)
    assert len(started) == 1 and started[0].name == "Subnautica"


def test_active_game_change_syncs_the_picker():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(), ":memory:")
    w._on_manual_pick_game(2)              # detection/manual switch to Subnautica
    assert w.guides_game.currentData() == 2


def test_update_starts_for_any_game_with_wiki_url():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(),
                      ":memory:")
    started = []
    w._start_ingest = lambda game: started.append(game)
    w.guides_game.setCurrentIndex(w.guides_game.findText("Subnautica"))
    w._on_update_guides()
    assert len(started) == 1 and started[0].name == "Subnautica"


def test_update_refuses_game_without_wiki_url():
    QApplication.instance() or QApplication([])
    games = [Game(id=1, name="Minecraft", process_names=[], wiki_url="https://minecraft.wiki"),
             Game(id=3, name="NoWiki", process_names=[], wiki_url=None)]
    w = OverlayWindow(QSettings("MeisterGuide", "T"), games, StubRepo(), ":memory:")
    started = []
    w._start_ingest = lambda game: started.append(game)
    w.guides_game.setCurrentIndex(w.guides_game.findText("NoWiki"))
    w._on_update_guides()
    assert started == []
    assert "wiki URL" in w.guides_status.text()


def test_counted_handler_shows_estimate():
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), _two_games(), StubRepo(),
                      ":memory:")
    w.guides_game.setCurrentIndex(w.guides_game.findText("Subnautica"))
    w._on_ingest_counted(6200)
    assert "6,200 pages" in w.guides_status.text()
    assert "Subnautica" in w.guides_status.text()
    w._on_ingest_counted(140000)
    assert "while" in w.guides_status.text().lower()
