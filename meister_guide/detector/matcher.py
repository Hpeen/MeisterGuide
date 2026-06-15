"""Pure logic: pick the active game from the running processes.

A game's process spec is either a plain executable name ("Terraria.exe") or a
name with a required command-line keyword ("javaw.exe::minecraft"). The keyword
form only counts the process as a match when that keyword appears in its command
line, which disambiguates generic runtimes like javaw.exe that many unrelated
programs share. Launcher executables that linger in the background (e.g. the
Minecraft launcher) are simply left out of a game's process list so they never
read as "playing".
"""


def parse_process_spec(spec):
    """Split a process spec into (exe_name, keyword_or_None).

    'javaw.exe::minecraft' -> ('javaw.exe', 'minecraft')
    'Terraria.exe'         -> ('Terraria.exe', None)
    """
    name, sep, keyword = spec.partition("::")
    keyword = keyword.strip()
    return name.strip(), (keyword if sep and keyword else None)


def match_running_game(processes, games):
    """Return the first Game with a currently-running matching process, else None.

    processes: iterable of (name, cmdline) pairs. cmdline may be '' or None.
    games: list of Game.
    """
    proc_list = [(name.lower(), (cmdline or "").lower()) for name, cmdline in processes]
    for game in games:
        for spec in game.process_names:
            exe, keyword = parse_process_spec(spec)
            exe = exe.lower()
            kw = keyword.lower() if keyword else None
            for pname, pcmd in proc_list:
                if pname == exe and (kw is None or kw in pcmd):
                    return game
    return None
