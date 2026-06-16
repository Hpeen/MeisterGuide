from meister_guide.db.database import connect, init_db
from meister_guide.db.chat import ChatRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "c.db")
    init_db(conn)
    # seed a game row so FK constraint is satisfied when game_id=1 is used
    conn.execute(
        "INSERT INTO games (id, name, process_names) VALUES (1, 'Minecraft', '[]')"
    )
    conn.commit()
    return ChatRepo(conn)


def test_session_and_message_crud(tmp_path):
    repo = _repo(tmp_path)
    sid = repo.create_session(game_id=1, title=None)
    repo.add_message(sid, "user", "hi")
    repo.add_message(sid, "assistant", "hello")
    msgs = repo.get_messages(sid)
    assert [(m.role, m.content) for m in msgs] == [("user", "hi"), ("assistant", "hello")]


def test_set_title_and_list_newest_first(tmp_path):
    repo = _repo(tmp_path)
    s1 = repo.create_session()
    s2 = repo.create_session()
    repo.set_title(s1, "First chat")
    sessions = repo.list_sessions()
    assert sessions[0].id == s2            # newest first
    titles = {s.id: s.title for s in sessions}
    assert titles[s1] == "First chat"
