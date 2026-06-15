from meister_guide.detector.matcher import match_running_game
from meister_guide.db.games import Game

MINECRAFT = Game(1, "Minecraft", ["javaw.exe", "Minecraft.exe"], "https://minecraft.wiki")
TERRARIA = Game(2, "Terraria", ["Terraria.exe"], None)
GAMES = [MINECRAFT, TERRARIA]


def test_matches_by_process_name_case_insensitive():
    assert match_running_game(["chrome.exe", "JAVAW.EXE"], GAMES) is MINECRAFT


def test_returns_none_when_no_match():
    assert match_running_game(["chrome.exe", "explorer.exe"], GAMES) is None


def test_returns_first_listed_game_on_match():
    assert match_running_game(["Terraria.exe"], GAMES) is TERRARIA


def test_empty_running_list_returns_none():
    assert match_running_game([], GAMES) is None
