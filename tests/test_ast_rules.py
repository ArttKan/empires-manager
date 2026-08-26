import unittest

from src.core.ast_rules import (
    BASIC_AST_REQUIREMENTS,
    ast_marker_state,
    meets_basic_ast_requirement,
)
from src.core.models import PlayerState


class AstRulesTests(unittest.TestCase):
    def test_basic_requirements_cover_all_six_eras(self) -> None:
        self.assertEqual(len(BASIC_AST_REQUIREMENTS), 6)
        self.assertEqual(BASIC_AST_REQUIREMENTS[0].minimum_cities, 0)
        self.assertEqual(BASIC_AST_REQUIREMENTS[1].minimum_cities, 2)
        self.assertEqual(BASIC_AST_REQUIREMENTS[2].minimum_advances, 3)
        self.assertEqual(BASIC_AST_REQUIREMENTS[3].minimum_advance_cost, 100)
        self.assertEqual(BASIC_AST_REQUIREMENTS[4].minimum_advance_cost, 200)
        self.assertEqual(BASIC_AST_REQUIREMENTS[5].minimum_advances, 3)

    def test_advance_cost_threshold_is_applied(self) -> None:
        player = PlayerState(
            "Assyria",
            "A",
            "WEST",
            cities=4,
            advances=["mining", "wonder_of_the_world"],
        )
        self.assertTrue(meets_basic_ast_requirement(player, 4))
        player.advances = ["monument", "naval_warfare"]
        self.assertFalse(meets_basic_ast_requirement(player, 4))

    def test_marker_is_blocked_before_unmet_next_era(self) -> None:
        player = PlayerState("Assyria", "A", "WEST", cities=1, ast_step=0)
        self.assertEqual(ast_marker_state(player), "BLOCKED")
        player.cities = 2
        self.assertEqual(ast_marker_state(player), "READY")

    def test_marker_warns_when_current_era_requirement_was_lost(self) -> None:
        player = PlayerState(
            "Assyria",
            "A",
            "WEST",
            cities=2,
            ast_step=8,
            advances=["mysticism", "pottery", "law"],
        )
        self.assertEqual(ast_marker_state(player), "WARNING")

    def test_final_step_has_finished_marker(self) -> None:
        player = PlayerState(
            "Assyria",
            "A",
            "WEST",
            cities=5,
            ast_step=15,
            advances=["mining", "wonder_of_the_world", "advanced_military"],
        )
        self.assertEqual(ast_marker_state(player), "FINISHED")


if __name__ == "__main__":
    unittest.main()
