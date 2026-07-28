import tkinter as tk
import unittest

from mega_empires.models import GameState, PlayerState
from mega_empires.sequence import PHASE_BY_NUMBER
from mega_empires.ui import (
    CALAMITY_DIALOG_SPECS,
    DEFAULT_RULES_VALUES,
    PHASE_AFFECTING_ADVANCES,
    PHASE_UPON_PURCHASE_ADVANCES,
    MegaEmpiresApp,
    _valid_credit_allocation,
)


class ScoreboardUiTests(unittest.TestCase):
    def test_small_west_scenario_uses_market_phase_rules(self) -> None:
        app = object.__new__(MegaEmpiresApp)
        app.game = GameState(
            3,
            [
                PlayerState("Minoa", "A", "WEST"),
                PlayerState("Hatti", "B", "WEST"),
                PlayerState("Hellas", "C", "WEST"),
            ],
            game_mode="WEST",
        )

        self.assertIn(
            "up to 6 market rounds",
            app._phase_order_summary(PHASE_BY_NUMBER[7]),
        )
        self.assertTrue(app._small_player_phase_rules(PHASE_BY_NUMBER[6]))
        self.assertIn(
            "Minor Calamities are not used in the 3–4 player scenario.",
            app._small_player_phase_rules(PHASE_BY_NUMBER[8]),
        )

    def test_all_remaining_major_calamities_have_generic_dialogs(
        self,
    ) -> None:
        self.assertEqual(
            set(CALAMITY_DIALOG_SPECS),
            {
                "Treachery",
                "Famine",
                "Slave Revolt",
                "Flood",
                "Superstition",
                "Barbarian Hordes",
                "Cyclone",
                "Epidemic",
                "Tyranny",
                "Civil Disorder",
                "Corruption",
                "Iconoclasm and Heresy",
                "Regression",
                "Piracy",
            },
        )

    def test_barbarian_hordes_lists_all_explicit_advance_interactions(
        self,
    ) -> None:
        self.assertEqual(
            {
                advance_id
                for advance_id, _effect in CALAMITY_DIALOG_SPECS[
                    "Barbarian Hordes"
                ]["advances"]
            },
            {
                "monarchy",
                "politics",
                "provincial_empire",
                "universal_doctrine",
            },
        )

    def test_tax_collection_lists_directly_affecting_advances(self) -> None:
        self.assertEqual(
            PHASE_AFFECTING_ADVANCES[1],
            (
                ("coinage", "COI"),
                ("democracy", "DEM"),
                ("monarchy", "MON"),
            ),
        )

    def test_tax_advance_column_contains_only_owned_affecting_cards(self) -> None:
        player = PlayerState(
            "Minoa",
            "Mia",
            "WEST",
            advances=["coinage", "monarchy", "pottery"],
        )
        app = object.__new__(MegaEmpiresApp)
        owned = app._owned_affecting_advances(PHASE_BY_NUMBER[1], player)
        self.assertEqual(owned, (("coinage", "COI"), ("monarchy", "MON")))

    def test_movement_lists_directly_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[3]),
            {
                "astronavigation": "ASN",
                "cloth_making": "CLO",
                "naval_warfare": "NAV",
                "roadbuilding": "RDB",
                "military": "MIL",
                "diplomacy": "DIP",
                "cultural_ascendancy": "CUL",
                "advanced_military": "AMI",
            },
        )

    def test_movement_default_token_rule_is_precise(self) -> None:
        movement_values: list[str] = []
        phase_number = 0
        for heading, value in DEFAULT_RULES_VALUES:
            if heading:
                phase_number = int(heading.split(maxsplit=1)[0])
            if phase_number == 3:
                movement_values.append(value)
        self.assertEqual(movement_values[0], "Token: 1 area or into a ship")

    def test_conflict_lists_directly_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[4]),
            {
                "advanced_military": "AMI",
                "agriculture": "AGR",
                "cultural_ascendancy": "CUL",
                "engineering": "ENG",
                "metalworking": "MET",
                "naval_warfare": "NAV",
            },
        )

    def test_conflict_default_rules_include_resolution_reminders(self) -> None:
        values = self._default_values_for_phase(4)
        self.assertIn(
            "Resolve all token conflicts before city attacks",
            values,
        )
        self.assertIn(
            "Minority removes first  •  Equal counts remove simultaneously",
            values,
        )
        self.assertIn(
            "Draw 1 random trade card and gain up to 3 treasury",
            values,
        )

    def test_city_construction_lists_directly_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[5]),
            {
                "urbanism": "URB",
                "architecture": "ARC",
                "agriculture": "AGR",
                "cultural_ascendancy": "CUL",
                "public_works": "PUB",
            },
        )

    def test_city_construction_default_rules_include_cleanup(self) -> None:
        values = self._default_values_for_phase(5)
        self.assertIn(
            'Cities cannot be built in printed "0" population-limit areas',
            values,
        )
        self.assertIn("Check all areas for excess population", values)

    def test_trade_card_acquisition_lists_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[6]),
            {
                "rhetoric": "RHE",
                "cartography": "CAR",
                "mining": "MIN",
                "wonder_of_the_world": "WON",
            },
        )

    def test_special_abilities_phase_lists_all_seven_cards(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[10]),
            {
                "diaspora": "DIA",
                "fundamentalism": "FUN",
                "monotheism": "MTH",
                "politics": "POL",
                "provincial_empire": "PRO",
                "trade_routes": "TRD",
                "universal_doctrine": "UND",
            },
        )

    def test_surplus_support_phase_lists_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[11]),
            {
                "agriculture": "AGR",
                "cultural_ascendancy": "CUL",
                "public_works": "PUB",
            },
        )

    def test_surplus_support_rules_include_excess_population_check(self) -> None:
        self.assertIn(
            "Check all areas for excess population",
            self._default_values_for_phase(11),
        )

    def test_advance_acquisition_lists_affecting_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_AFFECTING_ADVANCES[12]),
            {
                "mining": "MIN",
                "roadbuilding": "RDB",
                "trade_empire": "TEM",
            },
        )

    def test_advance_acquisition_separates_purchase_time_advances(self) -> None:
        self.assertEqual(
            dict(PHASE_UPON_PURCHASE_ADVANCES[12]),
            {
                "anatomy": "ANA",
                "library": "LIB",
                "monument": "MON",
                "written_record": "WRI",
            },
        )

    def test_flexible_credit_allocation_requires_exact_full_amount(self) -> None:
        self.assertTrue(
            _valid_credit_allocation(
                {"ART": 5, "CIVIC": 0, "CRAFT": 5, "RELIGION": 0, "SCIENCE": 0},
                10,
            )
        )
        self.assertFalse(
            _valid_credit_allocation(
                {"ART": 5, "CIVIC": 0, "CRAFT": 0, "RELIGION": 0, "SCIENCE": 0},
                10,
            )
        )
        self.assertFalse(
            _valid_credit_allocation(
                {"ART": 3, "CIVIC": 2, "CRAFT": 5, "RELIGION": 0, "SCIENCE": 0},
                10,
            )
        )

    def test_ast_alteration_lists_wonder_of_the_world(self) -> None:
        self.assertEqual(
            PHASE_AFFECTING_ADVANCES[13],
            (("wonder_of_the_world", "WON"),),
        )

    def _default_values_for_phase(self, selected_phase: int) -> list[str]:
        values: list[str] = []
        phase_number = 0
        for heading, value in DEFAULT_RULES_VALUES:
            if heading:
                phase_number = int(heading.split(maxsplit=1)[0])
            if phase_number == selected_phase:
                values.append(value)
        return values

    def test_census_entry_commits_directly_without_refresh(self) -> None:
        interpreter = tk.Tcl()
        value = tk.StringVar(master=interpreter, value="37")
        player = PlayerState("Minoa", "Mia", "WEST", census=12)
        app = object.__new__(MegaEmpiresApp)
        save_calls: list[bool] = []
        app._save = lambda: save_calls.append(True)

        app._commit_census(player, value)

        self.assertEqual(player.census, 37)
        self.assertEqual(len(save_calls), 1)

        app._commit_census(player, value)
        self.assertEqual(len(save_calls), 1)


if __name__ == "__main__":
    unittest.main()
