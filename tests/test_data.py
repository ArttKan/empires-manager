import unittest

from mega_empires.data import (
    ADVANCES,
    ADVANCE_CHAINS,
    AST_MAX_STEP,
    BASIC_AST_ERA_STARTS,
    CIVILIZATIONS,
    ast_era_index,
    default_block,
    scenario_civilizations,
)


class DataTests(unittest.TestCase):
    def test_ast_has_all_civilizations_in_rank_order(self) -> None:
        self.assertEqual(len(CIVILIZATIONS), 18)
        self.assertEqual(
            [civilization.ast_rank for civilization in CIVILIZATIONS],
            list(range(1, 19)),
        )
        self.assertEqual(CIVILIZATIONS[0].name, "Minoa")
        self.assertEqual(CIVILIZATIONS[-1].name, "Parthia")

    def test_advance_catalog_has_51_unique_cards(self) -> None:
        self.assertEqual(len(ADVANCES), 51)
        self.assertEqual(len({advance.id for advance in ADVANCES}), 51)
        self.assertEqual({advance.victory_points for advance in ADVANCES}, {1, 3, 6})
        self.assertEqual(
            {group for advance in ADVANCES for group in advance.groups},
            {"ART", "CIVIC", "CRAFT", "RELIGION", "SCIENCE"},
        )
        self.assertEqual(
            sum(len(advance.groups) == 2 for advance in ADVANCES),
            9,
        )
        self.assertEqual(
            next(
                advance.groups
                for advance in ADVANCES
                if advance.name == "Mysticism"
            ),
            ("ART", "RELIGION"),
        )
        self.assertEqual(
            next(
                advance.groups
                for advance in ADVANCES
                if advance.name == "Engineering"
            ),
            ("CRAFT", "SCIENCE"),
        )
        self.assertEqual(len(ADVANCE_CHAINS), 17)
        for low, middle, high in ADVANCE_CHAINS:
            self.assertEqual(
                [
                    next(a.victory_points for a in ADVANCES if a.id == advance_id)
                    for advance_id in (low, middle, high)
                ],
                [1, 3, 6],
            )
        self.assertTrue(
            all(
                amount > 0 and amount % 5 == 0
                for advance in ADVANCES
                for _group, amount in advance.credits
            )
        )

    def test_ast_has_15_scoring_steps(self) -> None:
        self.assertEqual(AST_MAX_STEP, 15)

    def test_basic_ast_era_boundaries_are_civilization_specific(self) -> None:
        self.assertEqual(
            BASIC_AST_ERA_STARTS["Minoa"],
            (0, 6, 9, 11, 14, 15),
        )
        self.assertEqual(
            BASIC_AST_ERA_STARTS["Assyria"],
            (0, 5, 8, 11, 14, 15),
        )
        self.assertEqual(
            BASIC_AST_ERA_STARTS["Carthage"],
            (0, 5, 9, 11, 14, 15),
        )
        self.assertEqual(ast_era_index("Minoa", 0), 0)
        self.assertEqual(ast_era_index("Minoa", 5), 0)
        self.assertEqual(ast_era_index("Minoa", 6), 1)
        self.assertEqual(ast_era_index("Assyria", 8), 2)
        self.assertEqual(ast_era_index("Carthage", 8), 1)
        self.assertEqual(ast_era_index("Carthage", 9), 2)
        for civilization in CIVILIZATIONS:
            self.assertEqual(ast_era_index(civilization.name, 14), 4)
            self.assertEqual(ast_era_index(civilization.name, 15), 5)

    def test_large_scenario_block_overrides(self) -> None:
        self.assertEqual(default_block("Babylon", 9), "EAST")
        self.assertEqual(default_block("Hatti", 9), "WEST")
        self.assertEqual(default_block("Assyria", 12), "EAST")
        self.assertEqual(default_block("Assyria", 13), "EAST")
        self.assertEqual(default_block("Assyria", 16), "EAST")
        self.assertEqual(default_block("Assyria", 15), "EAST")
        self.assertEqual(default_block("Assyria", 14), "EAST")
        self.assertEqual(default_block("Egypt", 13), "EAST")
        self.assertEqual(default_block("Egypt", 14), "EAST")
        self.assertEqual(default_block("Egypt", 16), "WEST")
        self.assertEqual(default_block("Minoa", 10), "SINGLE")

    def test_official_setups_cover_every_player_count(self) -> None:
        for count in range(5, 10):
            for mode in ("WEST", "EAST"):
                names = scenario_civilizations(mode, count)
                self.assertEqual(len(names), count)
                self.assertEqual(len(set(names)), count)
        for count in range(10, 19):
            names = scenario_civilizations("BOTH", count)
            self.assertEqual(len(names), count)
            self.assertEqual(len(set(names)), count)

    def test_known_setup_memberships(self) -> None:
        self.assertEqual(
            set(scenario_civilizations("WEST", 5)),
            {"Minoa", "Assyria", "Hatti", "Hellas", "Egypt"},
        )
        self.assertEqual(
            set(scenario_civilizations("EAST", 6)),
            {"Saba", "Babylon", "Kushan", "Persia", "Indus", "Parthia"},
        )
        self.assertNotIn("Celt", scenario_civilizations("BOTH", 17))
        self.assertEqual(len(scenario_civilizations("BOTH", 18)), 18)

    def test_invalid_mode_and_player_count_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scenario_civilizations("WEST", 10)
        with self.assertRaises(ValueError):
            scenario_civilizations("BOTH", 9)


if __name__ == "__main__":
    unittest.main()
