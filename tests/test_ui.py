import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# The server install is headless and the container image is slim; neither can
# run Tk. The whole module is then skipped, so the suite passes as a deploy gate.
#
# The import is attempted rather than looked up with find_spec: a slim image
# ships the tkinter package but not libtk8.6.so, so the spec exists and the
# import still fails. find_spec only answers "is it on disk", which is not the
# question.
try:  # pragma: no cover
    import tkinter as tk
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("tkinter is not available")

from src.core.models import GameState, PlayerState
from src.client.remote import RemoteGameService
from src.service import (
    LocalGameService,
    ServiceUnavailable,
    VersionConflict,
)
from src.storage import DATA_DIRECTORY_VARIABLE
from src.core.sequence import PHASE_BY_NUMBER
from src.client import ui as ui_module
from src.client.ui import (
    POLL_BACKOFF_MS,
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
        """The Census field sends a command and never mutates the player itself."""

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

        # The same value again must not bump the version or write to the log.
        app._commit_census(app.game.players[0], value)
        self.assertEqual(app.service.snapshot().state_version, 1)

    def test_counter_reads_the_current_value_not_the_captured_copy(self) -> None:
        """A button's closure holds a draw-time copy; the command must not use it."""

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

        # Counting from the stale copy the result would be 3, from the fresh one 4.
        self.assertEqual(app.service.snapshot().players[0].cities, 4)


class ScoreboardRowUpdateTests(unittest.TestCase):
    """Rows are built once and updated in place.

    Every change used to destroy and create nearly 500 widgets, which cost over
    a second at 18 players. These tests prevent a return to that.
    """

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:  # no display available
            raise unittest.SkipTest(f"no display: {error}")
        self.root.withdraw()

        # `_open_game` saves immediately. Without a directory of its own the save
        # would go to `default_save_path()`, that is the developer's real
        # `tallennukset/` directory, and overwrite a live game. Both the path and the
        # environment variable are set so neither route can land there.
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
        """A field being typed into must not be overwritten."""

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

    def test_sequence_shell_is_built_once(self) -> None:
        """Rebuilding the whole tab cost ~100 ms at 18 players."""

        self.app.notebook.select(self.app.sequence_tab)
        self.app._refresh_sequence()
        self.root.update_idletasks()
        first = [id(w) for w in self.app.sequence_tab.winfo_children()]
        buttons = {n: id(b) for n, b in self.app._phase_buttons.items()}

        self.app._refresh_sequence()
        self.root.update_idletasks()

        self.assertEqual(
            first, [id(w) for w in self.app.sequence_tab.winfo_children()]
        )
        self.assertEqual(
            buttons, {n: id(b) for n, b in self.app._phase_buttons.items()}
        )

    def test_irrelevant_change_does_not_redraw_the_phase_detail(self) -> None:
        """Census affects phase 3; while looking at phase 12 it affects nothing."""

        self.app.game.current_phase = 12
        self.app._refresh_sequence()
        self.root.update_idletasks()
        before = [
            id(w) for w in self.app._sequence_detail_host.winfo_children()
        ]

        self.app.game.players[0].census = 44
        self.app._refresh_sequence()
        self.root.update_idletasks()

        self.assertEqual(
            before,
            [id(w) for w in self.app._sequence_detail_host.winfo_children()],
        )

    def test_phase_change_redraws_the_detail(self) -> None:
        self.app.game.current_phase = 12
        self.app._refresh_sequence()
        self.root.update_idletasks()
        before = [
            id(w) for w in self.app._sequence_detail_host.winfo_children()
        ]

        self.app.game.current_phase = 3
        self.app._refresh_sequence()
        self.root.update_idletasks()

        self.assertNotEqual(
            before,
            [id(w) for w in self.app._sequence_detail_host.winfo_children()],
        )

    def test_ast_canvas_is_reused_and_redrawn_only_on_change(self) -> None:
        self.app._refresh_ast()
        self.root.update_idletasks()
        canvas = self.app._ast_canvas
        signature = self.app._ast_signature_value

        self.app.game.players[0].census = 31
        self.app._refresh_ast()
        self.assertIs(canvas, self.app._ast_canvas)
        self.assertEqual(signature, self.app._ast_signature_value)

        self.app.game.players[0].ast_step = 9
        self.app._refresh_ast()
        self.assertIs(canvas, self.app._ast_canvas)
        self.assertNotEqual(signature, self.app._ast_signature_value)

    def test_hidden_tabs_are_deferred_until_shown(self) -> None:
        self.app._refresh_all()

        # The Scoreboard is visible, so only it was drawn.
        self.assertNotIn("summary", self.app._pending_tabs)
        self.assertIn("ast", self.app._pending_tabs)
        self.assertIn("sequence", self.app._pending_tabs)

        self.app.notebook.select(self.app.ast_tab)
        self.app._on_tab_changed()
        self.assertNotIn("ast", self.app._pending_tabs)


class _StubRemote(RemoteGameService):
    """A RemoteGameService that never touches the network.

    It inherits from the real class because `_poll` and the status line detect
    remote mode with isinstance — a standalone stub would skip that branch
    entirely.
    """

    def __init__(self, snapshots) -> None:
        super().__init__("http://stub.invalid", "token", timeout=0.01)
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        value = self._snapshots[min(self.calls - 1, len(self._snapshots) - 1)]
        if isinstance(value, Exception):
            raise value
        return value


class RemoteModeTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"no display: {error}")
        self.root.withdraw()
        self.app = object.__new__(MegaEmpiresApp)
        self.app.root = self.root
        self.app.save_path = None
        self.app.game = self._game(state_version=1)
        self.app.service = None
        # The poll draws only while the main view is up.
        self.app._view_live = True

    def tearDown(self) -> None:
        self.root.destroy()

    @staticmethod
    def _game(state_version: int = 0, cities: int = 0) -> GameState:
        return GameState(
            player_count=2,
            players=[
                PlayerState("Minoa", "A", "WEST", cities=cities),
                PlayerState("Hellas", "C", "WEST"),
            ],
            game_mode="WEST",
            state_version=state_version,
        )

    def test_poll_redraws_only_when_the_version_changed(self) -> None:
        same = self._game(state_version=1)
        self.app.service = _StubRemote([same])
        redraws = []
        self.app._refresh_all = lambda: redraws.append(True)

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.assertEqual(redraws, [])

    def test_poll_adopts_a_newer_snapshot(self) -> None:
        newer = self._game(state_version=9, cities=6)
        self.app.service = _StubRemote([newer])
        redraws = []
        self.app._refresh_all = lambda: redraws.append(True)

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.assertEqual(self.app.game.state_version, 9)
        self.assertEqual(self.app.game.players[0].cities, 6)
        self.assertEqual(len(redraws), 1)

    def test_lost_connection_keeps_the_current_view(self) -> None:
        """Yhteyskatko ei ole pelitilan muutos."""

        self.app.service = _StubRemote([ServiceUnavailable("boom")])
        self.app._refresh_all = lambda: self.fail("must not redraw")
        before = self.app.game

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.assertIs(self.app.game, before)
        self.assertFalse(self.app._connected)

    def test_failed_poll_backs_off(self) -> None:
        """Blocking urllib + frequent polling = a frozen UI."""

        self.app.service = _StubRemote([ServiceUnavailable("boom")])
        scheduled = []
        self.app.root.after = lambda ms, fn=None: scheduled.append(ms)

        self.app._poll()

        self.assertEqual(scheduled, [POLL_BACKOFF_MS])

    def test_version_conflict_refreshes_instead_of_retrying(self) -> None:
        """Automaattinen uudelleenyritys yliajaisi toisen laitteen muutoksen."""

        self.app.service = _StubRemote([self._game(state_version=5, cities=8)])
        self.app._refresh_all = lambda: None

        def conflicting():
            raise VersionConflict(1, 4)

        with mock.patch.object(ui_module.messagebox, "showinfo") as info:
            accepted = self.app._run_command(conflicting)

        self.assertFalse(accepted)
        self.assertTrue(info.called)
        self.assertEqual(self.app.game.state_version, 5)

    def test_outage_during_a_command_says_the_change_was_not_saved(self) -> None:
        """An outage is not a rejection, so the view stays and looks correct.

        Without an explicit message the game master would think the change had
        gone through, and nothing would say that the mirror is reachable by
        restarting.
        """

        def unreachable():
            raise ServiceUnavailable(
                "<urlopen error [Errno 111] Connection refused>"
            )

        with mock.patch.object(ui_module.messagebox, "showerror") as shown:
            accepted = self.app._run_command(unreachable)

        self.assertFalse(accepted)
        message = shown.call_args[0][1]
        self.assertIn("was not saved", message)
        # The reason belongs in this dialog: this is where the question is whether
        # the network is at fault.
        self.assertIn("Connection refused", message)
        self.assertIn(ui_module.OFFLINE_HINT, message)

    def test_offline_header_gives_the_route_back(self) -> None:
        """The line is read from a TV: the hint helps, urllib's text does not."""

        self.app.service = _StubRemote([self._game()])
        self.app._connected = False
        self.app._connection_message = (
            "<urlopen error [Errno 111] Connection refused>"
        )

        text = self.app._connection_text()

        self.assertIn("OFFLINE", text)
        self.assertIn(ui_module.OFFLINE_HINT, text)
        self.assertNotIn("urlopen", text)

    def test_subtitle_shows_phone_status_in_remote_mode(self) -> None:
        """The game master must know whose data they are entering themselves."""

        class Claiming(_StubRemote):
            def claims(self):
                return {"Minoa": True, "Hellas": False}

        self.app.service = Claiming([self._game()])
        player = self.app.game.players[0]

        self.assertIn(
            "phone connected", self.app._row_subtitle(self.app.game.players[0])
        )
        self.assertNotIn(
            "no phone connected",
            self.app._row_subtitle(self.app.game.players[0]),
        )
        self.assertIn(
            "no phone connected",
            self.app._row_subtitle(self.app.game.players[1]),
        )

    def test_subtitle_omits_phone_status_locally(self) -> None:
        self.app.service = LocalGameService(self._game())

        subtitle = self.app._row_subtitle(self.app.game.players[0])

        self.assertNotIn("phone", subtitle)

    def test_poll_redraws_the_summary_when_someone_joins(self) -> None:
        """Joining does not change state_version, so it must be triggered separately."""

        class Joining(_StubRemote):
            def __init__(self, snapshots):
                super().__init__(snapshots)
                self.claim_state = {"Minoa": False}

            def claims(self):
                return dict(self.claim_state)

        service = Joining([self._game(state_version=1)])
        self.app.service = service
        redraws = []
        self.app._refresh_all = lambda: None
        self.app._refresh_summary = lambda: redraws.append(True)
        self.app.summary_tab = object()   # enough for the hasattr check

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)
        self.assertEqual(redraws, [True])   # the first state it sees

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)
        self.assertEqual(len(redraws), 1)   # ei muutosta, ei piirtoa

        service.claim_state["Minoa"] = True
        self.app._poll()
        self.root.after_cancel(self.app._poll_job)
        self.assertEqual(len(redraws), 2)

    def test_poll_mirrors_new_state_to_disk(self) -> None:
        """The mirror is what makes the fallback useful."""

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ, {DATA_DIRECTORY_VARIABLE: directory}
            ):
                newer = self._game(state_version=9, cities=6)
                self.app.service = _StubRemote([newer])
                self.app._refresh_all = lambda: None

                self.app._poll()
                self.root.after_cancel(self.app._poll_job)

                mirror = self.app._mirror_path()
                self.assertTrue(mirror.is_file())
                saved = json.loads(mirror.read_text(encoding="utf-8"))
                self.assertEqual(saved["players"][0]["cities"], 6)

    def test_unchanged_state_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ, {DATA_DIRECTORY_VARIABLE: directory}
            ):
                same = self._game(state_version=1)
                self.app.service = _StubRemote([same])
                self.app._refresh_all = lambda: None

                self.app._poll()
                self.root.after_cancel(self.app._poll_job)

                self.assertFalse(self.app._mirror_path().is_file())

    def test_offline_offer_preselects_the_mirror_but_still_asks(self) -> None:
        """The program must not decide for the user which game is continued."""

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ, {DATA_DIRECTORY_VARIABLE: directory}
            ):
                self.app._mirror_state(self._game(state_version=4, cities=7))
                calls = []
                self.app._start_local = lambda **kw: calls.append(kw)
                self.app._load_selected_game = lambda path: self.fail(
                    "must offer the list, not open a game directly"
                )

                with mock.patch.object(
                    ui_module.messagebox, "askyesno", return_value=True
                ) as ask:
                    self.app._offer_offline("server down")

                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["preselect"], self.app._mirror_path())
                self.assertEqual(calls[0]["reason"], "server down")
                self.assertIn("Continue offline", ask.call_args[0][1])

    def test_offline_offer_has_nothing_preselected_without_a_mirror(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ, {DATA_DIRECTORY_VARIABLE: directory}
            ):
                calls = []
                self.app._start_local = lambda **kw: calls.append(kw)

                with mock.patch.object(
                    ui_module.messagebox, "askyesno", return_value=True
                ):
                    self.app._offer_offline("server down")

                self.assertEqual(len(calls), 1)
                self.assertIsNone(calls[0]["preselect"])

    def test_offline_banner_names_the_reason(self) -> None:
        banner = self.app._local_destination("server down")

        self.assertIn("SERVER UNAVAILABLE", banner)
        self.assertIn("server down", banner)
        self.assertIn("LOCAL GAME", banner)

    def test_poll_does_not_draw_while_the_view_is_torn_down(self) -> None:
        """Velhon aikana widgetit on tuhottu; piirto kaataisi Tkinterin."""

        self.app.service = _StubRemote([self._game(state_version=9)])
        self.app._view_live = False
        self.app._refresh_all = lambda: self.fail("must not draw")
        before = self.app.game

        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.assertIs(self.app.game, before)

    def test_polling_resumes_once_the_view_is_back(self) -> None:
        service = _StubRemote([self._game(state_version=9)])
        self.app.service = service
        self.app._view_live = False
        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.app._view_live = True
        self.app._refresh_all = lambda: None
        self.app._poll()
        self.root.after_cancel(self.app._poll_job)

        self.assertEqual(self.app.game.state_version, 9)

    def test_lobby_visible_survives_a_destroyed_notebook(self) -> None:
        """`_poll` fires on its timer even just after the view was torn down."""

        frame = tk.Frame(self.root)
        notebook = ttk_notebook = __import__(
            "tkinter.ttk", fromlist=["Notebook"]
        ).Notebook(self.root)
        notebook.add(frame, text="Players")
        self.app.notebook = notebook
        self.app.lobby_tab = frame
        notebook.destroy()

        self.assertFalse(self.app._lobby_visible())

    def test_census_typing_is_debounced_into_one_command(self) -> None:
        self.app.service = _StubRemote([self._game()])
        commits = []
        self.app._commit_census = lambda player, value: commits.append(value.get())
        value = tk.StringVar(master=self.root, value="4")
        player = self.app.game.players[0]

        self.app._schedule_census_commit(player, value)
        value.set("45")
        self.app._schedule_census_commit(player, value)
        self.assertEqual(commits, [])

        self.root.update()
        deadline = time.monotonic() + 2
        while not commits and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)

        self.assertEqual(commits, ["45"])


class DestinationBannerTests(unittest.TestCase):
    """The startup views have to say where the game will be saved.

    Without this the new-game wizard looks the same whether the game ends up on
    this machine or on the server.
    """

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"no display: {error}")
        self.root.withdraw()
        ui_module._configure_styles(self.root)
        self._directory = tempfile.TemporaryDirectory()
        self._environment = mock.patch.dict(
            os.environ, {DATA_DIRECTORY_VARIABLE: self._directory.name}
        )
        self._environment.start()
        self.app = object.__new__(MegaEmpiresApp)
        self.app.root = self.root
        self.app.game = None
        self.app.service = None
        self.app.save_path = None

    def tearDown(self) -> None:
        self.root.destroy()
        self._environment.stop()
        self._directory.cleanup()

    @staticmethod
    def _banners(widget) -> list:
        found = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and "GAME —" in child.cget("text"):
                found.append(child.cget("text"))
            found.extend(DestinationBannerTests._banners(child))
        return found

    def test_local_wizard_names_the_save_directory(self) -> None:
        wizard = ui_module.NewGameWizard(
            self.root, lambda *a: None, destination=self.app._local_destination()
        )
        self.root.update_idletasks()
        try:
            banners = self._banners(wizard)
            self.assertEqual(len(banners), 1)
            self.assertIn("LOCAL GAME", banners[0])
            self.assertIn(self._directory.name, banners[0])
            self.assertTrue(wizard.ask_name)
        finally:
            wizard.destroy()

    def test_remote_wizard_names_the_server_and_hides_the_name_field(
        self,
    ) -> None:
        """In remote mode the name would go unused, so it is not asked for."""

        self.app.service = RemoteGameService("https://example.test", "tok")
        wizard = ui_module.NewGameWizard(
            self.root,
            lambda *a: None,
            destination=self.app._remote_destination(),
            ask_name=False,
        )
        self.root.update_idletasks()
        try:
            banners = self._banners(wizard)
            self.assertEqual(len(banners), 1)
            self.assertIn("REMOTE GAME", banners[0])
            self.assertIn("https://example.test", banners[0])
            self.assertFalse(wizard.ask_name)
            # The name is neither asked for nor invented: the game goes to the server.
            self.assertEqual(wizard.save_name.get(), "")
        finally:
            wizard.destroy()

    def test_dialog_preselects_the_requested_save(self) -> None:
        """The mirror is preselected, but the other saves remain choosable."""

        from src.storage import SavedGame

        saves = tuple(
            SavedGame(
                name=name,
                path=Path(self._directory.name) / f"{name}.json",
                saved_at="2026-08-24T12:00:00",
                player_count=3,
                game_mode="WEST",
            )
            for name in ("perjantai", "palvelinpeli", "lauantai")
        )
        target = saves[1].path

        dialog = ui_module.SavedGameDialog(
            self.root,
            saves,
            lambda path: None,
            lambda: None,
            preselect=target,
        )
        self.root.update_idletasks()
        try:
            self.assertEqual(dialog.tree.selection(), ("1",))
            # The other options are still in the list.
            self.assertEqual(len(dialog.tree.get_children()), 3)
        finally:
            dialog.destroy()

    def test_dialog_defaults_to_the_first_save_without_preselection(
        self,
    ) -> None:
        from src.storage import SavedGame

        saves = tuple(
            SavedGame(
                name=name,
                path=Path(self._directory.name) / f"{name}.json",
                saved_at="2026-08-24T12:00:00",
                player_count=3,
                game_mode="WEST",
            )
            for name in ("eka", "toka")
        )
        dialog = ui_module.SavedGameDialog(
            self.root, saves, lambda path: None, lambda: None
        )
        self.root.update_idletasks()
        try:
            self.assertEqual(dialog.tree.selection(), ("0",))
        finally:
            dialog.destroy()

    def test_remote_wizard_ignores_local_save_names(self) -> None:
        """The mirror `palvelinpeli.json` must not block creating a new game.

        In remote mode no name is asked for, so the local saves' name-collision
        check does not apply to it at all.
        """

        from src.storage import save_game, save_path_for_name

        save_game(
            GameState(
                player_count=1,
                players=[PlayerState("Hellas", "M", "WEST")],
                game_mode="WEST",
            ),
            save_path_for_name("palvelinpeli"),
        )
        self.app.service = RemoteGameService("https://example.test", "tok")
        wizard = ui_module.NewGameWizard(
            self.root,
            lambda *a: None,
            destination=self.app._remote_destination(),
            ask_name=False,
        )
        errors = []
        try:
            with mock.patch.object(
                ui_module.messagebox, "showerror",
                side_effect=lambda *a, **k: errors.append(a),
            ):
                wizard.player_count.set(3)
                wizard.game_mode.set("WEST")
                wizard._start_players()
            self.assertEqual(errors, [])
            self.assertTrue(wizard.scenario_names)
        finally:
            wizard.destroy()

    def test_local_wizard_still_rejects_a_duplicate_name(self) -> None:
        from src.storage import save_game, save_path_for_name

        save_game(
            GameState(
                player_count=1,
                players=[PlayerState("Hellas", "M", "WEST")],
                game_mode="WEST",
            ),
            save_path_for_name("perjantai"),
        )
        wizard = ui_module.NewGameWizard(self.root, lambda *a: None)
        errors = []
        try:
            with mock.patch.object(
                ui_module.messagebox, "showerror",
                side_effect=lambda *a, **k: errors.append(a),
            ):
                wizard.save_name.set("perjantai")
                wizard._start_players()
            self.assertEqual(len(errors), 1)
            self.assertIn("Name already in use", errors[0][0])
        finally:
            wizard.destroy()

    def test_saved_game_dialog_names_the_save_directory(self) -> None:
        dialog = ui_module.SavedGameDialog(
            self.root,
            (),
            lambda path: None,
            lambda: None,
            destination=self.app._local_destination(),
        )
        self.root.update_idletasks()
        try:
            banners = self._banners(dialog)
            self.assertEqual(len(banners), 1)
            self.assertIn(self._directory.name, banners[0])
        finally:
            dialog.destroy()


class LobbyTests(unittest.TestCase):
    """The lobby is the only route to releasing a seat, so it has to be right."""

    class _Stub(RemoteGameService):
        def __init__(self, status) -> None:
            super().__init__("http://stub.invalid", "t", timeout=0.01)
            self.status = status
            self.released = []
            self.status_calls = 0

        def join_status(self):
            self.status_calls += 1
            return self.status

        def release_seat(self, civilization):
            self.released.append(civilization)
            for player in self.status["players"]:
                if player["civilization"] == civilization:
                    player["claimed"] = False
            return {"civilization": civilization, "claimed": False}

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"no display: {error}")
        self.root.withdraw()
        ui_module._configure_styles(self.root)
        self.game = GameState(
            player_count=2,
            players=[
                PlayerState("Minoa", "Salla", "WEST"),
                PlayerState("Hellas", "Matti", "WEST"),
            ],
            game_mode="WEST",
        )
        self.status = {
            "join_code": "AB7QX",
            "admin_code": "K9MRT",
            "players": [
                {
                    "civilization": "Minoa",
                    "nickname": "Salla",
                    "claimed": False,
                    "elevated": False,
                },
                {
                    "civilization": "Hellas",
                    "nickname": "Matti",
                    "claimed": True,
                    "elevated": False,
                },
            ],
        }
        self.app = object.__new__(MegaEmpiresApp)
        self.app.root = self.root
        self.app.game = self.game
        self.app.save_path = None

    def tearDown(self) -> None:
        self.root.destroy()

    def _build(self, service) -> None:
        self.app.service = service
        self.app._build_main_view()
        self.root.update_idletasks()

    def _tabs(self) -> list:
        return [
            self.app.notebook.tab(tab, "text")
            for tab in self.app.notebook.tabs()
        ]

    def test_players_tab_exists_only_in_remote_mode(self) -> None:
        self._build(LocalGameService(self.game))
        self.assertNotIn("Players", self._tabs())
        self.assertIsNone(self.app.lobby_tab)

        self._build(self._Stub(self.status))
        self.assertIn("Players", self._tabs())

    def test_lobby_shows_the_code_and_the_seats(self) -> None:
        self._build(self._Stub(self.status))
        self.app._refresh_lobby()
        self.root.update_idletasks()

        shown = self._labels(self.app.lobby_tab)
        self.assertIn("AB7QX", shown)
        self.assertIn("Minoa (Salla)", shown)
        self.assertIn("Hellas (Matti)", shown)
        self.assertIn("1 of 2 players have joined", shown)

    def test_admin_code_is_not_on_the_television_by_default(self) -> None:
        """The lobby is on screen all game; a bare code would be everyone's."""

        service = self._Stub(self.status)
        self._build(service)
        self.app._refresh_lobby()
        self.root.update_idletasks()

        shown = self._labels(self.app.lobby_tab)
        self.assertNotIn("K9MRT", shown)
        self.assertIn("•••••", shown)

        self.app._toggle_admin_code()
        self.root.update_idletasks()

        self.assertIn("K9MRT", self._labels(self.app.lobby_tab))

    def test_lobby_marks_who_can_edit_every_row(self) -> None:
        """The game master should not have to remember who they gave the code to."""

        self.status["players"][1]["elevated"] = True
        self._build(self._Stub(self.status))
        self.app._refresh_lobby()
        self.root.update_idletasks()

        self.assertIn("edits all rows", self._labels(self.app.lobby_tab))

    def test_lobby_redraws_when_an_elevation_appears(self) -> None:
        """The signature has to list everything the panel renders."""

        service = self._Stub(self.status)
        self._build(service)
        self.app._refresh_lobby()
        self.root.update_idletasks()
        self.assertNotIn("edits all rows", self._labels(self.app.lobby_tab))

        self.status["players"][1]["elevated"] = True
        self.app._refresh_lobby()
        self.root.update_idletasks()

        self.assertIn("edits all rows", self._labels(self.app.lobby_tab))

    def test_unchanged_status_is_not_redrawn(self) -> None:
        """The poll runs every couple of seconds; redrawing each time would flicker."""

        service = self._Stub(self.status)
        self._build(service)
        self.app._refresh_lobby()
        self.root.update_idletasks()
        first = [id(w) for w in self.app.lobby_tab.winfo_children()]

        self.app._refresh_lobby()
        self.root.update_idletasks()

        self.assertEqual(
            first, [id(w) for w in self.app.lobby_tab.winfo_children()]
        )

    def test_release_asks_first_and_then_frees_the_seat(self) -> None:
        service = self._Stub(self.status)
        self._build(service)
        self.app._refresh_lobby()

        with mock.patch.object(
            ui_module.messagebox, "askyesno", return_value=False
        ):
            self.app._release_seat("Hellas")
        self.assertEqual(service.released, [])

        with mock.patch.object(
            ui_module.messagebox, "askyesno", return_value=True
        ):
            self.app._release_seat("Hellas")
        self.assertEqual(service.released, ["Hellas"])

    def test_lobby_reports_a_connection_failure(self) -> None:
        class Broken(self._Stub):
            def join_status(self):
                raise ServiceUnavailable("server down")

        self._build(Broken(self.status))
        self.app._refresh_lobby()
        self.root.update_idletasks()

        self.assertIn("server down", " ".join(self._labels(self.app.lobby_tab)))

    @staticmethod
    def _labels(widget, out=None) -> list:
        out = [] if out is None else out
        for child in widget.winfo_children():
            if isinstance(child, tk.Label):
                text = child.cget("text").strip()
                if text:
                    out.append(text)
            LobbyTests._labels(child, out)
        return out


if __name__ == "__main__":
    unittest.main()
