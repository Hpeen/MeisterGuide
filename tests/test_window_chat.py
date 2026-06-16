from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from meister_guide.overlay.window import OverlayWindow
from meister_guide.db.database import connect, init_db
from meister_guide.db.chat import ChatRepo
from meister_guide.db.articles import ArticlesRepo


class OkClient:
    def list_models(self):
        return ["llama3"]


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
