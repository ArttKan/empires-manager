import unittest

from src.core.calamities import MAJOR_CALAMITIES, MINOR_CALAMITIES


class CalamityReferenceTests(unittest.TestCase):
    def test_minor_calamities_cover_trade_stacks_two_through_nine(self) -> None:
        self.assertEqual(
            [calamity.stack for calamity in MINOR_CALAMITIES],
            list(range(2, 10)),
        )
        self.assertTrue(all(calamity.effect for calamity in MINOR_CALAMITIES))

    def test_major_calamities_are_in_resolution_order(self) -> None:
        self.assertEqual(
            [calamity.stack for calamity in MAJOR_CALAMITIES],
            [stack for stack in range(2, 10) for _ in range(2)],
        )
        for index in range(0, len(MAJOR_CALAMITIES), 2):
            self.assertFalse(MAJOR_CALAMITIES[index].tradeable)
            self.assertTrue(MAJOR_CALAMITIES[index + 1].tradeable)

    def test_all_major_calamities_are_present(self) -> None:
        self.assertEqual(
            [calamity.name for calamity in MAJOR_CALAMITIES],
            [
                "Volcanic Eruption",
                "Treachery",
                "Famine",
                "Slave Revolt",
                "Flood",
                "Superstition",
                "Civil War",
                "Barbarian Hordes",
                "Cyclone",
                "Epidemic",
                "Tyranny",
                "Civil Disorder",
                "Corruption",
                "Iconoclasm and Heresy",
                "Regression",
                "Piracy",
            ],
        )


if __name__ == "__main__":
    unittest.main()
