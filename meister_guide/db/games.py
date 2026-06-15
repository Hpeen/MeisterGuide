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
    "process_names": ["javaw.exe", "Minecraft.exe", "MinecraftLauncher.exe"],
    "wiki_url": "https://minecraft.wiki",
}

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
