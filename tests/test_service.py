import json
import tempfile
import unittest
from pathlib import Path

from src.core.models import GameState, PlayerState
from src.service import (
    LocalGameService,
    RuleViolation,
    UnknownPlayer,
    VersionConflict,
    validate_ast_bonus,
)


def _game(player_count: int = 3, mode: str = "WEST") -> GameState:
    names = {
        3: (("Minoa", "WEST"), ("Hatti", "WEST"), ("Hellas", "WEST")),
        12: tuple(
            (name, "WEST" if index % 2 else "EAST")
            for index, name in enumerate(
                (
                    "Minoa", "Saba", "Assyria", "Carthage", "Babylon", "Hatti",
                    "Rome", "Persia", "Nubia", "Hellas", "Egypt", "Parthia",
                )
            )
        ),
    }[player_count]
    return GameState(
        player_count=player_count,
        players=[
            PlayerState(name, name[0], block) for name, block in names
        ],
        game_mode=mode,
    )


class CommandTests(unittest.TestCase):
    def test_set_cities_bumps_both_version_counters(self) -> None:
        service = LocalGameService(_game())

        result = service.set_cities("Hellas", 5)

        self.assertEqual(result.player.cities, 5)
        self.assertEqual(result.player.version, 1)
        self.assertEqual(result.state_version, 1)
        self.assertEqual(service.snapshot().state_version, 1)

    def test_each_command_advances_the_global_version(self) -> None:
        service = LocalGameService(_game())

        service.set_cities("Hellas", 5)
        service.set_census("Minoa", 30)

        snapshot = service.snapshot()
        self.assertEqual(snapshot.state_version, 2)
        # Pelaajakohtaiset laskurit ovat toisistaan riippumattomia.
        self.assertEqual(
            [player.version for player in snapshot.players if player.version],
            [1, 1],
        )

    def test_stale_expected_version_is_rejected_without_mutating(self) -> None:
        service = LocalGameService(_game())
        service.set_cities("Hellas", 5)

        with self.assertRaises(VersionConflict) as caught:
            service.set_cities("Hellas", 9, expected_version=0)

        self.assertEqual(caught.exception.expected, 0)
        self.assertEqual(caught.exception.actual, 1)
        # Hylätty komento ei saa jättää jälkeä tilaan.
        snapshot = service.snapshot()
        self.assertEqual(snapshot.players[2].cities, 5)
        self.assertEqual(snapshot.state_version, 1)

    def test_current_expected_version_is_accepted(self) -> None:
        service = LocalGameService(_game())
        first = service.set_cities("Hellas", 5)

        second = service.set_cities(
            "Hellas", 6, expected_version=first.player.version
        )

        self.assertEqual(second.player.cities, 6)
        self.assertEqual(second.player.version, 2)

    def test_unknown_civilization_is_rejected(self) -> None:
        service = LocalGameService(_game())

        with self.assertRaises(UnknownPlayer):
            service.set_cities("Atlantis", 3)

    def test_values_are_clamped_by_normalize(self) -> None:
        service = LocalGameService(_game())

        self.assertEqual(service.set_cities("Hellas", 99).player.cities, 9)
        self.assertEqual(service.set_census("Hellas", -4).player.census, 0)

    def test_snapshot_is_a_copy_not_a_live_reference(self) -> None:
        """Etätoteutus ei voi palauttaa elävää oliota, joten paikallinenkaan ei saa."""

        service = LocalGameService(_game())
        snapshot = service.snapshot()

        snapshot.players[0].cities = 7

        self.assertEqual(service.snapshot().players[0].cities, 0)

    def test_returned_player_is_a_copy_not_a_live_reference(self) -> None:
        service = LocalGameService(_game())

        result = service.set_cities("Hellas", 5)
        result.player.cities = 7

        self.assertEqual(service.snapshot().players[2].cities, 5)


class AstBonusRuleTests(unittest.TestCase):
    def test_small_game_allows_only_one_recipient(self) -> None:
        service = LocalGameService(_game())
        service.set_ast_bonus("Hellas", True)

        with self.assertRaises(RuleViolation):
            service.set_ast_bonus("Minoa", True)

    def test_small_game_allows_regranting_the_same_player(self) -> None:
        service = LocalGameService(_game())
        service.set_ast_bonus("Hellas", True)

        result = service.set_ast_bonus("Hellas", True)

        self.assertTrue(result.player.ast_bonus)

    def test_combined_game_allows_two_in_different_blocks(self) -> None:
        game = _game(12, "BOTH")
        service = LocalGameService(game)
        service.set_ast_bonus("Minoa", True)  # EAST in this fixture

        result = service.set_ast_bonus("Saba", True)  # WEST

        self.assertTrue(result.player.ast_bonus)

    def test_combined_game_rejects_two_in_the_same_block(self) -> None:
        game = _game(12, "BOTH")
        service = LocalGameService(game)
        service.set_ast_bonus("Minoa", True)

        with self.assertRaises(RuleViolation):
            service.set_ast_bonus("Assyria", True)  # also EAST

    def test_combined_game_rejects_a_third_recipient(self) -> None:
        game = _game(12, "BOTH")
        service = LocalGameService(game)
        service.set_ast_bonus("Minoa", True)
        service.set_ast_bonus("Saba", True)

        with self.assertRaises(RuleViolation):
            service.set_ast_bonus("Carthage", True)

    def test_revoking_is_always_allowed(self) -> None:
        service = LocalGameService(_game())
        service.set_ast_bonus("Hellas", True)

        result = service.set_ast_bonus("Minoa", False)

        self.assertFalse(result.player.ast_bonus)

    def test_validation_is_reachable_without_a_service(self) -> None:
        game = _game()
        game.players[2].ast_bonus = True

        with self.assertRaises(RuleViolation):
            validate_ast_bonus(game, "Minoa", True)


class PersistenceTests(unittest.TestCase):
    def test_commands_write_snapshot_and_append_to_the_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "peli.json"
            service = LocalGameService(_game(), save_path=save_path)

            service.set_cities("Hellas", 5, actor="laptop")
            service.set_census("Hellas", 22, actor="phone:Hellas")

            saved = json.loads(save_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["state_version"], 2)

            log_path = save_path.with_suffix(".jsonl")
            entries = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["command"], "set_cities")
            self.assertEqual(entries[0]["actor"], "laptop")
            self.assertEqual(entries[0]["arguments"]["cities"], 5)
            self.assertEqual(entries[1]["actor"], "phone:Hellas")
            self.assertEqual(entries[1]["state_version"], 2)

    def test_rejected_commands_are_not_logged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "peli.json"
            service = LocalGameService(_game(), save_path=save_path)
            service.set_cities("Hellas", 5)

            with self.assertRaises(VersionConflict):
                service.set_cities("Hellas", 9, expected_version=0)

            log_path = save_path.with_suffix(".jsonl")
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

    def test_service_without_paths_keeps_state_in_memory_only(self) -> None:
        service = LocalGameService(_game())

        service.set_cities("Hellas", 4)

        self.assertEqual(service.snapshot().players[2].cities, 4)


class WiderCommandTests(unittest.TestCase):
    def test_set_ast_step_clamps_and_versions(self) -> None:
        service = LocalGameService(_game())

        self.assertEqual(service.set_ast_step("Hellas", 9).player.ast_step, 9)
        self.assertEqual(service.set_ast_step("Hellas", 99).player.ast_step, 15)

    def test_set_advances_replaces_the_whole_set(self) -> None:
        service = LocalGameService(_game())

        service.set_advances("Hellas", ["pottery", "masonry"])
        result = service.set_advances("Hellas", ["pottery"])

        self.assertEqual(result.player.advances, ["pottery"])

    def test_set_advances_dedupes_via_normalize(self) -> None:
        service = LocalGameService(_game())

        result = service.set_advances("Hellas", ["pottery", "pottery"])

        self.assertEqual(result.player.advances, ["pottery"])

    def test_set_advances_can_carry_flexible_credits(self) -> None:
        service = LocalGameService(_game())

        result = service.set_advances(
            "Hellas", ["written_record"], {"ART": 10}
        )

        self.assertEqual(result.player.flexible_credits["ART"], 10)

    def test_set_player_details_is_one_command_one_version(self) -> None:
        service = LocalGameService(_game())

        result = service.set_player_details(
            "Hellas",
            nickname="Matti",
            block="WEST",
            cities=6,
            ast_step=11,
            census=40,
            ast_bonus=False,
        )

        self.assertEqual(result.player.nickname, "Matti")
        self.assertEqual(result.player.cities, 6)
        self.assertEqual(result.player.ast_step, 11)
        self.assertEqual(result.player.census, 40)
        # Kuusi kenttää, yksi käyttäjän teko, yksi versionnosto.
        self.assertEqual(result.player.version, 1)
        self.assertEqual(result.state_version, 1)

    def test_set_player_details_enforces_the_ast_bonus_rule(self) -> None:
        service = LocalGameService(_game())
        service.set_ast_bonus("Hellas", True)

        with self.assertRaises(RuleViolation):
            service.set_player_details(
                "Minoa",
                nickname="M",
                block="WEST",
                cities=1,
                ast_step=1,
                census=1,
                ast_bonus=True,
            )

    def test_set_turn_is_a_game_level_command(self) -> None:
        service = LocalGameService(_game())

        result = service.set_turn(3, 13)

        self.assertIsNone(result.player)
        self.assertEqual(result.state_version, 1)
        snapshot = service.snapshot()
        self.assertEqual(snapshot.round_number, 3)
        self.assertEqual(snapshot.current_phase, 13)

    def test_set_turn_checks_the_state_version(self) -> None:
        service = LocalGameService(_game())
        service.set_cities("Hellas", 2)

        with self.assertRaises(VersionConflict):
            service.set_turn(2, 1, expected_state_version=0)

    def test_game_level_log_entry_has_no_player_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "peli.json"
            service = LocalGameService(_game(), save_path=save_path)

            service.set_turn(2, 1, actor="laptop")

            entry = json.loads(
                save_path.with_suffix(".jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(entry["command"], "set_turn")
            self.assertIsNone(entry["player_version"])


if __name__ == "__main__":
    unittest.main()
