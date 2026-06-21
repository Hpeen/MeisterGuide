"""Games table access: the Game model, CRUD, and the Minecraft seed."""
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class Game:
    id: int
    name: str
    process_names: list  # list[str]
    wiki_url: Optional[str]


_MINECRAFT = {
    "name": "Minecraft",
    # The actual game, not the launcher. Bedrock is Minecraft.Windows.exe;
    # Java runs as javaw.exe, qualified by a 'minecraft' command-line keyword so
    # other Java apps don't false-trigger. The launcher (Minecraft.exe /
    # MinecraftLauncher.exe) is deliberately excluded because it lingers in the
    # background after its window is closed.
    "process_names": ["Minecraft.Windows.exe", "javaw.exe::minecraft"],
    "wiki_url": "https://minecraft.wiki",
}

# Built-in Minecraft process lists shipped by earlier versions. A Minecraft row
# still carrying one of these (i.e. untouched by the user) is auto-upgraded to
# the current list by reconcile_builtin_games().
_STALE_MINECRAFT_PROCESS_LISTS = [
    ["javaw.exe", "Minecraft.exe", "MinecraftLauncher.exe"],
]

def api_url_for(wiki_url):
    """Derive a MediaWiki action-API endpoint from a wiki URL. Normalizes a pasted
    page URL to its base first (e.g. .../wiki/Subnautica_Wiki -> host), so the
    endpoint is <base>/api.php. Works for minecraft.wiki and Fandom wikis. Returns
    None when no wiki_url is set."""
    if not wiki_url:
        return None
    from meister_guide.scraper.urls import wiki_base
    return wiki_base(wiki_url) + "/api.php"


_SELECT = "SELECT id, name, process_names, wiki_url FROM games"


class GamesRepo:
    def __init__(self, conn):
        self._conn = conn

    @staticmethod
    def _row_to_game(row) -> Game:
        return Game(row[0], row[1], json.loads(row[2]), row[3])

    def list_games(self):
        cur = self._conn.execute(_SELECT + " ORDER BY name")
        return [self._row_to_game(r) for r in cur.fetchall()]

    def get(self, game_id):
        cur = self._conn.execute(_SELECT + " WHERE id = ?", (game_id,))
        row = cur.fetchone()
        return self._row_to_game(row) if row else None

    def add(self, name, process_names, wiki_url) -> Game:
        cur = self._conn.execute(
            "INSERT INTO games (name, process_names, wiki_url) VALUES (?, ?, ?)",
            (name, json.dumps(process_names), wiki_url),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)

    def update(self, game_id, name, process_names, wiki_url) -> None:
        self._conn.execute(
            "UPDATE games SET name = ?, process_names = ?, wiki_url = ? WHERE id = ?",
            (name, json.dumps(process_names), wiki_url, game_id),
        )
        self._conn.commit()

    def delete(self, game_id) -> None:
        self._conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        self._conn.commit()

    def seed_defaults(self) -> None:
        """Insert Minecraft only if the games table is empty."""
        if self._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0:
            self.add(
                _MINECRAFT["name"],
                _MINECRAFT["process_names"],
                _MINECRAFT["wiki_url"],
            )

    def reconcile_builtin_games(self) -> None:
        """Upgrade a stale built-in Minecraft entry to the current process list.

        Only a Minecraft row whose process list exactly matches a known old
        default is touched, so any user edits are preserved.
        """
        for game in self.list_games():
            if (game.name == "Minecraft"
                    and game.process_names in _STALE_MINECRAFT_PROCESS_LISTS):
                self.update(
                    game.id,
                    game.name,
                    _MINECRAFT["process_names"],
                    game.wiki_url,
                )
