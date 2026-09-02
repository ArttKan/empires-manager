"""The command interface to the game state.

`GameService` is the only thing allowed to mutate a `GameState`. The UI and the
HTTP layer are both its clients and never touch the dataclasses directly.

The interface is defined so that it can also be implemented over the network:

* commands take an **absolute value**, not a delta. Two concurrent "+1"s would
  both succeed and add two cities, though the user only saw one. An absolute
  value together with the `expected_version` check rejects a stale write
  instead of letting it overwrite someone else's change;
* commands **return a value, not a reference** to internal state. An
  implementation working over the network cannot return a live object, so the
  local one must not either.

The module is deliberately standard library only: the desktop app has to work
without the venv and without FastAPI.
"""

from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .core.models import GameState, PlayerState
from .storage import save_game


class CommandError(Exception):
    """The command was not accepted. The HTTP layer maps subclasses to statuses."""


class UnknownPlayer(CommandError):
    """No such civilization in this game (HTTP 404)."""


class VersionConflict(CommandError):
    """The version the client knows is stale (HTTP 409).

    The client must fetch a fresh snapshot and try again; the command must
    never be retried automatically with the old value.
    """

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"Expected version {expected} but the current version is {actual}."
        )
        self.expected = expected
        self.actual = actual


class RuleViolation(CommandError):
    """The command would break a game rule (HTTP 422)."""


class ServiceUnavailable(CommandError):
    """The service could not be reached, or has no game (HTTP 503).

    Kept separate because the UI has to behave differently: a rejected command
    is the user's mistake, a dropped connection is not. In the latter case the
    view is left as it is and never read as a change of game state.
    """


@dataclass(frozen=True)
class CommandResult:
    """The result of a command. `player` is a copy, not a reference to state."""

    state_version: int
    player: PlayerState | None = None


class GameService(ABC):
    """The interface implemented by both the local and the HTTP versions."""

    @abstractmethod
    def snapshot(self) -> GameState:
        """Return the whole game state as a copy."""

    @abstractmethod
    def set_cities(
        self,
        civilization: str,
        cities: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Set the player's city count as an absolute value."""

    @abstractmethod
    def set_census(
        self,
        civilization: str,
        census: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Set the player's Census as an absolute value."""

    @abstractmethod
    def set_ast_bonus(
        self,
        civilization: str,
        granted: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Confirm or withdraw the end-game A.S.T. bonus."""

    @abstractmethod
    def set_ast_step(
        self,
        civilization: str,
        ast_step: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Set the player's A.S.T. step as an absolute value."""

    @abstractmethod
    def set_advances(
        self,
        civilization: str,
        advances: list[str],
        flexible_credits: dict[str, int] | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Replace the player's Advances and flexible credits."""

    @abstractmethod
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
        """Set the Details dialog's fields as one atomic command."""

    @abstractmethod
    def set_turn(
        self,
        round_number: int,
        current_phase: int,
        expected_state_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Set the turn and phase. A game-level command, not a per-player one."""


def validate_ast_bonus(
    game: GameState,
    civilization: str,
    granted: bool,
) -> None:
    """Check the scenario's A.S.T. bonus rules.

    This used to live in `PlayerDialog._save` in `ui.py`, where the rule
    applied to no other client. Lifting it here is the whole idea of Phase B in
    miniature: a rule belongs in the core, not in one dialog.

    Below 12 players only one player may receive the bonus. In a 12+ player
    combined game there may be at most two recipients, and they must be in
    different trade blocks.
    """

    if not granted:
        return

    others = [
        player
        for player in game.players
        if player.civilization != civilization and player.ast_bonus
    ]
    if not others:
        return

    if game.player_count <= 11:
        raise RuleViolation(
            "The A.S.T. end-game bonus can be confirmed for only one player "
            "in this game."
        )
    if len(others) >= 2:
        raise RuleViolation(
            "The bonus can be confirmed for no more than two players in a "
            "combined game."
        )

    player = _find_player(game, civilization)
    if others[0].block == player.block:
        raise RuleViolation(
            "Two bonus recipients must belong to different trade blocks."
        )


def _find_player(game: GameState, civilization: str) -> PlayerState:
    for player in game.players:
        if player.civilization == civilization:
            return player
    raise UnknownPlayer(f"No player for civilization {civilization!r}.")


class LocalGameService(GameService):
    """The in-process implementation that owns the state and writes to disk.

    The desktop app uses this directly; on the server the HTTP layer wraps it.
    Writes serialise because there is exactly one writing process.
    """

    def __init__(
        self,
        game: GameState,
        save_path: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        game.normalize()
        self._game = game
        self._save_path = save_path
        self._log_path = (
            log_path
            if log_path is not None
            else (save_path.with_suffix(".jsonl") if save_path else None)
        )

    # -- reading ------------------------------------------------------------

    def snapshot(self) -> GameState:
        return copy.deepcopy(self._game)

    @property
    def state_version(self) -> int:
        return self._game.state_version

    def save(self) -> None:
        """Write the snapshot to disk without a command.

        Needed when a game is installed as-is (a new game), where no command
        has run but the state still has to be persisted.
        """

        self._save()

    # -- commands -----------------------------------------------------------

    def set_cities(
        self,
        civilization: str,
        cities: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.cities = int(cities)
        return self._commit(
            player,
            "set_cities",
            {"civilization": civilization, "cities": player.cities},
            actor,
        )

    def set_census(
        self,
        civilization: str,
        census: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.census = int(census)
        return self._commit(
            player,
            "set_census",
            {"civilization": civilization, "census": player.census},
            actor,
        )

    def set_ast_bonus(
        self,
        civilization: str,
        granted: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        validate_ast_bonus(self._game, civilization, bool(granted))
        player.ast_bonus = bool(granted)
        return self._commit(
            player,
            "set_ast_bonus",
            {"civilization": civilization, "granted": player.ast_bonus},
            actor,
        )

    def set_ast_step(
        self,
        civilization: str,
        ast_step: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.ast_step = int(ast_step)
        return self._commit(
            player,
            "set_ast_step",
            {"civilization": civilization, "ast_step": player.ast_step},
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
        player = self._checked_player(civilization, expected_version)
        # New cards are stamped with the current turn. Existing stamps are kept, so
        # a purchase recorded in several batches does not move them forward.
        previous = set(player.advances)
        turn = self._game.round_number
        player.advances = list(advances)
        for advance_id in player.advances:
            if advance_id not in previous:
                player.advance_turns[advance_id] = turn
        if flexible_credits is not None:
            player.flexible_credits = dict(flexible_credits)
        return self._commit(
            player,
            "set_advances",
            {
                "civilization": civilization,
                "advances": list(player.advances),
                "flexible_credits": dict(player.flexible_credits),
            },
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
        """The Details dialog saves all of its fields at once.

        One command rather than six: the user's action is one, so the version
        bump, the log line and any future undo are one as well.
        """

        player = self._checked_player(civilization, expected_version)
        validate_ast_bonus(self._game, civilization, bool(ast_bonus))
        player.nickname = str(nickname)
        player.block = str(block)
        player.cities = int(cities)
        player.ast_step = int(ast_step)
        player.census = int(census)
        player.ast_bonus = bool(ast_bonus)
        return self._commit(
            player,
            "set_player_details",
            {
                "civilization": civilization,
                "nickname": player.nickname,
                "block": player.block,
                "cities": player.cities,
                "ast_step": player.ast_step,
                "census": player.census,
                "ast_bonus": player.ast_bonus,
            },
            actor,
        )

    def set_turn(
        self,
        round_number: int,
        current_phase: int,
        expected_state_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        if (
            expected_state_version is not None
            and expected_state_version != self._game.state_version
        ):
            raise VersionConflict(
                expected_state_version, self._game.state_version
            )
        self._game.round_number = int(round_number)
        self._game.current_phase = int(current_phase)
        self._game.normalize()
        self._game.state_version += 1
        self._append_log(
            "set_turn",
            {
                "round_number": self._game.round_number,
                "current_phase": self._game.current_phase,
            },
            actor,
            None,
        )
        self._save()
        return CommandResult(state_version=self._game.state_version)

    # -- internals -----------------------------------------------------------

    def _checked_player(
        self,
        civilization: str,
        expected_version: int | None,
    ) -> PlayerState:
        player = _find_player(self._game, civilization)
        if expected_version is not None and expected_version != player.version:
            raise VersionConflict(expected_version, player.version)
        return player

    def _commit(
        self,
        player: PlayerState,
        command: str,
        arguments: dict,
        actor: str,
    ) -> CommandResult:
        """Normalize, bump the versions, append the log and save the snapshot.

        `normalize()` runs only here, so that an out-of-range value is clamped
        the same way no matter which client sent it.
        """

        player.normalize()
        player.version += 1
        self._game.state_version += 1
        self._append_log(command, arguments, actor, player)
        self._save()
        return CommandResult(
            state_version=self._game.state_version,
            player=copy.deepcopy(player),
        )

    def _append_log(
        self,
        command: str,
        arguments: dict,
        actor: str,
        player: PlayerState | None,
    ) -> None:
        """Append a line to the command log.

        The log is append-only: it gives an audit trail ("who changed what and
        when") that is far more useful with sixteen writers than with one, and
        it is the substrate for a one-step undo.
        """

        if self._log_path is None:
            return
        entry = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "actor": actor,
            "command": command,
            "arguments": arguments,
            "state_version": self._game.state_version,
            "player_version": player.version if player is not None else None,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _save(self) -> None:
        if self._save_path is None:
            return
        save_game(self._game, self._save_path)
