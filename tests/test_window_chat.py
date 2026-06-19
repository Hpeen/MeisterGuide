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
