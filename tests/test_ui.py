import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Palvelinasennus on headless eikä siinä ole python3-tk-pakettia. Tällöin koko
# moduuli ohitetaan, jotta testit voi ajaa myös palvelimella ennen käynnistystä.
if importlib.util.find_spec("tkinter") is None:  # pragma: no cover
    raise unittest.SkipTest("tkinter is not installed")

import tkinter as tk

from mega_empires.models import GameState, PlayerState
from mega_empires.service import LocalGameService
from mega_empires.storage import DATA_DIRECTORY_VARIABLE
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

    def test_census_entry_issues_one_command_and_skips_no_op_edits(self) -> None:
        """Census-kenttä lähettää komennon eikä muuta pelaajaoliota itse."""

        interpreter = tk.Tcl()
        value = tk.StringVar(master=interpreter, value="37")
        game = GameState(
            player_count=1,
            players=[PlayerState("Minoa", "Mia", "WEST", census=12)],
            game_mode="WEST",
        )
        app = object.__new__(MegaEmpiresApp)
        app.service = LocalGameService(game)
        app._refresh_state()

        app._commit_census(app.game.players[0], value)

        self.assertEqual(app.service.snapshot().players[0].census, 37)
        self.assertEqual(app.service.snapshot().state_version, 1)

        # Sama arvo uudelleen ei saa nostaa versiota eikä kirjata lokiin.
        app._commit_census(app.game.players[0], value)
        self.assertEqual(app.service.snapshot().state_version, 1)

    def test_counter_reads_the_current_value_not_the_captured_copy(self) -> None:
        """Painikkeen sulkeuma pitää piirtohetken kopiota; komento ei saa käyttää sitä."""

        game = GameState(
            player_count=1,
            players=[PlayerState("Minoa", "Mia", "WEST", cities=2)],
            game_mode="WEST",
        )
        app = object.__new__(MegaEmpiresApp)
        app.service = LocalGameService(game)
        app._refresh_state()
        app._refresh_all = lambda: None
        stale = app.game.players[0]

        app._change_cities(stale, 1)
        app._change_cities(stale, 1)

        # Vanhentuneesta kopiosta laskien tulos olisi 3, tuoreesta 4.
        self.assertEqual(app.service.snapshot().players[0].cities, 4)


class ScoreboardRowUpdateTests(unittest.TestCase):
    """Rivit rakennetaan kerran ja päivitetään paikallaan.

    Aiemmin jokainen muutos tuhosi ja loi lähes 500 widgetiä, mikä maksoi
    18 pelaajalla yli sekunnin. Nämä testit estävät paluun siihen.
    """

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:  # ei näyttöä käytettävissä
            raise unittest.SkipTest(f"no display: {error}")
        self.root.withdraw()

        # `_open_game` tallentaa heti. Ilman omaa hakemistoa tallennus menisi
        # `default_save_path()`:iin eli kehittäjän oikeaan `tallennukset/`
        # -hakemistoon ja korvaisi käynnissä olevan pelin. Sekä polku että
        # ympäristömuuttuja asetetaan, jotta kumpikaan reitti ei osu sinne.
        self._directory = tempfile.TemporaryDirectory()
        self._environment = mock.patch.dict(
            os.environ, {DATA_DIRECTORY_VARIABLE: self._directory.name}
        )
        self._environment.start()
        self.save_path = Path(self._directory.name) / "peli.json"
        game = GameState(
            player_count=3,
            players=[
                PlayerState("Minoa", "A", "WEST"),
                PlayerState("Hatti", "B", "WEST"),
                PlayerState("Hellas", "C", "WEST"),
            ],
            game_mode="WEST",
        )
        self.app = object.__new__(MegaEmpiresApp)
        self.app.root = self.root
        self.app.game = None
        self.app.service = None
        self.app.save_path = None
        self.app._open_game(game, self.save_path)
        self.root.update_idletasks()

    def tearDown(self) -> None:
        self.root.destroy()
        self._environment.stop()
        self._directory.cleanup()

    def _text(self, civilization: str, key: str) -> str:
        return self.app._row_widgets[civilization][key].cget("text")

    def test_value_change_does_not_recreate_widgets(self) -> None:
        before = {
            civ: id(widgets["badge"])
            for civ, widgets in self.app._row_widgets.items()
        }

        self.app._change_cities(self.app._player("Hellas"), 1)
        self.root.update_idletasks()

        after = {
            civ: id(widgets["badge"])
            for civ, widgets in self.app._row_widgets.items()
        }
        self.assertEqual(before, after)

    def test_rank_badges_follow_score_changes(self) -> None:
        self.app._change_cities(self.app._player("Hellas"), 4)
        self.root.update_idletasks()

        self.assertEqual(self._text("Hellas", "badge"), "1")
        self.assertEqual(self._text("Hellas", "total"), "4")
        self.assertEqual(self._text("Minoa", "badge"), "2")

    def test_subtitle_tracks_advances_and_bonus(self) -> None:
        self.app._save_advances(
            self.app._player("Hellas"), ["pottery", "masonry"], {}, self.root
        )
        self.root.update_idletasks()
        self.assertIn("2 Advances", self._text("Hellas", "subtitle"))

        self.app._run_command(
            lambda: self.app.service.set_ast_bonus("Hellas", True)
        )
        self.app._refresh_all()
        self.root.update_idletasks()
        self.assertIn("A.S.T. bonus", self._text("Hellas", "subtitle"))

    def test_census_field_is_not_overwritten_while_focused(self) -> None:
        """Kesken kirjoituksen olevaa kenttää ei saa kirjoittaa yli."""

        widgets = self.app._row_widgets["Hellas"]
        widgets["census_var"].set("41")
        player = self.app._player("Hellas")

        self.app._update_player_row(player, 1, focused=widgets["census_entry"])

        self.assertEqual(widgets["census_var"].get(), "41")

    def test_census_field_is_updated_when_not_focused(self) -> None:
        widgets = self.app._row_widgets["Hellas"]
        widgets["census_var"].set("41")
        player = self.app._player("Hellas")

        self.app._update_player_row(player, 1, focused=None)

        self.assertEqual(widgets["census_var"].get(), str(player.census))

    def test_rows_are_rebuilt_when_the_player_set_changes(self) -> None:
        first = id(self.app._row_widgets["Hellas"]["badge"])

        other = GameState(
            player_count=2,
            players=[
                PlayerState("Saba", "S", "EAST"),
                PlayerState("Parthia", "P", "EAST"),
            ],
            game_mode="EAST",
        )
        self.app._open_game(other, Path(self._directory.name) / 'toinen.json')
        self.root.update_idletasks()

        self.assertNotIn("Hellas", self.app._row_widgets)
        self.assertIn("Saba", self.app._row_widgets)
        self.assertNotEqual(
            first, id(self.app._row_widgets["Saba"]["badge"])
        )

    def test_hidden_tabs_are_deferred_until_shown(self) -> None:
        self.app._refresh_all()

        # Scoreboard on näkyvissä, joten vain se piirrettiin.
        self.assertNotIn("summary", self.app._pending_tabs)
        self.assertIn("ast", self.app._pending_tabs)
        self.assertIn("sequence", self.app._pending_tabs)

        self.app.notebook.select(self.app.ast_tab)
        self.app._on_tab_changed()
        self.assertNotIn("ast", self.app._pending_tabs)


if __name__ == "__main__":
    unittest.main()
