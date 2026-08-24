"""RemoteGameService oikeaa HTTP-palvelinta vasten.

Ei stubattua vastausta: testi nostaa pystyyn saman FastAPI-sovelluksen joka ajaa
palvelimella ja puhuu sille `urllib`illa. Näin `remote.py` ja `main.py` eivät voi
ajautua erilleen huomaamatta — juuri se olisi vika joka näkyisi vasta pelipöydässä.
"""

import importlib.util
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

for _module in ("fastapi", "uvicorn", "httpx"):  # pragma: no cover
    if importlib.util.find_spec(_module) is None:
        raise unittest.SkipTest(f"{_module} is not installed")

import uvicorn

import main
from mega_empires.models import GameState, PlayerState
from mega_empires.remote import RemoteGameService
from mega_empires.service import (
    LocalGameService,
    RuleViolation,
    ServiceUnavailable,
    UnknownPlayer,
    VersionConflict,
)
from mega_empires.storage import DATA_DIRECTORY_VARIABLE

TOKEN = "remote-test-token"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _game() -> GameState:
    return GameState(
        player_count=3,
        players=[
            PlayerState("Minoa", "A", "WEST"),
            PlayerState("Hatti", "B", "WEST"),
            PlayerState("Hellas", "C", "WEST"),
        ],
        game_mode="WEST",
    )


class RemoteServiceTests(unittest.TestCase):
    server: uvicorn.Server
    port: int

    @classmethod
    def setUpClass(cls) -> None:
        cls.port = _free_port()
        cls._token = main.TOKEN
        main.TOKEN = TOKEN
        config = uvicorn.Config(
            main.app, host="127.0.0.1", port=cls.port, log_level="error"
        )
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise unittest.SkipTest("uvicorn did not start in time")
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        main.TOKEN = cls._token

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self._environment = mock.patch.dict(
            os.environ, {DATA_DIRECTORY_VARIABLE: self._directory.name}
        )
        self._environment.start()
        self.save_path = Path(self._directory.name) / "peli.json"
        self.local = LocalGameService(_game(), save_path=self.save_path)
        main.set_service(self.local)
        self.remote = RemoteGameService(
            f"http://127.0.0.1:{self.port}", TOKEN, timeout=5.0
        )

    def tearDown(self) -> None:
        main.set_service(None)
        self._environment.stop()
        self._directory.cleanup()

    # -- luku ---------------------------------------------------------------

    def test_snapshot_returns_a_real_game_state(self) -> None:
        state = self.remote.snapshot()

        self.assertIsInstance(state, GameState)
        self.assertEqual(state.player_count, 3)
        self.assertEqual(state.game_mode, "WEST")
        self.assertEqual(state.state_version, 0)
        self.assertEqual(
            [p.civilization for p in state.players],
            ["Minoa", "Hatti", "Hellas"],
        )

    # -- komennot -----------------------------------------------------------

    def test_every_command_reaches_the_server(self) -> None:
        self.assertEqual(self.remote.set_cities("Hellas", 5).player.cities, 5)
        self.assertEqual(self.remote.set_census("Hellas", 22).player.census, 22)
        self.assertEqual(
            self.remote.set_ast_step("Hellas", 7).player.ast_step, 7
        )
        self.assertEqual(
            self.remote.set_advances("Hellas", ["pottery"]).player.advances,
            ["pottery"],
        )
        self.assertTrue(
            self.remote.set_ast_bonus("Hellas", True).player.ast_bonus
        )
        details = self.remote.set_player_details(
            "Hellas",
            nickname="Matti",
            block="WEST",
            cities=6,
            ast_step=11,
            census=40,
            ast_bonus=True,
        )
        self.assertEqual(details.player.display_name, "Hellas (Matti)")

        turn = self.remote.set_turn(3, 13)
        self.assertIsNone(turn.player)
        self.assertEqual(self.remote.snapshot().round_number, 3)

    def test_command_mutates_the_server_side_state(self) -> None:
        self.remote.set_cities("Hellas", 5)

        self.assertEqual(self.local.snapshot().players[2].cities, 5)

    def test_flexible_credits_survive_the_round_trip(self) -> None:
        result = self.remote.set_advances(
            "Hellas", ["written_record"], {"ART": 10}
        )

        self.assertEqual(result.player.flexible_credits["ART"], 10)

    # -- virheiden kääntäminen ----------------------------------------------

    def test_unknown_player_becomes_unknown_player(self) -> None:
        with self.assertRaises(UnknownPlayer):
            self.remote.set_cities("Atlantis", 3)

    def test_stale_version_becomes_version_conflict(self) -> None:
        self.remote.set_cities("Hellas", 5)

        with self.assertRaises(VersionConflict) as caught:
            self.remote.set_cities("Hellas", 9, expected_version=0)

        self.assertEqual(caught.exception.expected, 0)
        self.assertEqual(caught.exception.actual, 1)

    def test_rule_break_becomes_rule_violation(self) -> None:
        self.remote.set_ast_bonus("Hellas", True)

        with self.assertRaises(RuleViolation):
            self.remote.set_ast_bonus("Minoa", True)

    def test_missing_game_becomes_service_unavailable(self) -> None:
        main.set_service(None)

        with self.assertRaises(ServiceUnavailable):
            self.remote.snapshot()

    def test_bad_token_becomes_service_unavailable(self) -> None:
        wrong = RemoteGameService(
            f"http://127.0.0.1:{self.port}", "nope", timeout=5.0
        )

        with self.assertRaises(ServiceUnavailable):
            wrong.snapshot()

    def test_unreachable_server_becomes_service_unavailable(self) -> None:
        """Verkkovirhe ei saa näyttää sääntörikkomukselta."""

        dead = RemoteGameService(
            f"http://127.0.0.1:{_free_port()}", TOKEN, timeout=0.3
        )

        with self.assertRaises(ServiceUnavailable):
            dead.snapshot()

    # -- sopimuksen yhdenmukaisuus ------------------------------------------

    def test_local_and_remote_agree(self) -> None:
        """Sama komento, sama tulos kummallakin toteutuksella."""

        remote_result = self.remote.set_cities("Hellas", 5)

        other = LocalGameService(_game())
        local_result = other.set_cities("Hellas", 5)

        self.assertEqual(remote_result.state_version, local_result.state_version)
        self.assertEqual(remote_result.player.cities, local_result.player.cities)
        self.assertEqual(
            remote_result.player.version, local_result.player.version
        )
        self.assertEqual(
            remote_result.player.civilization,
            local_result.player.civilization,
        )


if __name__ == "__main__":
    unittest.main()
