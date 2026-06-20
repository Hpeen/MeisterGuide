from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    return SettingsRepo(conn)


def test_brave_api_key_defaults_empty(tmp_path):
    assert _repo(tmp_path).brave_api_key() == ""


def test_web_fallback_on_by_default(tmp_path):
    # On out of the box — the free DuckDuckGo path needs no key.
    assert _repo(tmp_path).web_fallback_enabled() is True


def test_web_fallback_enabled_without_key(tmp_path):
    repo = _repo(tmp_path)
    assert repo.brave_api_key() == ""
    assert repo.web_fallback_enabled() is True


def test_web_fallback_paused_when_pref_zero(tmp_path):
    repo = _repo(tmp_path)
    repo.set("web_fallback", "0")
    assert repo.web_fallback_enabled() is False


def test_web_fallback_enabled_with_key(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    assert repo.web_fallback_enabled() is True
