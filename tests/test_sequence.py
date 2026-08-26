import unittest

from src.core.models import PlayerState
from src.core.sequence import (
    PHASES,
    SURPLUS_SUPPORT_ADVANCES,
    adjacent_phase,
    ast_progress_order,
    movement_order,
    special_ability_order,
    surplus_support_players,
    trade_card_order,
)


class SequenceTests(unittest.TestCase):
    def test_sequence_contains_all_thirteen_phases(self) -> None:
        self.assertEqual([phase.number for phase in PHASES], list(range(1, 14)))

    def test_movement_reminds_ship_limits_and_costs(self) -> None:
        movement_rules = " ".join(PHASES[2].rules)
        self.assertIn("up to 4 water areas", movement_rules)
        self.assertIn("carry up to 5 tokens", movement_rules)
        self.assertIn("Build a new ship for 2 tokens", movement_rules)
        self.assertIn("maintain it with 1 token", movement_rules)

    def test_movement_uses_census_and_puts_military_last(self) -> None:
        high = PlayerState("Saba", "High", "EAST", census=40)
        low = PlayerState("Minoa", "Low", "WEST", census=20)
        military = PlayerState(
            "Assyria",
            "Military",
            "WEST",
            census=55,
            advances=["military"],
        )

        self.assertEqual(
            movement_order([military, low, high]),
            [high, low, military],
        )

    def test_movement_census_tie_uses_ast_ranking(self) -> None:
        later = PlayerState("Saba", "B", "EAST", census=30)
        earlier = PlayerState("Minoa", "A", "WEST", census=30)
        self.assertEqual(movement_order([later, earlier]), [earlier, later])

    def test_trade_cards_use_lowest_positive_city_count_first(self) -> None:
        none = PlayerState("Minoa", "None", "WEST", cities=0)
        many = PlayerState("Saba", "Many", "EAST", cities=6)
        few = PlayerState("Assyria", "Few", "WEST", cities=2)
        self.assertEqual(trade_card_order([none, many, few]), [few, many])

    def test_ast_progress_uses_ast_ranking_for_ties(self) -> None:
        behind = PlayerState("Assyria", "Behind", "WEST", ast_step=4)
        later_rank = PlayerState("Saba", "B", "EAST", ast_step=8)
        earlier_rank = PlayerState("Minoa", "A", "WEST", ast_step=8)
        self.assertEqual(
            ast_progress_order([behind, later_rank, earlier_rank]),
            [earlier_rank, later_rank, behind],
        )

    def test_special_ability_order_excludes_other_players(self) -> None:
        no_ability = PlayerState(
            "Minoa",
            "No",
            "WEST",
            ast_step=10,
            advances=["military"],
        )
        ability = PlayerState(
            "Saba",
            "Yes",
            "EAST",
            ast_step=5,
            advances=["diaspora"],
        )
        self.assertEqual(special_ability_order([no_ability, ability]), [ability])

    def test_surplus_support_list_contains_only_affected_players(self) -> None:
        agriculture = PlayerState(
            "Saba",
            "A",
            "EAST",
            advances=["agriculture"],
        )
        public_works = PlayerState(
            "Minoa",
            "P",
            "WEST",
            advances=["public_works"],
        )
        ordinary = PlayerState("Assyria", "O", "WEST")
        self.assertEqual(
            surplus_support_players([agriculture, ordinary, public_works]),
            [public_works, agriculture],
        )
        self.assertEqual(
            SURPLUS_SUPPORT_ADVANCES,
            {"agriculture", "cultural_ascendancy", "public_works"},
        )

    def test_phase_navigation_crosses_turn_boundary(self) -> None:
        self.assertEqual(adjacent_phase(3, 13, 1), (4, 1))
        self.assertEqual(adjacent_phase(4, 1, -1), (3, 13))
        self.assertEqual(adjacent_phase(1, 1, -1), (1, 1))


if __name__ == "__main__":
    unittest.main()
