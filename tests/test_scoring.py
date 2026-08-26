import unittest

from src.core.models import PlayerState
from src.core.scoring import (
    calculate_score,
    players_in_ast_order,
    ranked_players,
    visible_rankings,
)


class ScoringTests(unittest.TestCase):
    def test_score_combines_all_visible_components(self) -> None:
        player = PlayerState(
            civilization="Hellas",
            nickname="Matti",
            block="WEST",
            cities=7,
            ast_step=10,
            advances=["mysticism", "monument", "wonder_of_the_world"],
            ast_bonus=True,
        )
        score = calculate_score(player)
        self.assertEqual(score.cities, 7)
        self.assertEqual(score.ast, 50)
        self.assertEqual(score.advances, 10)
        self.assertEqual(score.bonus, 5)
        self.assertEqual(score.total, 72)

    def test_unknown_card_does_not_break_old_save(self) -> None:
        player = PlayerState(
            civilization="Minoa",
            nickname="A",
            block="WEST",
            advances=["mysticism", "future_card"],
        )
        self.assertEqual(calculate_score(player).advances, 1)

    def test_ranking_orders_by_total_score(self) -> None:
        low = PlayerState("Minoa", "A", "WEST", cities=2)
        high = PlayerState("Saba", "B", "EAST", cities=3)
        self.assertEqual(ranked_players([low, high]), [high, low])

    def test_equal_points_receive_equal_visible_rank(self) -> None:
        first = PlayerState("Minoa", "A", "WEST", cities=3)
        second = PlayerState("Saba", "B", "EAST", cities=3)
        rankings = visible_rankings([first, second])
        self.assertEqual(rankings["Minoa"], 1)
        self.assertEqual(rankings["Saba"], 1)

    def test_scoreboard_order_follows_ast_instead_of_score(self) -> None:
        later_ast_rank = PlayerState("Saba", "B", "EAST", cities=9)
        earlier_ast_rank = PlayerState("Minoa", "A", "WEST", cities=0)

        self.assertEqual(
            players_in_ast_order([later_ast_rank, earlier_ast_rank]),
            [earlier_ast_rank, later_ast_rank],
        )
        self.assertEqual(
            visible_rankings([later_ast_rank, earlier_ast_rank])["Saba"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
