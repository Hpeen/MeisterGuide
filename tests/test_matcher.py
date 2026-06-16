from meister_guide.detector.matcher import match_running_game, parse_process_spec
from meister_guide.db.games import Game

# Minecraft now matches the actual game, not the lingering launcher:
#   - Bedrock: Minecraft.Windows.exe
#   - Java: javaw.exe, but only when its command line mentions 'minecraft'
MINECRAFT = Game(
    1, "Minecraft", ["Minecraft.Windows.exe", "javaw.exe::minecraft"],
    "https://minecraft.wiki",
)
TERRARIA = Game(2, "Terraria", ["Terraria.exe"], None)
GAMES = [MINECRAFT, TERRARIA]


def test_parse_plain_and_keyword_specs():
    assert parse_process_spec("Terraria.exe") == ("Terraria.exe", None)
    assert parse_process_spec("javaw.exe::minecraft") == ("javaw.exe", "minecraft")


def test_bedrock_process_matches_by_name():
    assert match_running_game([("Minecraft.Windows.exe", "")], GAMES) is MINECRAFT


def test_java_in_game_matches_when_cmdline_has_keyword():
    procs = [("javaw.exe", "-cp libs net.minecraft.client.main.Main --gameDir .minecraft")]
    assert match_running_game(procs, GAMES) is MINECRAFT


def test_other_java_app_does_not_match():
    procs = [("javaw.exe", "-jar eclipse.jar -workspace foo")]
    assert match_running_game(procs, GAMES) is None


def test_launcher_process_does_not_count_as_playing():
    # Minecraft.exe is the launcher and is intentionally NOT a play signal.
    assert match_running_game([("Minecraft.exe", "")], GAMES) is None


def test_plain_name_game_still_matches_case_insensitive():
    assert match_running_game([("TERRARIA.EXE", "")], GAMES) is TERRARIA


def test_keyword_match_is_case_insensitive():
    assert match_running_game([("JavaW.exe", "Some MINECRAFT path")], GAMES) is MINECRAFT


def test_empty_process_list_returns_none():
    assert match_running_game([], GAMES) is None
