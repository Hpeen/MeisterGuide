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


def test_delete_session_removes_session_and_its_messages(tmp_path):
    repo = _repo(tmp_path)
    keep = repo.create_session(title="keep me")
    repo.add_message(keep, "user", "stays")
    doomed = repo.create_session(title="delete me")
    repo.add_message(doomed, "user", "q")
    repo.add_message(doomed, "assistant", "a")

    repo.delete_session(doomed)

    ids = {s.id for s in repo.list_sessions()}
    assert doomed not in ids                       # session gone
    assert keep in ids                             # other session untouched
    assert repo.get_messages(doomed) == []         # its messages gone
    assert len(repo.get_messages(keep)) == 1       # other messages intact


def test_delete_session_missing_id_is_noop(tmp_path):
    repo = _repo(tmp_path)
    s1 = repo.create_session()
    repo.delete_session(999999)                    # not an error
    assert {s.id for s in repo.list_sessions()} == {s1}
