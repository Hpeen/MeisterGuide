from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import (
    SettingsRepo, BACKEND_OLLAMA, BACKEND_CLAUDE, BACKEND_AUTO,
)


def _repo(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    return SettingsRepo(conn)


def test_defaults_when_unset(tmp_path):
    repo = _repo(tmp_path)
    assert repo.chat_backend() == BACKEND_AUTO   # online-first, local fallback
    assert repo.claude_api_key() == ""
    assert repo.claude_model() == "claude-opus-4-8"


def test_set_and_get_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    repo.set("chat_backend", BACKEND_CLAUDE)
    repo.set("claude_api_key", "sk-test-123")
    assert repo.chat_backend() == BACKEND_CLAUDE
    assert repo.claude_api_key() == "sk-test-123"


def test_set_overwrites_existing(tmp_path):
    repo = _repo(tmp_path)
    repo.set("claude_model", "claude-haiku-4-5")
    repo.set("claude_model", "claude-sonnet-4-6")
    assert repo.claude_model() == "claude-sonnet-4-6"


def test_unknown_key_returns_explicit_default(tmp_path):
    repo = _repo(tmp_path)
    assert repo.get("nope", "fallback") == "fallback"


def test_none_value_stored_as_empty_string(tmp_path):
    repo = _repo(tmp_path)
    repo.set("claude_api_key", None)
    assert repo.claude_api_key() == ""


def test_dock_edge_default_is_right(tmp_path):
    repo = _repo(tmp_path)
    assert repo.get("dock_edge") == "right"
