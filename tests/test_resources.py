import sys
from pathlib import Path
from meister_guide.resources import resource_path


def test_resource_path_dev_uses_repo_root():
    # In dev (no sys._MEIPASS) the path resolves under the repo root, where the
    # meister_guide package and assets/ both live.
    p = resource_path("assets/fonts")
    assert p.name == "fonts"
    assert p.parent.name == "assets"
    assert (p.parent.parent / "meister_guide").is_dir()


def test_resource_path_frozen_uses_meipass(monkeypatch, tmp_path):
    # When frozen, PyInstaller sets sys._MEIPASS to the unpack dir; bundled
    # resources live under it at their declared relative paths.
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("seed/meister.db") == Path(tmp_path) / "seed" / "meister.db"
