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
from src.core.models import GameState, PlayerState
from src.service import LocalGameService
from src.server.tokens import TokenStore, tokens_path
from src.storage import DATA_DIRECTORY_VARIABLE

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
        main.set_token_store(None)
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

    def test_state_includes_derived_scores_and_ranks(self) -> None:
        """Pisteet tulevat palvelimelta, jottei sääntöjä tarvitse toistaa JS:ssä."""

        self.client.post(
            "/players/Hellas/cities", json={"value": 4}, headers=AUTH
        )
        self.client.post(
            "/players/Hellas/ast-step", json={"value": 3}, headers=AUTH
        )
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["pottery", "wonder_of_the_world"]},
            headers=AUTH,
        )

        players = self.client.get("/state", headers=AUTH).json()["players"]
        hellas = [p for p in players if p["civilization"] == "Hellas"][0]

        # 4 kaupunkia + 3 askelta * 5 VP + (1 VP pottery + 6 VP wonder)
        self.assertEqual(hellas["score"]["cities"], 4)
        self.assertEqual(hellas["score"]["ast"], 15)
        self.assertEqual(hellas["score"]["advances"], 7)
        self.assertEqual(hellas["score"]["total"], 26)
        self.assertEqual(hellas["rank"], 1)

    def test_state_carries_component_colours(self) -> None:
        """Väri tulee pelikomponentista; asiakas ei saa arvata sitä."""

        players = self.client.get("/state", headers=AUTH).json()["players"]
        by_name = {p["civilization"]: p for p in players}

        self.assertEqual(by_name["Hellas"]["color"], "#e5dd1e")
        self.assertEqual(by_name["Hellas"]["text_color"], "#101010")
        self.assertEqual(by_name["Minoa"]["color"], "#70b62c")

    def test_tied_players_share_a_rank(self) -> None:
        players = self.client.get("/state", headers=AUTH).json()["players"]

        self.assertEqual({p["rank"] for p in players}, {1})

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


class PlayerAppTests(HttpTestCase):
    def test_root_serves_the_player_page_without_a_token(self) -> None:
        """Sivu itsessään ei ole salaisuus; tokenit ovat."""

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Mega Empires", response.text)

    def test_page_is_never_cached(self) -> None:
        """Sovellus on yksi versioimaton tiedosto: välimuisti jäädyttäisi sen."""

        response = self.client.get("/")

        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_page_avoids_ad_blocker_prefixes(self) -> None:
        """Geneeriset mainossäännöt piilottavat nämä alkuiset id:t ja luokat.

        Elementit ovat silloin palvellussa HTML:ssä ja jäsennetyssä DOMissa,
        mutta näkymättömiä puhelimessa eivätkä löydy edes selaimen haulla —
        vika näyttää siltä kuin koodia ei olisi lainkaan.
        """

        text = self.client.get("/").text

        for prefix in ("adv", "ad-", "ads", "banner", "sponsor", "promo"):
            for attribute in ("id", "class"):
                self.assertNotIn(f'{attribute}="{prefix}', text, prefix)

    def test_page_has_one_code_field_and_the_wrong_row_banner(self) -> None:
        """Koodikenttiä on yksi; kumpi koodi annettiin, ratkeaa palvelimella."""

        text = self.client.get("/").text

        self.assertIn('id="code"', text)
        self.assertNotIn('id="code-admin"', text)
        # Kertoo kumpi koodi kelpasi, ennen paikan varaamista.
        self.assertIn('id="seat-role"', text)
        # Kertoo että näkyvissä on toisen rivi. Ilman sitä korotettu puhelin
        # näyttää täsmälleen tavalliselta.
        self.assertIn('id="other"', text)

    def test_hidden_beats_any_id_rule(self) -> None:
        """Piilotus on apuluokka; id-sääntö voittaisi sen tarkkuudessa.

        `#other` asettaa `display: flex`, joten ilman `!important`ia nauha jäi
        pysyvästi näkyviin vaikka luokka vaihtui DOMissa oikein.
        """

        text = self.client.get("/").text

        self.assertIn(".hidden { display: none !important; }", text)

    def test_page_carries_no_token_or_game_data(self) -> None:
        response = self.client.get("/")

        self.assertNotIn(TOKEN, response.text)
        self.assertNotIn("Hellas", response.text)


class AdvanceCatalogueTests(HttpTestCase):
    """Hinnat lasketaan palvelimella, jottei credits.py:tä toisteta JS:ssä."""

    def test_catalogue_lists_every_advance(self) -> None:
        body = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()

        self.assertEqual(len(body["advances"]), 51)
        first = body["advances"][0]
        self.assertEqual(
            set(first),
            {
                "id", "name", "cost", "vp", "groups", "owned", "locked",
                "effective_cost", "color_discount", "row_discount",
                "applied_group",
            },
        )

    def test_owned_cards_are_marked(self) -> None:
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["pottery", "masonry"]},
            headers=AUTH,
        )

        body = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()

        owned = {a["id"] for a in body["advances"] if a["owned"]}
        self.assertEqual(owned, {"pottery", "masonry"})

    def test_colour_credits_lower_the_effective_price(self) -> None:
        """Ostettu kortti antaa värikrediittiä, joka näkyy hinnoissa."""

        catalogue = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()
        before = {a["id"]: a["effective_cost"] for a in catalogue["advances"]}

        # Pottery antaa CRAFT 10 / ART 5, mutta vasta seuraavalla kierroksella:
        # saman kierroksen ostot eivät alenna toisiaan.
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["pottery"]},
            headers=AUTH,
        )
        self.client.post(
            "/turn", json={"round_number": 2, "current_phase": 12}, headers=AUTH
        )
        catalogue = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()
        after = {a["id"]: a["effective_cost"] for a in catalogue["advances"]}

        # 3 pelaajan pelissä alkukrediitti on 10 per väri, ja Pottery tuo
        # CRAFTiin 10 lisää. Endpoint laskee siis myös alkukrediitit mukaan.
        self.assertEqual(catalogue["credits"]["CRAFT"], 20)
        self.assertEqual(catalogue["credits"]["ART"], 15)
        # Cloth Making on CRAFT, joten sen hinta laski.
        self.assertLess(after["cloth_making"], before["cloth_making"])
        self.assertEqual(after["cloth_making"], 30)

    def test_row_chain_discount_is_reported_separately(self) -> None:
        """Referenssirivin 1 VP -> 3 VP antaa 10 lisäalennusta."""

        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism"]},
            headers=AUTH,
        )
        self.client.post(
            "/turn", json={"round_number": 2, "current_phase": 12}, headers=AUTH
        )

        body = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()
        monument = [a for a in body["advances"] if a["id"] == "monument"][0]

        self.assertEqual(monument["row_discount"], 10)

    def test_same_turn_purchases_do_not_discount_each_other(self) -> None:
        """Hankintavaihe on yhtäaikainen, myös useassa erässä kirjattuna."""

        self.client.post(
            "/turn", json={"round_number": 3, "current_phase": 12}, headers=AUTH
        )
        before = {
            a["id"]: a["effective_cost"]
            for a in self.client.get(
                "/players/Hellas/advances", headers=AUTH
            ).json()["advances"]
        }

        # Ensimmäinen erä: Mysticism (ART 5 / RELIGION 5, ja rivin 1 VP -kortti).
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism"]},
            headers=AUTH,
        )
        body = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()
        after = {a["id"]: a["effective_cost"] for a in body["advances"]}
        monument = [a for a in body["advances"] if a["id"] == "monument"][0]

        # Toinen erä samalla kierroksella näkee samat hinnat kuin ensimmäinen.
        self.assertEqual(after["monument"], before["monument"])
        self.assertEqual(monument["row_discount"], 0)
        # 3 pelaajan alkukrediitti on 10 per väri; Mysticismin RELIGION 5 ei
        # vielä näy, koska se ostettiin tällä kierroksella.
        self.assertEqual(body["credits"]["RELIGION"], 10)

        # Seuraavalla kierroksella alennus alkaa vaikuttaa.
        self.client.post(
            "/turn", json={"round_number": 4, "current_phase": 12}, headers=AUTH
        )
        later = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()
        monument = [a for a in later["advances"] if a["id"] == "monument"][0]
        self.assertEqual(monument["row_discount"], 10)
        self.assertEqual(later["credits"]["RELIGION"], 15)

    def test_flexible_credit_entitlement_is_reported(self) -> None:
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["written_record", "monument"]},
            headers=AUTH,
        )

        body = self.client.get(
            "/players/Hellas/advances", headers=AUTH
        ).json()

        self.assertEqual(body["flexible_total"], 30)

    def test_player_may_read_their_own_catalogue(self) -> None:
        store = TokenStore.create(
            ["Minoa", "Hatti", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(store)
        token = store.claim(store.join_code, "Hellas", "now")

        response = self.client.get(
            "/players/Hellas/advances",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)

    def test_unknown_civilization_is_404(self) -> None:
        self.assertEqual(
            self.client.get("/players/Atlantis/advances", headers=AUTH).status_code,
            404,
        )


class PermanentAdvanceTests(HttpTestCase):
    """Aiemman kierroksen kortti on ostettu; sitä ei voi perua puhelimelta."""

    def setUp(self) -> None:
        super().setUp()
        store = TokenStore.create(
            ["Minoa", "Hatti", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(store)
        self.player = {
            "Authorization": "Bearer "
            + store.claim(store.join_code, "Hellas", "now")
        }
        # Kierros 1: osta Mysticism. Kierros 2: se on pysyvä.
        self.client.post(
            "/turn", json={"round_number": 1, "current_phase": 12}, headers=AUTH
        )
        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism"]},
            headers=self.player,
        )
        self.client.post(
            "/turn", json={"round_number": 2, "current_phase": 12}, headers=AUTH
        )

    def test_catalogue_marks_earlier_cards_as_locked(self) -> None:
        body = self.client.get(
            "/players/Hellas/advances", headers=self.player
        ).json()

        locked = {a["id"] for a in body["advances"] if a["locked"]}
        self.assertEqual(locked, {"mysticism"})

    def test_player_cannot_drop_an_earlier_card(self) -> None:
        response = self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["pottery"]},
            headers=self.player,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("mysticism", response.json()["detail"])
        state = self.client.get("/state", headers=AUTH).json()
        hellas = [p for p in state["players"] if p["civilization"] == "Hellas"][0]
        self.assertEqual(hellas["advances"], ["mysticism"])

    def test_player_may_add_alongside_an_earlier_card(self) -> None:
        response = self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism", "pottery"]},
            headers=self.player,
        )

        self.assertEqual(response.status_code, 200)

    def test_player_may_undo_a_card_bought_this_turn(self) -> None:
        """Näppäilyvirheen on voitava korjata saman vaiheen aikana."""

        self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism", "pottery"]},
            headers=self.player,
        )

        response = self.client.post(
            "/players/Hellas/advances",
            json={"advances": ["mysticism"]},
            headers=self.player,
        )

        self.assertEqual(response.status_code, 200)

    def test_admin_may_correct_anything(self) -> None:
        response = self.client.post(
            "/players/Hellas/advances", json={"advances": []}, headers=AUTH
        )

        self.assertEqual(response.status_code, 200)


class ScopeTests(HttpTestCase):
    """Puhelin saa muuttaa vain omaa riviään ja vain sovituilla komennoilla."""

    def setUp(self) -> None:
        super().setUp()
        store = TokenStore.create(
            ["Minoa", "Hatti", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(store)
        self.store = store
        self.hellas = store.claim(store.join_code, "Hellas", "now")
        self.player = {"Authorization": f"Bearer {self.hellas}"}

    def test_player_may_change_their_own_row(self) -> None:
        # Census ja advances ovat vaihesidonnaisia; kaupungit eivät.
        for phase, route, body in (
            (1, "cities", {"value": 4}),
            (2, "census", {"value": 20}),
            (12, "advances", {"advances": ["pottery"]}),
        ):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            response = self.client.post(
                f"/players/Hellas/{route}", json=body, headers=self.player
            )
            self.assertEqual(response.status_code, 200, route)

    def test_advances_are_editable_only_in_phase_twelve(self) -> None:
        """Koko korttivalikoima kirjoitetaan kerralla, joten väärä vaihe pyyhkisi kortit."""

        allowed = []
        for phase in range(1, 14):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            if self.client.post(
                "/players/Hellas/advances",
                json={"advances": ["pottery"]},
                headers=self.player,
            ).status_code == 200:
                allowed.append(phase)

        self.assertEqual(allowed, [12])

    def test_cities_stay_editable_in_every_phase(self) -> None:
        """Kaupunkimäärä muuttuu myös konflikteissa ja calamityissä."""

        for phase in range(1, 14):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            self.assertEqual(
                self.client.post(
                    "/players/Hellas/cities",
                    json={"value": 3},
                    headers=self.player,
                ).status_code,
                200,
                f"phase {phase}",
            )

    def test_admin_may_correct_advances_in_any_phase(self) -> None:
        for phase in (1, 7, 13):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            self.assertEqual(
                self.client.post(
                    "/players/Hellas/advances",
                    json={"advances": ["pottery"]},
                    headers=AUTH,
                ).status_code,
                200,
                f"phase {phase}",
            )

    def test_census_is_editable_only_in_its_own_phases(self) -> None:
        """Census lasketaan laudalta vain vaiheessa 2."""

        allowed, blocked = [], []
        for phase in range(1, 14):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            status = self.client.post(
                "/players/Hellas/census",
                json={"value": 20 + phase},
                headers=self.player,
            ).status_code
            (allowed if status == 200 else blocked).append(phase)

        self.assertEqual(allowed, [2])
        self.assertEqual(len(blocked), 12)

    def test_blocked_census_does_not_change_anything(self) -> None:
        self.client.post(
            "/turn", json={"round_number": 1, "current_phase": 7}, headers=AUTH
        )

        response = self.client.post(
            "/players/Hellas/census", json={"value": 44}, headers=self.player
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("phase 7", response.json()["detail"])
        state = self.client.get("/state", headers=AUTH).json()
        hellas = [p for p in state["players"] if p["civilization"] == "Hellas"][0]
        self.assertEqual(hellas["census"], 0)

    def test_admin_may_correct_census_in_any_phase(self) -> None:
        """Pelinjohtajan on voitava korjata tieto milloin tahansa."""

        for phase in (1, 7, 13):
            self.client.post(
                "/turn",
                json={"round_number": 1, "current_phase": phase},
                headers=AUTH,
            )
            self.assertEqual(
                self.client.post(
                    "/players/Hellas/census", json={"value": 30}, headers=AUTH
                ).status_code,
                200,
                f"phase {phase}",
            )

    def test_state_tells_clients_the_phase_gates(self) -> None:
        body = self.client.get("/state", headers=AUTH).json()

        self.assertEqual(
            body["phase_gates"], {"census": [2], "advances": [12]}
        )
        self.assertNotIn("cities", body["phase_gates"])

    def test_player_cannot_touch_another_row(self) -> None:
        response = self.client.post(
            "/players/Minoa/cities", json={"value": 9}, headers=self.player
        )

        self.assertEqual(response.status_code, 403)
        # Mitään ei saanut muuttua.
        state = self.client.get("/state", headers=AUTH).json()
        minoa = [p for p in state["players"] if p["civilization"] == "Minoa"][0]
        self.assertEqual(minoa["cities"], 0)

    def test_player_cannot_move_their_own_ast_marker(self) -> None:
        """A.S.T.-askel on kannettavan yksinoikeus."""

        response = self.client.post(
            "/players/Hellas/ast-step", json={"value": 5}, headers=self.player
        )

        self.assertEqual(response.status_code, 403)

    def test_player_cannot_use_admin_commands(self) -> None:
        cases = (
            ("/players/Hellas/ast-bonus", {"value": True}),
            (
                "/players/Hellas/details",
                {
                    "nickname": "X",
                    "block": "WEST",
                    "cities": 1,
                    "ast_step": 1,
                    "census": 1,
                    "ast_bonus": False,
                },
            ),
            ("/turn", {"round_number": 2, "current_phase": 1}),
            ("/game", {"player_count": 0, "players": []}),
        )
        for path, body in cases:
            response = self.client.post(path, json=body, headers=self.player)
            self.assertEqual(response.status_code, 403, path)

    def test_player_may_read_the_whole_state(self) -> None:
        """Avoimen informaation peli: pistetilanne on TV:llä joka tapauksessa."""

        response = self.client.get("/state", headers=self.player)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["players"]), 3)

    def test_unknown_token_is_401_not_403(self) -> None:
        response = self.client.post(
            "/players/Hellas/cities",
            json={"value": 1},
            headers={"Authorization": "Bearer garbage"},
        )

        self.assertEqual(response.status_code, 401)

    def test_admin_is_not_restricted(self) -> None:
        for path, body in (
            ("/players/Hellas/ast-step", {"value": 5}),
            ("/players/Minoa/cities", {"value": 3}),
        ):
            self.assertEqual(
                self.client.post(path, json=body, headers=AUTH).status_code,
                200,
                path,
            )

    def test_new_game_mints_new_tokens(self) -> None:
        """Vanha puhelintoken ei saa jäädä voimaan uuteen peliin."""

        before = self.store.join_code
        payload = GameState(
            player_count=2,
            players=[
                PlayerState("Saba", "S", "EAST"),
                PlayerState("Persia", "P", "EAST"),
            ],
            game_mode="EAST",
        ).to_dict()

        self.client.post("/game", json=payload, headers=AUTH)

        response = self.client.post(
            "/players/Saba/cities", json={"value": 1}, headers=self.player
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(main.get_token_store().join_code, before)


class JoinFlowTests(HttpTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = TokenStore.create(
            ["Minoa", "Hatti", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(self.store)
        self.code = self.store.join_code
        main._join_failures.clear()

    def test_roster_needs_the_code(self) -> None:
        self.assertEqual(
            self.client.post("/join/roster", json={"code": "NOPE"}).status_code,
            403,
        )

    def test_roster_lists_free_and_taken_seats(self) -> None:
        self.store.claim(self.code, "Hatti", "now")

        body = self.client.post(
            "/join/roster", json={"code": self.code}
        ).json()

        self.assertEqual(
            {p["civilization"]: p["claimed"] for p in body["players"]},
            {"Minoa": False, "Hatti": True, "Hellas": False},
        )

    def test_roster_carries_colours_for_the_seat_list(self) -> None:
        body = self.client.post(
            "/join/roster", json={"code": self.code}
        ).json()

        colours = {p["civilization"]: p["color"] for p in body["players"]}
        self.assertEqual(colours["Hellas"], "#e5dd1e")
        self.assertEqual(colours["Minoa"], "#70b62c")

    def test_roster_shows_the_setup_nickname(self) -> None:
        """Nimi on vahvin tunniste juuri siinä hetkessä kun paikka valitaan."""

        self.client.post(
            "/players/Hellas/details",
            json={
                "nickname": "Matti",
                "block": "WEST",
                "cities": 0,
                "ast_step": 0,
                "census": 0,
                "ast_bonus": False,
            },
            headers=AUTH,
        )

        body = self.client.post(
            "/join/roster", json={"code": self.code}
        ).json()

        names = {p["civilization"]: p["nickname"] for p in body["players"]}
        self.assertEqual(names["Hellas"], "Matti")
        self.assertEqual(names["Minoa"], "A")

    def test_lobby_shows_nicknames_too(self) -> None:
        body = self.client.get("/admin/join", headers=AUTH).json()

        names = {p["civilization"]: p["nickname"] for p in body["players"]}
        self.assertEqual(names["Hellas"], "C")

    def test_joining_returns_a_working_token(self) -> None:
        response = self.client.post(
            "/join", json={"code": self.code, "civilization": "Hellas"}
        )

        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        write = self.client.post(
            "/players/Hellas/cities",
            json={"value": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(write.status_code, 200)

    def test_taken_seat_is_409_not_403(self) -> None:
        """Varattu paikka on tavallinen tilanne, ei tunkeutumisyritys."""

        self.client.post(
            "/join", json={"code": self.code, "civilization": "Hellas"}
        )

        response = self.client.post(
            "/join", json={"code": self.code, "civilization": "Hellas"}
        )

        self.assertEqual(response.status_code, 409)

    def test_wrong_code_does_not_claim(self) -> None:
        self.client.post(
            "/join", json={"code": "NOPE", "civilization": "Hellas"}
        )

        self.assertFalse(main.get_token_store().is_claimed("Hellas"))

    def test_repeated_wrong_codes_are_rate_limited(self) -> None:
        """Lyhyt koodi kestää arvailua vain jos yrityksiä rajoitetaan."""

        codes = [
            self.client.post("/join/roster", json={"code": "NOPE"}).status_code
            for _ in range(main.JOIN_MAX_FAILURES + 2)
        ]

        self.assertIn(429, codes)
        # Oikea koodikaan ei auta ennen kuin ikkuna umpeutuu.
        self.assertEqual(
            self.client.post(
                "/join/roster", json={"code": self.code}
            ).status_code,
            429,
        )

    def test_correct_codes_are_not_counted_against_the_limit(self) -> None:
        for _ in range(main.JOIN_MAX_FAILURES + 2):
            response = self.client.post(
                "/join/roster", json={"code": self.code}
            )
            self.assertEqual(response.status_code, 200)


class ElevatedPhoneTests(HttpTestCase):
    """Admin-koodilla liittynyt puhelin korjaa kenen tahansa rivin."""

    def setUp(self) -> None:
        super().setUp()
        self.store = TokenStore.create(
            ["Minoa", "Hatti", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(self.store)
        self.elevated = {
            "Authorization": "Bearer "
            + self.store.claim(self.store.admin_code, "Hellas", "now")
        }
        self.plain = {
            "Authorization": "Bearer "
            + self.store.claim(self.store.join_code, "Minoa", "now")
        }

    def _phase(self, phase: int, round_number: int = 1) -> None:
        self.client.post(
            "/turn",
            json={"round_number": round_number, "current_phase": phase},
            headers=AUTH,
        )

    def test_joining_with_the_admin_code_reports_the_elevation(self) -> None:
        store = TokenStore.create(
            ["Minoa", "Hatti"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(store)

        body = self.client.post(
            "/join", json={"code": store.admin_code, "civilization": "Hatti"}
        ).json()

        self.assertTrue(body["elevated"])
        self.assertEqual(body["civilization"], "Hatti")

    def test_the_roster_takes_either_code_and_says_which(self) -> None:
        """Yksi kenttä: liittyjän on nähtävä kumman koodin hän näppäili."""

        plain = self.client.post(
            "/join/roster", json={"code": self.store.join_code}
        ).json()
        admin = self.client.post(
            "/join/roster", json={"code": self.store.admin_code}
        ).json()

        self.assertFalse(plain["elevated"])
        self.assertTrue(admin["elevated"])
        # Sama lista kummallakin: korotus ei muuta sitä mitä paikkoja on.
        self.assertEqual(
            [p["civilization"] for p in plain["players"]],
            [p["civilization"] for p in admin["players"]],
        )

    def test_a_wrong_code_opens_nothing(self) -> None:
        wrong = "".join("A" if c != "A" else "B" for c in self.store.join_code)

        response = self.client.post("/join/roster", json={"code": wrong})

        self.assertEqual(response.status_code, 403)

    def test_elevated_phone_edits_another_row(self) -> None:
        self._phase(1)

        response = self.client.post(
            "/players/Minoa/cities", json={"value": 4}, headers=self.elevated
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["cities"], 4)

    def test_a_plain_phone_still_cannot(self) -> None:
        """Vertailukohta: korotus on se mikä eron tekee, ei liittyminen."""

        self._phase(1)

        response = self.client.post(
            "/players/Hellas/cities", json={"value": 4}, headers=self.plain
        )

        self.assertEqual(response.status_code, 403)

    def test_elevated_phone_bypasses_the_phase_gates(self) -> None:
        """Naapurin virhe huomataan yleensä vasta vaiheen jo vaihduttua."""

        self._phase(7)

        census = self.client.post(
            "/players/Minoa/census", json={"value": 20}, headers=self.elevated
        )
        advances = self.client.post(
            "/players/Minoa/advances",
            json={"advances": ["pottery"]},
            headers=self.elevated,
        )

        self.assertEqual(census.status_code, 200)
        self.assertEqual(advances.status_code, 200)

    def test_elevated_phone_may_drop_a_card_from_an_earlier_turn(self) -> None:
        self._phase(12, round_number=1)
        self.client.post(
            "/players/Minoa/advances",
            json={"advances": ["mysticism"]},
            headers=self.elevated,
        )
        self._phase(12, round_number=2)

        response = self.client.post(
            "/players/Minoa/advances",
            json={"advances": ["pottery"]},
            headers=self.elevated,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["advances"], ["pottery"])

    def test_the_catalogue_unlocks_earlier_cards_for_an_elevated_phone(
        self,
    ) -> None:
        """Lukitus on vihje POSTin säännöstä, joten sen on kertova sama asia.

        Muuten lista näyttäisi kortin lukittuna vaikka palvelin ottaisi
        muutoksen vastaan, ja korjaus näyttäisi mahdottomalta.
        """

        self._phase(12, round_number=1)
        self.client.post(
            "/players/Minoa/advances",
            json={"advances": ["mysticism"]},
            headers=self.elevated,
        )
        self._phase(12, round_number=2)

        mine = self.client.get(
            "/players/Minoa/advances", headers=self.elevated
        ).json()
        theirs = self.client.get(
            "/players/Minoa/advances", headers=self.plain
        ).json()

        self.assertEqual([a for a in mine["advances"] if a["locked"]], [])
        # Tavalliselle puhelimelle sama kortti on yhä lukittu.
        self.assertEqual(
            {a["id"] for a in theirs["advances"] if a["locked"]}, {"mysticism"}
        )

    def test_elevation_stops_at_the_ast_and_the_turn(self) -> None:
        """Korotus laajentaa rivejä, ei komentoja."""

        details = {
            "nickname": "Matti",
            "block": "WEST",
            "cities": 1,
            "ast_step": 1,
            "census": 0,
            "ast_bonus": False,
        }
        for route, body in (
            ("players/Hellas/ast-step", {"value": 3}),
            ("players/Minoa/ast-step", {"value": 3}),
            ("players/Hellas/details", details),
        ):
            response = self.client.post(
                f"/{route}", json=body, headers=self.elevated
            )
            self.assertEqual(response.status_code, 403, route)

        turn = self.client.post(
            "/turn",
            json={"round_number": 2, "current_phase": 1},
            headers=self.elevated,
        )
        self.assertEqual(turn.status_code, 403)

    def test_state_tells_the_phone_that_it_is_elevated(self) -> None:
        """Puhelin ei voi päätellä korotustaan mistään muualta."""

        mine = self.client.get("/state", headers=self.elevated).json()["you"]
        theirs = self.client.get("/state", headers=self.plain).json()["you"]

        self.assertTrue(mine["elevated"])
        self.assertEqual(mine["civilization"], "Hellas")
        self.assertFalse(mine["admin"])
        self.assertFalse(theirs["elevated"])

    def test_releasing_the_seat_ends_the_elevation(self) -> None:
        """Vapautus on ainoa tapa perua korotus kesken pelin."""

        self.client.post(
            "/admin/release", json={"civilization": "Hellas"}, headers=AUTH
        )
        self._phase(1)

        response = self.client.post(
            "/players/Minoa/cities", json={"value": 4}, headers=self.elevated
        )

        # 403 eikä 401: token itsessään kelpaa yhä — vapautus vapauttaa paikan
        # eikä mitätöi tokenia — mutta korotus on poissa, joten toisen rivi ei
        # enää aukea.
        self.assertEqual(response.status_code, 403)

    def test_lobby_reports_the_admin_code_and_who_is_elevated(self) -> None:
        body = self.client.get("/admin/join", headers=AUTH).json()

        self.assertEqual(body["admin_code"], self.store.admin_code)
        self.assertNotEqual(body["admin_code"], body["join_code"])
        elevated = {
            p["civilization"] for p in body["players"] if p["elevated"]
        }
        self.assertEqual(elevated, {"Hellas"})


class AdminLobbyTests(HttpTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = TokenStore.create(
            ["Minoa", "Hellas"], tokens_path(Path(self._directory.name))
        )
        main.set_token_store(self.store)

    def test_admin_sees_the_code_and_who_joined(self) -> None:
        self.store.claim(self.store.join_code, "Hellas", "now")

        body = self.client.get("/admin/join", headers=AUTH).json()

        self.assertEqual(body["join_code"], self.store.join_code)
        self.assertEqual(
            {p["civilization"]: p["claimed"] for p in body["players"]},
            {"Minoa": False, "Hellas": True},
        )

    def test_players_cannot_read_the_lobby(self) -> None:
        token = self.store.claim(self.store.join_code, "Hellas", "now")

        response = self.client.get(
            "/admin/join", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 403)

    def test_release_lets_the_seat_be_claimed_again(self) -> None:
        """Puhelimen vaihto ei saa lukita pelaajaa ulos."""

        self.store.claim(self.store.join_code, "Hellas", "now")

        released = self.client.post(
            "/admin/release", json={"civilization": "Hellas"}, headers=AUTH
        )
        rejoin = self.client.post(
            "/join",
            json={"code": self.store.join_code, "civilization": "Hellas"},
        )

        self.assertEqual(released.status_code, 200)
        self.assertEqual(rejoin.status_code, 200)

    def test_release_of_an_unknown_civilization_is_404(self) -> None:
        response = self.client.post(
            "/admin/release", json={"civilization": "Atlantis"}, headers=AUTH
        )

        self.assertEqual(response.status_code, 404)


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

    def test_create_archives_the_previous_game(self) -> None:
        """Uusi peli ei saa hävittää käynnissä olevaa lopullisesti."""

        self.client.post(
            "/players/Hellas/cities", json={"value": 6}, headers=AUTH
        )
        directory = Path(self._directory.name)
        live = directory / "nykyinen_peli.json"
        # Aja komento myös oletuspolkuun, jotta arkistoitavaa on.
        self.client.post("/game", json=self._payload(), headers=AUTH)
        self.client.post(
            "/players/Saba/cities", json={"value": 3}, headers=AUTH
        )

        response = self.client.post("/game", json=self._payload(), headers=AUTH)

        archived = response.json()["archived"]
        self.assertIsNotNone(archived)
        self.assertTrue((directory / archived).is_file())
        previous = json.loads((directory / archived).read_text(encoding="utf-8"))
        saba = [p for p in previous["players"] if p["civilization"] == "Saba"][0]
        self.assertEqual(saba["cities"], 3)
        # Uusi peli alkaa puhtaalta pöydältä.
        self.assertEqual(
            json.loads(live.read_text(encoding="utf-8"))["state_version"], 0
        )

    def test_first_game_has_nothing_to_archive(self) -> None:
        (Path(self._directory.name) / "nykyinen_peli.json").unlink(
            missing_ok=True
        )

        response = self.client.post("/game", json=self._payload(), headers=AUTH)

        self.assertIsNone(response.json()["archived"])

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
