import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mega_empires.models import GameState, PlayerState
from mega_empires.storage import (
    DATA_DIRECTORY_VARIABLE,
    REPO_SAVE_DIRECTORY,
    data_directory,
    default_save_path,
    list_saved_games,
    load_game,
    save_game,
    save_path_for_name,
)


class DataDirectoryTests(unittest.TestCase):
    def test_repo_directory_is_used_without_the_variable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(DATA_DIRECTORY_VARIABLE, None)
            self.assertEqual(data_directory(), REPO_SAVE_DIRECTORY)
            self.assertEqual(default_save_path().parent, REPO_SAVE_DIRECTORY)

    def test_environment_variable_overrides_the_repo_directory(self) -> None:
        with mock.patch.dict(
            os.environ,
            {DATA_DIRECTORY_VARIABLE: "/var/lib/mega-empires"},
        ):
            self.assertEqual(data_directory(), Path("/var/lib/mega-empires"))
            self.assertEqual(
                default_save_path(),
                Path("/var/lib/mega-empires/nykyinen_peli.json"),
            )

    def test_blank_variable_falls_back_to_the_repo_directory(self) -> None:
        with mock.patch.dict(os.environ, {DATA_DIRECTORY_VARIABLE: "   "}):
            self.assertEqual(data_directory(), REPO_SAVE_DIRECTORY)

    def test_named_saves_follow_the_configured_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ,
                {DATA_DIRECTORY_VARIABLE: directory},
            ):
                path = save_path_for_name("Sunday game")
                self.assertEqual(path.parent, Path(directory))


class StorageTests(unittest.TestCase):
    def test_named_save_path_and_listing(self) -> None:
        game = GameState(
            player_count=3,
            players=[
                PlayerState("Indus", "I", "EAST"),
                PlayerState("Kushan", "K", "EAST"),
                PlayerState("Parthia", "P", "EAST"),
            ],
            game_mode="EAST",
        )
        with tempfile.TemporaryDirectory() as directory:
            save_directory = Path(directory)
            path = save_path_for_name("Monday game", save_directory)
            save_game(game, path)
            saves = list_saved_games(save_directory)
            self.assertEqual(path.name, "Monday game.json")
            self.assertEqual(len(saves), 1)
            self.assertEqual(saves[0].name, "Monday game")
            self.assertEqual(saves[0].player_count, 3)

    def test_invalid_save_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_path_for_name("")
        with self.assertRaises(ValueError):
            save_path_for_name("bad/name")

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
            self.assertEqual(raw["version"], 5)

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
        self.assertEqual(game.version, 5)
        self.assertEqual(game.game_mode, "WEST")
        self.assertEqual(game.players[0].block, "EAST")
        self.assertEqual(game.players[1].block, "WEST")


class SaveFormatMigrationTests(unittest.TestCase):
    def test_version_four_save_gains_zero_version_counters(self) -> None:
        """Versiolaskurit puuttuvat vanhoista tallennuksista ja alkavat nollasta."""

        raw = {
            "version": 4,
            "player_count": 1,
            "players": [
                {
                    "civilization": "Hellas",
                    "nickname": "Matti",
                    "block": "WEST",
                    "cities": 4,
                }
            ],
            "game_mode": "WEST",
        }
        game = GameState.from_dict(raw)

        self.assertEqual(game.version, 5)
        self.assertEqual(game.state_version, 0)
        self.assertEqual(game.players[0].version, 0)
        self.assertEqual(game.players[0].cities, 4)

    def test_version_counters_survive_a_round_trip(self) -> None:
        game = GameState(
            player_count=1,
            players=[PlayerState("Hellas", "Matti", "WEST", version=7)],
            game_mode="WEST",
            state_version=42,
        )
        restored = GameState.from_dict(json.loads(json.dumps(game.to_dict())))

        self.assertEqual(restored.state_version, 42)
        self.assertEqual(restored.players[0].version, 7)


if __name__ == "__main__":
    unittest.main()
