from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.chat import ChatRepo
from meister_guide.db.articles import ArticlesRepo


class OkClient:
    def list_models(self):
        return ["llama3"]

    def list_model_info(self):
        return [{"name": "llama3", "details": {"parameter_size": "8.0B"},
                 "capabilities": ["completion"]}]

    def chat(self, model, messages):
        return iter(())   # stream nothing so the worker finishes immediately


def _window(tmp_path):
    conn = connect(tmp_path / "w.db")
    init_db(conn)
    arts = ArticlesRepo(conn)
    arts.add_article(1, "Creeper", "A creeper is a hostile mob that explodes.", 1, "u")
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T"), [], arts, ":memory:",
                      chat, OkClient())
    return w, chat


def test_streaming_handlers_render_and_persist(tmp_path):
    w, chat = _window(tmp_path)
    w._begin_exchange("How do creepers work?", [(1, "Creeper")])
    w._on_chat_token("Creepers ")
    w._on_chat_token("explode.")
    w._on_chat_finished("Creepers explode.")

    html = w.chat_view.toHtml()
    assert "How do creepers work?" in html
    assert "Creepers explode." in html
    assert 'guide:1' in html
    sessions = chat.list_sessions()
    assert sessions
    msgs = chat.get_messages(sessions[0].id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "How do creepers work?"),
        ("assistant", "Creepers explode."),
    ]


def test_error_shows_message_and_persists_partial(tmp_path):
    w, chat = _window(tmp_path)
    w._begin_exchange("hi", [])
    w._on_chat_token("partial")
    w._on_chat_error("stream broke")
    html = w.chat_view.toHtml()
    assert "stream broke" in html
    msgs = chat.get_messages(chat.list_sessions()[0].id)
    assert msgs[-1].role == "assistant"


def test_cancelled_stream_does_not_persist_truncated_answer(tmp_path):
    w, chat = _window(tmp_path)
    w._begin_exchange("how do creepers work?", [])
    w._on_chat_token("Creepers ex")
    w._chat_cancelled = True          # e.g. overlay hidden mid-stream
    w._on_chat_finished("Creepers ex")  # worker emits the partial text
    msgs = chat.get_messages(chat.list_sessions()[0].id)
    # user turn kept; truncated assistant reply not saved as a complete answer
    assert [(m.role, m.content) for m in msgs] == [("user", "how do creepers work?")]


def test_new_chat_does_not_create_empty_session(tmp_path):
    w, chat = _window(tmp_path)
    w._on_new_chat()
    assert chat.list_sessions() == []          # nothing persisted until a message
    w._begin_exchange("first question", [])
    assert len(chat.list_sessions()) == 1      # session created lazily on send


def test_send_uses_ranked_retrieval(tmp_path, monkeypatch):
    w, chat = _window(tmp_path)
    calls = {}
    real = w._articles_repo.search_ranked
    def spy(q, limit=3, game_id=None):
        calls["q"] = q
        return real(q, limit=limit, game_id=game_id)
    monkeypatch.setattr(w._articles_repo, "search_ranked", spy)
    w.chat_input.setText("how do creepers work?")
    w._on_send()
    assert calls.get("q") == "how do creepers work?"
    w._teardown_chat_thread()   # stop the worker thread started by _on_send


from meister_guide.db.games import Game


def _window_with_wiki_game(tmp_path, with_article=False):
    conn = connect(tmp_path / "wg.db")
    init_db(conn)
    # Seed the games DB row so FK constraint is satisfied when game_id=7 is used
    conn.execute("INSERT INTO games (id, name, process_names, wiki_url) VALUES (7, 'Subnautica', '[]', 'https://subnautica.fandom.com')")
    conn.commit()
    arts = ArticlesRepo(conn)
    game = Game(7, "Subnautica", [], "https://subnautica.fandom.com")
    if with_article:
        arts.add_article(1, "Peeper", "A peeper is a common fish.", 1, "u",
                         game_id=7)
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    w = OverlayWindow(QSettings("MeisterGuide", "T2"), [game], arts, ":memory:",
                      chat, OkClient())
    w.active_game = game
    return w, chat


def test_send_miss_triggers_fetch_not_chat(tmp_path, monkeypatch):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    started = {}
    monkeypatch.setattr(w, "_start_fetch",
                        lambda q, h, wiki: started.update(q=q, wiki=wiki, h=h))
    w.chat_input.setText("where do peepers live?")
    w._on_send()
    assert started.get("q") == "where do peepers live?"
    assert started["wiki"][0] == "https://subnautica.fandom.com/api.php"
    assert started["h"] == []          # history captured before any turn appended
    assert w._chat_thread is None      # we answer AFTER the fetch, not now


def test_send_hit_skips_fetch(tmp_path, monkeypatch):
    w, chat = _window_with_wiki_game(tmp_path, with_article=True)
    calls = []
    monkeypatch.setattr(w, "_start_fetch", lambda *a: calls.append(a))
    w.chat_input.setText("peeper")
    w._on_send()
    assert calls == []                 # local hit -> no wiki fetch
    w._teardown_chat_thread()          # stop the chat worker started on the hit


def test_no_wiki_game_skips_fetch(tmp_path, monkeypatch):
    # Game without a wiki_url -> miss path is skipped, answer as today.
    conn = connect(tmp_path / "nw.db"); init_db(conn)
    arts = ArticlesRepo(conn)
    chat = ChatRepo(conn)
    QApplication.instance() or QApplication([])
    game = Game(8, "MysteryGame", [], None)
    w = OverlayWindow(QSettings("MeisterGuide", "T3"), [game], arts, ":memory:",
                      chat, OkClient())
    w.active_game = game
    calls = []
    monkeypatch.setattr(w, "_start_fetch", lambda *a: calls.append(a))
    w.chat_input.setText("anything")
    w._on_send()
    assert calls == []
    w._teardown_chat_thread()


def test_on_fetch_done_answers_from_fetched(tmp_path):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    # Simulate the worker having ingested the page while it ran off-thread.
    w._articles_repo.add_article(1, "Peeper", "A peeper is a fish.", 1, "u",
                                 game_id=7)
    w._begin_exchange("what is a peeper?", [])   # placeholder, empty sources
    w._on_fetch_done("what is a peeper?", history=[])
    # the placeholder assistant turn now carries the freshly-fetched source
    assert w._chat_view[-1]["sources"] == [(1, "Peeper")]
    w._teardown_chat_thread()


def test_on_fetch_done_cancelled_does_not_start_chat(tmp_path):
    w, chat = _window_with_wiki_game(tmp_path, with_article=False)
    w._begin_exchange("q", [])
    w._chat_cancelled = True            # overlay hidden mid-fetch
    w._on_fetch_done("q", history=[])
    assert w._chat_thread is None       # no answer started after cancellation
