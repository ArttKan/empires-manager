import unittest

from mega_empires.credits import (
    advance_price,
    color_credits,
    flexible_credit_entitlement,
    special_credit,
    starting_color_credit,
)
from mega_empires.data import ADVANCE_BY_ID
from mega_empires.models import PlayerState


class CreditTests(unittest.TestCase):
    def test_starting_credits_follow_player_count(self) -> None:
        self.assertEqual(starting_color_credit(5), 10)
        self.assertEqual(starting_color_credit(6), 5)
        self.assertEqual(starting_color_credit(7), 0)
        self.assertEqual(starting_color_credit(18), 0)

    def test_card_credits_are_added_by_color(self) -> None:
        player = PlayerState(
            "Minoa",
            "A",
            "WEST",
            advances=["pottery", "masonry"],
        )
        totals = color_credits(player, 10)
        self.assertEqual(totals["ART"], 5)
        self.assertEqual(totals["CRAFT"], 20)
        self.assertEqual(totals["SCIENCE"], 5)

    def test_rulebook_agriculture_example_costs_ninety(self) -> None:
        player = PlayerState(
            "Minoa",
            "A",
            "WEST",
            advances=["pottery", "masonry"],
        )
        price = advance_price(ADVANCE_BY_ID["agriculture"], player, 10)
        self.assertEqual(price.color_discount, 20)
        self.assertEqual(price.special_discount, 10)
        self.assertEqual(price.effective_cost, 90)

    def test_dual_color_card_uses_larger_credit_not_sum(self) -> None:
        player = PlayerState(
            "Minoa",
            "A",
            "WEST",
            flexible_credits={"ART": 20, "RELIGION": 10},
        )
        price = advance_price(ADVANCE_BY_ID["mysticism"], player, 10)
        self.assertEqual(price.color_discount, 20)
        self.assertEqual(price.effective_cost, 30)

    def test_middle_card_discounts_high_card_on_same_row(self) -> None:
        player = PlayerState(
            "Minoa",
            "A",
            "WEST",
            advances=["monument"],
        )
        self.assertEqual(
            special_credit("wonder_of_the_world", player.advances),
            20,
        )
        price = advance_price(
            ADVANCE_BY_ID["wonder_of_the_world"],
            player,
            10,
        )
        self.assertEqual(price.effective_cost, 260)

    def test_flexible_credit_entitlement_comes_from_two_cards(self) -> None:
        self.assertEqual(flexible_credit_entitlement([]), 0)
        self.assertEqual(flexible_credit_entitlement(["written_record"]), 10)
        self.assertEqual(
            flexible_credit_entitlement(["written_record", "monument"]),
            30,
        )


if __name__ == "__main__":
    unittest.main()
