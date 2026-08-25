"""`GameService`-toteutus HTTP:n yli.

Työpöytäsovellus käyttää tätä silloin kun peli on palvelimella. Rajapinta on
sama kuin `LocalGameService`:llä, joten `ui.py` ei tiedä kumpaa se pitelee.

**Vain vakiokirjastoa.** Palvelimella on venv jossa on httpx, mutta
työpöytäsovelluksen on käynnistyttävä pelkällä `python3`:lla ilman venviä —
se on koko paikallisen varajärjestelmän edellytys. Siksi täällä käytetään
`urllib.request`ia eikä httpx:ää.

Kutsut ovat synkronisia ja siis estäviä. Aikakatkaisu on tarkoituksella lyhyt:
verkon katketessa napin painallus saa jumittaa käyttöliittymän korkeintaan sen
verran. Vaihtoehto olisi taustasäie, mikä toisi säikeistyksen työpöytäsovellukseen
pelkän harvinaisen virhetilanteen vuoksi.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import GameState, PlayerState
from .service import (
    CommandError,
    CommandResult,
    GameService,
    RuleViolation,
    ServiceUnavailable,
    UnknownPlayer,
    VersionConflict,
)

DEFAULT_TIMEOUT = 3.0

# Cloudflare torjuu urllibin oletusotsakkeen "Python-urllib/3.x" virhekoodilla
# 1010 ("browser signature banned"), joten jokainen pyyntö palautuisi 403:na.
# Riittää, että sovellus kertoo rehellisesti kuka on — selaimeksi ei tarvitse
# tekeytyä. Tämä ei paljastu testeissä, koska ne puhuvat suoraan 127.0.0.1:lle
# eivätkä kulje Cloudflaren läpi.
USER_AGENT = "MegaEmpires-Desktop/1.0 (+https://empiresmanager.com)"


class RemoteGameService(GameService):
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # -- luku ---------------------------------------------------------------

    def snapshot(self) -> GameState:
        data = self._request("GET", "/state")
        # `claimed` ei kuulu pelitilaan eikä säily GameStatessa, joten se
        # otetaan talteen tässä. Näin pistetaulu voi näyttää kenellä on puhelin
        # ilman erillistä kutsua.
        self._claims = {
            str(entry["civilization"]): bool(entry.get("claimed"))
            for entry in data.get("players", [])
        }
        return GameState.from_dict(data)

    def claims(self) -> dict:
        """Sivilisaatio -> onko paikka varattu, viimeisimmästä tilannekuvasta."""

        return dict(getattr(self, "_claims", {}))

    # -- komennot -----------------------------------------------------------

    def set_cities(
        self,
        civilization: str,
        cities: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "cities",
            {"value": int(cities)},
            expected_version,
            actor,
        )

    def set_census(
        self,
        civilization: str,
        census: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "census",
            {"value": int(census)},
            expected_version,
            actor,
        )

    def set_ast_step(
        self,
        civilization: str,
        ast_step: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "ast-step",
            {"value": int(ast_step)},
            expected_version,
            actor,
        )

    def set_ast_bonus(
        self,
        civilization: str,
        granted: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "ast-bonus",
            {"value": bool(granted)},
            expected_version,
            actor,
        )

    def set_advances(
        self,
        civilization: str,
        advances: list[str],
        flexible_credits: dict[str, int] | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "advances",
            {
                "advances": list(advances),
                "flexible_credits": flexible_credits,
            },
            expected_version,
            actor,
        )

    def set_player_details(
        self,
        civilization: str,
        nickname: str,
        block: str,
        cities: int,
        ast_step: int,
        census: int,
        ast_bonus: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        return self._command(
            civilization,
            "details",
            {
                "nickname": nickname,
                "block": block,
                "cities": int(cities),
                "ast_step": int(ast_step),
                "census": int(census),
                "ast_bonus": bool(ast_bonus),
            },
            expected_version,
            actor,
        )

    def set_turn(
        self,
        round_number: int,
        current_phase: int,
        expected_state_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        payload = {
            "round_number": int(round_number),
            "current_phase": int(current_phase),
            "expected_state_version": expected_state_version,
            "actor": actor or "desktop",
        }
        return self._result(self._request("POST", "/turn", payload))

    def create_game(self, game: GameState) -> int:
        """Asenna peli palvelimelle ja palauta uusi state_version.

        Ei ole osa `GameService`-rajapintaa: paikallisessa tilassa uusi peli
        syntyy tiedostoon, ei komennolla.
        """

        data = self._request("POST", "/game", game.to_dict())
        return int(data["state_version"])

    # -- ylläpito ------------------------------------------------------------
    #
    # Nämä eivät kuulu `GameService`-rajapintaan: paikallisessa tilassa ei ole
    # liittymistä eikä tokeneita, joten niillä ei olisi vastinetta.

    def join_status(self) -> dict:
        """Liittymiskoodi ja paikkojen tila aulanäkymää varten."""

        return self._request("GET", "/admin/join")

    def release_seat(self, civilization: str) -> dict:
        """Vapauta paikka uudelleen varattavaksi.

        Tarvitaan kun puhelin vaihtuu tai selaimen tiedot tyhjenevät. Pelaajalla
        itsellään ei ole tätä: vahingossa painettuna se lukitsisi hänet ulos
        kesken pelin.
        """

        return self._request(
            "POST", "/admin/release", {"civilization": civilization}
        )

    # -- sisäiset ------------------------------------------------------------

    def _command(
        self,
        civilization: str,
        route: str,
        payload: dict,
        expected_version: int | None,
        actor: str,
    ) -> CommandResult:
        body = dict(payload)
        body["expected_version"] = expected_version
        body["actor"] = actor or "desktop"
        path = f"/players/{urllib.parse.quote(civilization)}/{route}"
        return self._result(self._request("POST", path, body))

    @staticmethod
    def _result(data: dict) -> CommandResult:
        player = data.get("player")
        return CommandResult(
            state_version=int(data["state_version"]),
            player=PlayerState.from_dict(player) if player else None,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> Any:
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "User-Agent": USER_AGENT,
            },
        )
        if payload is not None:
            request.add_header("Content-Type", "application/json")
            request.data = json.dumps(payload).encode("utf-8")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise self._translate(error) from error
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
            # Verkkovirhe, DNS, aikakatkaisu tai roskaa vastauksessa.
            raise ServiceUnavailable(
                f"Could not reach the game server at {self.base_url}: {error}"
            ) from error

    @staticmethod
    def _translate(error: urllib.error.HTTPError) -> CommandError:
        """Käännä palvelimen statuskoodi takaisin samaksi poikkeukseksi.

        Näin `ui.py` käsittelee etäpalvelun 422:n täsmälleen samoin kuin
        paikallisen `RuleViolation`in eikä sen tarvitse tuntea HTTP:tä.
        """

        # HTTPError on tiedostomainen olio: se on suljettava, tai kahvat
        # kertyvät pitkään ajossa olevassa työpöytäsovelluksessa.
        try:
            detail = json.loads(error.read().decode("utf-8")).get("detail")
        except Exception:  # pragma: no cover - vastaus ei ollut JSONia
            detail = None
        finally:
            error.close()
        message = detail if isinstance(detail, str) else str(detail or error)

        if error.code == 404:
            return UnknownPlayer(message)
        if error.code == 409 and isinstance(detail, dict):
            return VersionConflict(
                int(detail.get("expected_version", -1)),
                int(detail.get("current_version", -1)),
            )
        if error.code == 422:
            return RuleViolation(message)
        if error.code == 503:
            return ServiceUnavailable(message)
        if error.code in (401, 403):
            return ServiceUnavailable(f"Authentication failed: {message}")
        return CommandError(f"HTTP {error.code}: {message}")
