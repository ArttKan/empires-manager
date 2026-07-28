import json
import tempfile
import unittest
from pathlib import Path

from mega_empires.models import GameState, PlayerState
from mega_empires.storage import load_game, save_game


class StorageTests(unittest.TestCase):
    def test_game_round_trip_preserves_finnish_nickname(self) -> None:
        game = GameState(
            player_count=1,
            players=[
                PlayerState(
                    civilization="Hatti",
                    nickname="Väinö",
                    block="EAST",
                    cities=4,
                    ast_step=6,
                    advances=["music"],
                    census=31,
                    flexible_credits={"ART": 10, "SCIENCE": 5},
                )
            ],
            game_mode="EAST",
            round_number=4,
            current_phase=10,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "peli.json"
            save_game(game, path)
            loaded = load_game(path)
            self.assertEqual(loaded.players[0].nickname, "Väinö")
            self.assertEqual(loaded.players[0].display_name, "Hatti (Väinö)")
            self.assertEqual(loaded.players[0].cities, 4)
            self.assertEqual(loaded.players[0].advances, ["music"])
            self.assertEqual(loaded.players[0].flexible_credits["ART"], 10)
            self.assertEqual(loaded.players[0].flexible_credits["SCIENCE"], 5)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded.game_mode, "EAST")
            self.assertEqual(loaded.ast_variant, "BASIC")
            self.assertEqual(loaded.round_number, 4)
            self.assertEqual(loaded.current_phase, 10)
            self.assertEqual(raw["version"], 4)

    def test_version_one_save_is_migrated_without_losing_players(self) -> None:
        old_data = {
            "player_count": 16,
            "players": [
                {
                    "civilization": "Babylon",
                    "nickname": "B",
                    "block": "WEST",
                },
                {
                    "civilization": "Hatti",
                    "nickname": "H",
                    "block": "EAST",
                },
            ],
            "version": 1,
        }
        game = GameState.from_dict(old_data)
        self.assertEqual(game.version, 4)
        self.assertEqual(game.game_mode, "WEST")
        self.assertEqual(game.players[0].block, "EAST")
        self.assertEqual(game.players[1].block, "WEST")


if __name__ == "__main__":
    unittest.main()
