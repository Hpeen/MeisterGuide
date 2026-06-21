import sqlite3
from meister_guide.db.database import connect, init_db, migrate_game_ids
from meister_guide.db.articles import ScrapeStateRepo, ScrapeState
from meister_guide.db.redirects import RedirectStateRepo, RedirectState


def test_scrape_state_is_per_game(tmp_path):
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    repo = ScrapeStateRepo(conn)
    repo.save(ScrapeState("tokA", 5, 100), game_id=1)
    repo.save(ScrapeState("tokB", 7, 200), game_id=2)
    assert repo.load(1) == ScrapeState("tokA", 5, 100)
    assert repo.load(2) == ScrapeState("tokB", 7, 200)
    assert repo.load(999) == ScrapeState(None, 0, None)


def test_redirect_state_is_per_game(tmp_path):
    conn = connect(tmp_path / "r.db")
    init_db(conn)
    repo = RedirectStateRepo(conn)
    repo.save(RedirectState("tokA", 3), game_id=1)
    repo.save(RedirectState("tokB", 9), game_id=2)
    assert repo.load(1) == RedirectState("tokA", 3)
    assert repo.load(2) == RedirectState("tokB", 9)
    assert repo.load(7) == RedirectState(None, 0)


def _legacy_state_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, "
                 "process_names TEXT, wiki_url TEXT)")
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (1,'Minecraft','[]')")
    conn.execute("CREATE TABLE scrape_state (id INTEGER PRIMARY KEY CHECK (id=1), "
                 "continue_token TEXT, done INTEGER NOT NULL DEFAULT 0, total INTEGER, "
                 "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO scrape_state (id, continue_token, done, total) "
                 "VALUES (1, 'RESUME', 9000, 16000)")
    conn.execute("CREATE TABLE redirect_state (id INTEGER PRIMARY KEY CHECK (id=1), "
                 "continue_token TEXT, done INTEGER NOT NULL DEFAULT 0, "
                 "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO redirect_state (id, continue_token, done) VALUES (1, 'RTOK', 12)")
    conn.commit()
    return conn


def test_migration_moves_legacy_state_to_minecraft(tmp_path):
    db = tmp_path / "legacy.db"
    conn = _legacy_state_db(db)
    migrate_game_ids(conn)
    assert ScrapeStateRepo(conn).load(1) == ScrapeState("RESUME", 9000, 16000)
    assert RedirectStateRepo(conn).load(1) == RedirectState("RTOK", 12)
    ScrapeStateRepo(conn).save(ScrapeState("X", 1, 2), game_id=2)
    assert ScrapeStateRepo(conn).load(2) == ScrapeState("X", 1, 2)


def test_migration_is_idempotent(tmp_path):
    conn = _legacy_state_db(tmp_path / "legacy2.db")
    migrate_game_ids(conn)
    migrate_game_ids(conn)
    assert ScrapeStateRepo(conn).load(1) == ScrapeState("RESUME", 9000, 16000)


def test_migration_tolerates_missing_redirect_state(tmp_path):
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "partial.db"))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, "
                 "process_names TEXT, wiki_url TEXT)")
    conn.execute("INSERT INTO games (id, name, process_names) VALUES (1,'Minecraft','[]')")
    conn.execute("CREATE TABLE scrape_state (id INTEGER PRIMARY KEY CHECK (id=1), "
                 "continue_token TEXT, done INTEGER NOT NULL DEFAULT 0, total INTEGER, "
                 "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO scrape_state (id, continue_token, done, total) "
                 "VALUES (1, 'TOK', 100, 200)")
    conn.commit()
    migrate_game_ids(conn)              # must not raise despite no redirect_state table
    assert ScrapeStateRepo(conn).load(1) == ScrapeState("TOK", 100, 200)
