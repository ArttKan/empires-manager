"""HTTP-kerroksen testit.

Moduuli ohittaa itsensä jos fastapi puuttuu, samoin kuin test_ui.py tekee
tkinterin kanssa. Kehityskoneella ei välttämättä ole venviä; palvelimella on,
joten deploy-skriptin testiportti ajaa nämä ennen uudelleenkäynnistystä.
"""

import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# TestClient tarvitsee httpx:n, eikä fastapi asenna sitä itse. Puuttuessaan se
# nostaa RuntimeErrorin eikä ImportErroria, joten se tarkistetaan erikseen —
# muuten deployn testiportti kaatuisi palvelimella sen sijaan että ohittaisi.
for _module in ("fastapi", "httpx"):  # pragma: no cover
    if importlib.util.find_spec(_module) is None:
        raise unittest.SkipTest(f"{_module} is not installed")

from fastapi.testclient import TestClient

import main
from mega_empires.models import GameState, PlayerState
from mega_empires.service import LocalGameService
from mega_empires.storage import DATA_DIRECTORY_VARIABLE

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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


class HttpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()

        # Ilman tätä `get_service()` putoaisi takaisin `default_save_path()`:iin,
        # joka kehityskoneella osoittaa repon oikeaan `tallennukset/`-hakemistoon.
        # Testi lukisi — ja komennon sattuessa kirjoittaisi — kehittäjän omaan
        # peliin. Ympäristömuuttuja pitää testit omassa hiekkalaatikossaan.
        self._environment = mock.patch.dict(
            os.environ, {DATA_DIRECTORY_VARIABLE: self._directory.name}
        )
        self._environment.start()

        self.save_path = Path(self._directory.name) / "peli.json"
        self.service = LocalGameService(_game(), save_path=self.save_path)
        main.set_service(self.service)
        self._token = main.TOKEN
        main.TOKEN = TOKEN
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.set_service(None)
        main.TOKEN = self._token
        self._environment.stop()
        self._directory.cleanup()


class AuthTests(HttpTestCase):
    def test_health_needs_no_token(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_state_requires_a_token(self) -> None:
        self.assertEqual(self.client.get("/state").status_code, 401)

    def test_wrong_token_is_rejected(self) -> None:
        response = self.client.get(
            "/state", headers={"Authorization": "Bearer nope"}
        )
        self.assertEqual(response.status_code, 401)

    def test_commands_require_a_token(self) -> None:
        response = self.client.post(
            "/players/Hellas/cities", json={"value": 4}
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_server_token_fails_closed(self) -> None:
        main.TOKEN = None
        response = self.client.get("/state", headers=AUTH)
        self.assertEqual(response.status_code, 500)


class StateTests(HttpTestCase):
    def test_state_returns_the_full_snapshot(self) -> None:
        response = self.client.get("/state", headers=AUTH)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["player_count"], 3)
        self.assertEqual(body["state_version"], 0)
        self.assertEqual(len(body["players"]), 3)

    def test_missing_game_returns_503(self) -> None:
        main.set_service(None)
        response = self.client.get("/state", headers=AUTH)
        self.assertEqual(response.status_code, 503)


class CommandTests(HttpTestCase):
    def test_set_cities_returns_player_and_version(self) -> None:
        response = self.client.post(
            "/players/Hellas/cities", json={"value": 5}, headers=AUTH
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state_version"], 1)
        self.assertEqual(body["player"]["cities"], 5)
        self.assertEqual(body["player"]["version"], 1)

    def test_unknown_player_is_404(self) -> None:
        response = self.client.post(
            "/players/Atlantis/cities", json={"value": 5}, headers=AUTH
        )
        self.assertEqual(response.status_code, 404)

    def test_stale_version_is_409_with_the_current_version(self) -> None:
        self.client.post(
            "/players/Hellas/cities", json={"value": 5}, headers=AUTH
        )
        response = self.client.post(
            "/players/Hellas/cities",
            json={"value": 9, "expected_version": 0},
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["expected_version"], 0)
        self.assertEqual(detail["current_version"], 1)

    def test_rule_violation_is_422(self) -> None:
        self.client.post(
            "/players/Hellas/ast-bonus", json={"value": True}, headers=AUTH
        )
        response = self.client.post(
            "/players/Minoa/ast-bonus", json={"value": True}, headers=AUTH
        )
        self.assertEqual(response.status_code, 422)

    def test_census_ast_step_and_advances(self) -> None:
        self.assertEqual(
            self.client.post(
                "/players/Hellas/census", json={"value": 22}, headers=AUTH
            ).json()["player"]["census"],
            22,
        )
        self.assertEqual(
            self.client.post(
                "/players/Hellas/ast-step", json={"value": 7}, headers=AUTH
            ).json()["player"]["ast_step"],
            7,
        )
        self.assertEqual(
            self.client.post(
                "/players/Hellas/advances",
                json={"advances": ["pottery", "masonry"]},
                headers=AUTH,
            ).json()["player"]["advances"],
            ["pottery", "masonry"],
        )

    def test_details_is_one_command(self) -> None:
        response = self.client.post(
            "/players/Hellas/details",
            json={
                "nickname": "Matti",
                "block": "WEST",
                "cities": 6,
                "ast_step": 11,
                "census": 40,
                "ast_bonus": False,
            },
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["version"], 1)

    def test_turn_has_no_player_in_the_response(self) -> None:
        response = self.client.post(
            "/turn",
            json={"round_number": 3, "current_phase": 13},
            headers=AUTH,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["player"])
        self.assertEqual(
            self.client.get("/state", headers=AUTH).json()["round_number"], 3
        )

    def test_commands_persist_to_disk(self) -> None:
        self.client.post(
            "/players/Hellas/cities", json={"value": 5}, headers=AUTH
        )
        saved = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["state_version"], 1)
        log = self.save_path.with_suffix(".jsonl").read_text(encoding="utf-8")
        self.assertIn("set_cities", log)


class _StubRequest:
    """Riittävä osa Requestista event_streamille."""

    def __init__(self, disconnect_after: int = 1000) -> None:
        self._calls = 0
        self._limit = disconnect_after

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > self._limit


class CreateGameTests(HttpTestCase):
    def _payload(self, players: int = 3) -> dict:
        return GameState(
            player_count=players,
            players=[
                PlayerState("Saba", "S", "EAST"),
                PlayerState("Persia", "P", "EAST"),
                PlayerState("Parthia", "X", "EAST"),
            ][:players],
            game_mode="EAST",
        ).to_dict()

    def test_create_replaces_the_current_game(self) -> None:
        response = self.client.post(
            "/game", json=self._payload(), headers=AUTH
        )

        self.assertEqual(response.status_code, 200)
        state = self.client.get("/state", headers=AUTH).json()
        self.assertEqual(state["game_mode"], "EAST")
        self.assertEqual(
            [p["civilization"] for p in state["players"]],
            ["Saba", "Persia", "Parthia"],
        )

    def test_create_resets_the_version_counters(self) -> None:
        """Uusi peli ei saa periä vanhan pelin versiolaskureita."""

        self.client.post(
            "/players/Hellas/cities", json={"value": 5}, headers=AUTH
        )
        payload = self._payload()
        payload["state_version"] = 99
        payload["players"][0]["version"] = 42

        self.client.post("/game", json=payload, headers=AUTH)

        state = self.client.get("/state", headers=AUTH).json()
        self.assertEqual(state["state_version"], 0)
        self.assertEqual(state["players"][0]["version"], 0)

    def test_create_needs_a_token(self) -> None:
        response = self.client.post("/game", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_empty_game_is_rejected(self) -> None:
        response = self.client.post(
            "/game", json={"player_count": 0, "players": []}, headers=AUTH
        )
        self.assertEqual(response.status_code, 422)

    def test_create_persists_without_a_restart(self) -> None:
        self.client.post("/game", json=self._payload(), headers=AUTH)

        saved = json.loads(
            (Path(self._directory.name) / "nykyinen_peli.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(saved["game_mode"], "EAST")


class EventStreamTests(HttpTestCase):
    """Virtaa ajetaan generaattorina eikä HTTP-vasteena.

    `/events` ei pääty koskaan, joten TestClientin stream jäisi roikkumaan sen
    sulkemiseen. Generaattori antaa saman sopimuksen ilman ikuista pyyntöä.
    """

    def _collect(self, count: int, before_second=None) -> list:
        async def run() -> list:
            generator = main.event_stream(_StubRequest())
            chunks = []
            try:
                chunks.append(await generator.__anext__())
                for _ in range(count - 1):
                    if before_second is not None:
                        await before_second()
                    chunks.append(await generator.__anext__())
            finally:
                await generator.aclose()
            return chunks

        return asyncio.run(run())

    def test_stream_opens_with_the_current_version(self) -> None:
        self.service.set_cities("Hellas", 4)

        chunk = self._collect(1)[0]

        self.assertTrue(chunk.startswith("event: state\n"))
        payload = json.loads(chunk.split("data: ", 1)[1].strip())
        self.assertEqual(payload, {"state_version": 1})

    def test_stream_carries_no_game_data(self) -> None:
        """Virta on ilman tokenia, joten siinä ei saa kulkea pelidataa."""

        self.service.set_player_details(
            "Hellas",
            nickname="Matti",
            block="WEST",
            cities=6,
            ast_step=11,
            census=40,
            ast_bonus=False,
        )

        chunk = self._collect(1)[0]

        payload = json.loads(chunk.split("data: ", 1)[1].strip())
        self.assertEqual(set(payload), {"state_version"})
        for leaked in ("Matti", "Hellas", "cities", "census"):
            self.assertNotIn(leaked, chunk)

    def test_idle_stream_sends_a_heartbeat(self) -> None:
        original = main.HEARTBEAT_SECONDS
        main.HEARTBEAT_SECONDS = 0.05
        try:
            chunks = self._collect(2)
        finally:
            main.HEARTBEAT_SECONDS = original

        self.assertEqual(chunks[1], ": heartbeat\n\n")

    def test_broadcast_reaches_a_subscriber(self) -> None:
        async def publish() -> None:
            await main.broadcast(42)

        chunks = self._collect(2, before_second=publish)

        payload = json.loads(chunks[1].split("data: ", 1)[1].strip())
        self.assertEqual(payload, {"state_version": 42})

    def test_subscriber_is_removed_when_the_stream_closes(self) -> None:
        self._collect(1)

        self.assertEqual(len(main._subscribers), 0)

    def test_stream_reports_no_version_when_no_game_is_loaded(self) -> None:
        main.set_service(None)

        chunk = self._collect(1)[0]

        payload = json.loads(chunk.split("data: ", 1)[1].strip())
        self.assertEqual(payload, {"state_version": None})


if __name__ == "__main__":
    unittest.main()
