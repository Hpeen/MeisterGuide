from meister_guide.detector.detector import GameDetector
from meister_guide.db.games import Game

MINECRAFT = Game(1, "Minecraft", ["javaw.exe"], None)


def test_poll_emits_game_then_none_on_change():
    running = {"names": ["javaw.exe"]}
    detector = GameDetector(
        games_provider=lambda: [MINECRAFT],
        process_lister=lambda: running["names"],
    )
    seen = []
    detector.detected.connect(seen.append)

    detector.poll()                 # match -> emit Minecraft
    running["names"] = ["chrome.exe"]
    detector.poll()                 # no match -> emit None

    assert seen == [MINECRAFT, None]


def test_poll_does_not_re_emit_same_state():
    detector = GameDetector(
        games_provider=lambda: [MINECRAFT],
        process_lister=lambda: ["javaw.exe"],
    )
    seen = []
    detector.detected.connect(seen.append)

    detector.poll()
    detector.poll()  # same match -> must NOT emit again

    assert seen == [MINECRAFT]
