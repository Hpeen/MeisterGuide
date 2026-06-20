from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo
from meister_guide.db.articles import ArticlesRepo, ScrapeStateRepo, ScrapeState
from meister_guide.db.redirects import RedirectsRepo, RedirectStateRepo
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
    games.seed_defaults()                      # Minecraft (id 1)
    sub = games.add("Subnautica", [], "https://subnautica.fandom.com")
    articles = ArticlesRepo(conn)
    mc = next(g for g in games.list_games() if g.name == "Minecraft")
    articles.add_article(1, "Creeper", "boom", 1, "u", game_id=mc.id)
    articles.add_article(2, "Leviathan", "big", 2, "u", game_id=sub.id)
    redirects = RedirectsRepo(conn)
    redirects.add_redirect("Reaper", 2, game_id=sub.id)
    w = OverlayWindow(QSettings("MeisterGuide", "Manage"),
                      games.list_games(), articles, str(db), None, OllamaStub(),
                      settings_repo=SettingsRepo(conn),
                      scrape_state_repo=ScrapeStateRepo(conn),
                      redirect_state_repo=RedirectStateRepo(conn),
                      games_repo=games, redirects_repo=redirects)
    return w, games, articles, mc, sub


def _pick(w, game_id):
    w.manage_game.setCurrentIndex(w.manage_game.findData(game_id))


def test_combo_lists_games_and_shows_count(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    assert "1 guides" in w.manage_count.text()
    assert "1 aliases" in w.manage_count.text()


def test_remove_disabled_for_minecraft_enabled_otherwise(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, mc.id)
    assert not w.manage_remove_btn.isEnabled()
    _pick(w, sub.id)
    assert w.manage_remove_btn.isEnabled()


def test_clear_deletes_guides(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    w._confirm = lambda *a: True
    w._on_clear_guides()
    assert articles.count(game_id=sub.id) == 0
    assert "Cleared 1 guides" in w.manage_status.text()


def test_clear_cancelled_keeps_guides(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, sub.id)
    w._confirm = lambda *a: False
    w._on_clear_guides()
    assert articles.count(game_id=sub.id) == 1


def test_clear_minecraft_resets_scrape_state(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    w._scrape_state_repo.save(ScrapeState("token", 17915, 16689))
    _pick(w, mc.id)
    w._confirm = lambda *a: True
    w._on_clear_guides()
    st = w._scrape_state_repo.load()
    assert st.continue_token is None and st.done == 0


def test_remove_game_deletes_and_resets_active(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    w._set_active(next(g for g in w._games if g.id == sub.id), manual=True)
    _pick(w, sub.id)
    w._confirm = lambda *a: True
    w._on_remove_game()
    assert all(g.id != sub.id for g in games.list_games())   # game row gone
    assert articles.count(game_id=sub.id) == 0               # guides gone
    assert w.active_game is None                              # active reset


def test_remove_minecraft_is_noop(tmp_path):
    w, games, articles, mc, sub = _window(tmp_path)
    _pick(w, mc.id)
    w._confirm = lambda *a: True
    w._on_remove_game()
    assert any(g.id == mc.id for g in games.list_games())     # still there
