"""Pure logic: pick the active game from a list of running process names."""


def match_running_game(running_names, games):
    """Return the first Game whose any process name is currently running.

    running_names: iterable of process executable names (any case).
    games: list of Game. Returns the matching Game, or None.
    """
    running = {n.lower() for n in running_names}
    for game in games:
        for proc_name in game.process_names:
            if proc_name.lower() in running:
                return game
    return None
