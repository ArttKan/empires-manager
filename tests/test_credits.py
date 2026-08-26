import unittest

from src.core.credits import (
    discount_advances,
    advance_price,
    color_credits,
    flexible_credit_entitlement,
    special_credit,
    starting_color_credit,
)
from src.core.data import ADVANCE_BY_ID
from src.core.models import PlayerState


class CreditTests(unittest.TestCase):
    def test_starting_credits_follow_player_count(self) -> None:
        self.assertEqual(starting_color_credit(3), 10)
        self.assertEqual(starting_color_credit(4), 5)
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


class SameTurnDiscountTests(unittest.TestCase):
    """Hankintavaihe on yhtäaikainen: saman kierroksen ostot eivät alenna toisiaan."""

    def test_untagged_advances_count_as_old(self) -> None:
        """Ennen tätä sääntöä tallennetut pelit eivät saa menettää alennuksiaan."""

        player = PlayerState("Hellas", "M", "WEST", advances=["mysticism"])

        self.assertEqual(discount_advances(player, 5), ["mysticism"])

    def test_this_turns_purchase_gives_no_discount(self) -> None:
        player = PlayerState(
            "Hellas", "M", "WEST",
            advances=["mysticism"],
            advance_turns={"mysticism": 4},
        )

        self.assertEqual(discount_advances(player, 4), [])

    def test_earlier_turns_still_discount(self) -> None:
        player = PlayerState(
            "Hellas", "M", "WEST",
            advances=["mysticism", "pottery"],
            advance_turns={"mysticism": 3, "pottery": 4},
        )

        self.assertEqual(discount_advances(player, 4), ["mysticism"])

    def test_row_chain_ignores_a_same_turn_card(self) -> None:
        player = PlayerState(
            "Hellas", "M", "WEST",
            advances=["mysticism"],
            advance_turns={"mysticism": 4},
        )
        monument = ADVANCE_BY_ID["monument"]

        same_turn = advance_price(
            monument, player, 12, owned=discount_advances(player, 4)
        )
        next_turn = advance_price(
            monument, player, 12, owned=discount_advances(player, 5)
        )

        self.assertEqual(same_turn.special_discount, 0)
        self.assertEqual(next_turn.special_discount, 10)

    def test_colour_credit_also_waits_a_turn(self) -> None:
        player = PlayerState(
            "Hellas", "M", "WEST",
            advances=["pottery"],
            advance_turns={"pottery": 2},
        )

        same_turn = color_credits(player, 12, owned=discount_advances(player, 2))
        next_turn = color_credits(player, 12, owned=discount_advances(player, 3))

        self.assertEqual(same_turn["CRAFT"], 0)
        self.assertEqual(next_turn["CRAFT"], 10)


if __name__ == "__main__":
    unittest.main()
