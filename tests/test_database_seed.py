from meister_guide.db.database import seed_db_if_missing


def test_seed_copies_when_target_absent(tmp_path):
    seed = tmp_path / "seed.db"
    seed.write_bytes(b"DBDATA")
    target = tmp_path / "out" / "meister.db"      # parent does not exist yet
    assert seed_db_if_missing(target, seed) is True
    assert target.read_bytes() == b"DBDATA"


def test_seed_noop_when_target_exists(tmp_path):
    seed = tmp_path / "seed.db"
    seed.write_bytes(b"NEW")
    target = tmp_path / "meister.db"
    target.write_bytes(b"OLD")
    assert seed_db_if_missing(target, seed) is False
    assert target.read_bytes() == b"OLD"          # never overwrites a user DB


def test_seed_noop_when_seed_absent(tmp_path):
    target = tmp_path / "meister.db"
    assert seed_db_if_missing(target, tmp_path / "missing.db") is False
    assert not target.exists()
