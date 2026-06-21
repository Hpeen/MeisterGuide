from meister_guide.db.database import connect, init_db
from meister_guide.db.games import GamesRepo, Game


def _repo(tmp_path):
    conn = connect(tmp_path / "g.db")
    init_db(conn)
    return GamesRepo(conn)


def test_seed_adds_minecraft_once(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_defaults()
    repo.seed_defaults()  # second call must be a no-op
    games = repo.list_games()
    assert len(games) == 1
    mc = games[0]
    assert mc.name == "Minecraft"
    assert mc.process_names == ["Minecraft.Windows.exe", "javaw.exe::minecraft"]
    assert mc.wiki_url == "https://minecraft.wiki"


def test_reconcile_upgrades_stale_minecraft(tmp_path):
    repo = _repo(tmp_path)
    old = repo.add(
        "Minecraft",
        ["javaw.exe", "Minecraft.exe", "MinecraftLauncher.exe"],
        "https://minecraft.wiki",
    )
    repo.reconcile_builtin_games()
    assert repo.get(old.id).process_names == [
        "Minecraft.Windows.exe", "javaw.exe::minecraft",
    ]


def test_reconcile_leaves_user_edited_minecraft_alone(tmp_path):
    repo = _repo(tmp_path)
    custom = repo.add("Minecraft", ["javaw.exe"], "https://minecraft.wiki")
    repo.reconcile_builtin_games()
    assert repo.get(custom.id).process_names == ["javaw.exe"]


def test_add_get_update_delete(tmp_path):
    repo = _repo(tmp_path)
    g = repo.add("Terraria", ["Terraria.exe"], "https://terraria.wiki.gg")
    assert isinstance(g, Game)
    assert repo.get(g.id).name == "Terraria"

    repo.update(g.id, "Terraria", ["Terraria.exe", "tModLoader.exe"], "https://terraria.wiki.gg")
    assert "tModLoader.exe" in repo.get(g.id).process_names

    repo.delete(g.id)
    assert repo.get(g.id) is None


def test_process_names_roundtrip_as_list(tmp_path):
    repo = _repo(tmp_path)
    g = repo.add("X", ["a.exe", "b.exe"], None)
    assert repo.get(g.id).process_names == ["a.exe", "b.exe"]


def test_api_url_for_derives_mediawiki_endpoint():
    from meister_guide.db.games import api_url_for
    assert api_url_for("https://minecraft.wiki") == "https://minecraft.wiki/api.php"
    assert api_url_for("https://subnautica.fandom.com/") == "https://subnautica.fandom.com/api.php"
    assert api_url_for(None) is None


def test_api_url_for_normalizes_a_pasted_page_url():
    # Users paste a wiki page URL, not the bare base; the API endpoint must still
    # resolve to <host>/api.php, not <host>/wiki/Page/api.php.
    from meister_guide.db.games import api_url_for
    assert api_url_for("https://subnautica.fandom.com/wiki/Subnautica_Wiki") == \
        "https://subnautica.fandom.com/api.php"
    assert api_url_for("https://minecraft.wiki/w/Creeper") == \
        "https://minecraft.wiki/api.php"
