from meister_guide.db.database import connect, init_db
from meister_guide.db.settings import SettingsRepo


def _repo(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    return SettingsRepo(conn)


def test_brave_api_key_defaults_empty(tmp_path):
    assert _repo(tmp_path).brave_api_key() == ""


def test_web_fallback_disabled_without_key(tmp_path):
    repo = _repo(tmp_path)
    assert repo.web_fallback_enabled() is False


def test_web_fallback_enabled_when_key_set(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    assert repo.web_fallback_enabled() is True   # defaults on once a key exists


def test_web_fallback_can_be_paused_with_key_set(tmp_path):
    repo = _repo(tmp_path)
    repo.set("brave_api_key", "brv-123")
    repo.set("web_fallback", "0")
    assert repo.web_fallback_enabled() is False


def test_web_fallback_off_pref_without_key_still_false(tmp_path):
    repo = _repo(tmp_path)
    repo.set("web_fallback", "1")     # pref on but no key
    assert repo.web_fallback_enabled() is False
