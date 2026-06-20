from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo
from meister_guide.db.settings import SettingsRepo


class OllamaStub:
    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]
    def chat(self, model, messages):
        return iter(())


def _window(tmp_path):
    db = tmp_path / "w.db"
    conn = connect(db)
    init_db(conn)
    QApplication.instance() or QApplication([])
    games = GamesRepo(conn)
    nowiki = games.add("NoWiki", [], None)
    withwiki = games.add("Subnautica", [], "https://subnautica.fandom.com")
    w = OverlayWindow(QSettings("MeisterGuide", "Seed"),
                      games.list_games(), ArticlesRepo(conn), str(db), None,
                      OllamaStub(), settings_repo=SettingsRepo(conn),
                      games_repo=games)
    return w, nowiki, withwiki


def test_seed_combo_lists_games(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    labels = [w.seed_game.itemText(i) for i in range(w.seed_game.count())]
    assert "Subnautica" in labels and "NoWiki" in labels


def test_seed_without_wiki_url_shows_message_and_starts_no_thread(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_game.setCurrentIndex(w.seed_game.findData(nowiki.id))
    w.seed_category.setText("Mobs")
    w._on_seed_category()
    assert w._seed_thread is None
    assert "wiki" in w.seed_status.text().lower()


def test_seed_with_blank_category_does_nothing(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_game.setCurrentIndex(w.seed_game.findData(withwiki.id))
    w.seed_category.setText("   ")
    w._on_seed_category()
    assert w._seed_thread is None


def test_seed_progress_handler_updates_bar(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w._on_seed_progress(3, 10)
    assert w.seed_progress.maximum() == 10
    assert w.seed_progress.value() == 3


def test_seed_done_handler_reports_count_and_resets(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w.seed_btn.setEnabled(False)
    w.seed_progress.setVisible(True)
    w._on_seed_done(5)
    assert "5" in w.seed_status.text()
    assert w.seed_btn.isEnabled()
    assert not w.seed_progress.isVisible()


def test_seed_done_zero_count_shows_no_guides_message(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w._on_seed_done(0)
    assert "No new guides" in w.seed_status.text()


def test_seed_error_handler_shows_truncated_error(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    w._on_seed_error("Boom happened\nsecond line")
    assert "Boom happened" in w.seed_status.text()
    assert "second line" not in w.seed_status.text()
    assert w.seed_btn.isEnabled()


def test_shutdown_cancels_active_seed_worker(tmp_path):
    w, nowiki, withwiki = _window(tmp_path)
    class FakeWorker:
        def __init__(self): self.cancelled = False
        def cancel(self): self.cancelled = True
    fw = FakeWorker()
    w._seed_worker = fw
    w.shutdown()
    assert fw.cancelled
