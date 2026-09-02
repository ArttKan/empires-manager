"""A `GameService` implementation over HTTP.

The desktop app uses this when the game lives on the server. The interface is
the same as `LocalGameService`'s, so `ui.py` does not know which one it holds.

**Standard library only.** The server has a venv with httpx in it, but the
desktop app must start under bare `python3` without the venv — that is the
whole precondition for the local fallback. Hence `urllib.request` here rather
than httpx.

The calls are synchronous and therefore blocking. The timeout is deliberately
short: when the network drops, a button press may freeze the UI for at most
that long. The alternative would be a background thread, which would bring
threading into the desktop app for the sake of one rare failure case.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..core.models import GameState, PlayerState
from ..service import (
    CommandError,
    CommandResult,
    GameService,
    RuleViolation,
    ServiceUnavailable,
    UnknownPlayer,
    VersionConflict,
)

DEFAULT_TIMEOUT = 3.0

# Cloudflare rejects urllib's default "Python-urllib/3.x" header with error
# 1010 ("browser signature banned"), so every request would come back 403.
# It is enough for the app to say honestly who it is — no need to pose as a
# browser. This never shows up in the tests, because they talk straight to
# 127.0.0.1 and never traverse Cloudflare.
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

    # -- reading ------------------------------------------------------------

    def snapshot(self) -> GameState:
        data = self._request("GET", "/state")
        # `claimed` is not game state and does not survive in GameState, so it is
        # cached here. That way the scoreboard can show who has a phone without a
        # second request.
        self._claims = {
            str(entry["civilization"]): bool(entry.get("claimed"))
            for entry in data.get("players", [])
        }
        return GameState.from_dict(data)

    def claims(self) -> dict:
        """Civilization -> whether the seat is claimed, from the latest snapshot."""

        return dict(getattr(self, "_claims", {}))

    # -- commands -----------------------------------------------------------

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
        """Install a game on the server and return the new state_version.

        Not part of the `GameService` interface: in local mode a new game is
        created as a file, not by a command.
        """

        data = self._request("POST", "/game", game.to_dict())
        return int(data["state_version"])

    # -- administration ------------------------------------------------------
    #
    # These are not part of the `GameService` interface: in local mode there is
    # no joining and there are no tokens, so they would have no counterpart.

    def join_status(self) -> dict:
        """The join code and the state of the seats, for the lobby view."""

        return self._request("GET", "/admin/join")

    def release_seat(self, civilization: str) -> dict:
        """Free a seat to be claimed again.

        Needed when a phone is swapped or a browser's data is cleared. The
        player has no such button themselves: pressed by accident it would lock
        them out mid-game.
        """

        return self._request(
            "POST", "/admin/release", {"civilization": civilization}
        )

    # -- internals -----------------------------------------------------------

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
            # Network error, DNS, timeout, or garbage in the response.
            raise ServiceUnavailable(
                f"Could not reach the game server at {self.base_url}: {error}"
            ) from error

    @staticmethod
    def _translate(error: urllib.error.HTTPError) -> CommandError:
        """Map a server status code back to the same exception type.

        That way `ui.py` handles a remote 422 exactly as it handles a local
        `RuleViolation`, and never needs to know about HTTP.
        """

        # HTTPError is a file-like object: it has to be closed, or handles pile up
        # in a long-running desktop app.
        try:
            detail = json.loads(error.read().decode("utf-8")).get("detail")
        except Exception:  # pragma: no cover - the response was not JSON
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
