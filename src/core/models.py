"""Data models for the persisted game state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .data import ADVANCE_GROUPS, AST_MAX_STEP, default_block


@dataclass(slots=True)
class PlayerState:
    civilization: str
    nickname: str
    block: str
    cities: int = 0
    ast_step: int = 0
    advances: list[str] = field(default_factory=list)
    ast_bonus: bool = False
    census: int = 0
    flexible_credits: dict[str, int] = field(default_factory=dict)
    # Advance id -> the turn it was acquired on. Needed because purchases made on
    # the same turn do not discount each other: acquisition is simultaneous.
    advance_turns: dict[str, int] = field(default_factory=dict)
    # Incremented on every accepted command. A client sends the value it knows
    # along with the write, so a stale write can be rejected instead of
    # overwriting the change another player just made.
    version: int = 0

    @property
    def display_name(self) -> str:
        nickname = self.nickname.strip()
        return f"{self.civilization} ({nickname})" if nickname else self.civilization

    def normalize(self) -> None:
        self.nickname = self.nickname.strip()
        self.block = self.block.upper()
        if self.block == "YHTEINEN":
            self.block = "SINGLE"
        if self.block not in {"WEST", "EAST", "SINGLE"}:
            self.block = "WEST"
        self.cities = max(0, min(9, int(self.cities)))
        self.ast_step = max(0, min(AST_MAX_STEP, int(self.ast_step)))
        self.census = max(0, min(55, int(self.census)))
        self.advances = list(dict.fromkeys(self.advances))
        # Stamps for owned cards only; the stamp of a discarded card is garbage.
        self.advance_turns = {
            advance_id: max(0, int(turn))
            for advance_id, turn in self.advance_turns.items()
            if advance_id in set(self.advances)
        }
        self.ast_bonus = bool(self.ast_bonus)
        self.version = max(0, int(self.version))
        self.flexible_credits = {
            group: max(0, int(self.flexible_credits.get(group, 0)))
            for group in ADVANCE_GROUPS
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerState":
        player = cls(
            civilization=str(data["civilization"]),
            nickname=str(data.get("nickname", "")),
            block=str(data.get("block", "WEST")),
            cities=int(data.get("cities", 0)),
            ast_step=int(data.get("ast_step", 0)),
            advances=[str(value) for value in data.get("advances", [])],
            ast_bonus=bool(data.get("ast_bonus", False)),
            census=int(data.get("census", 0)),
            version=int(data.get("version", 0)),
            flexible_credits={
                str(group): int(value)
                for group, value in data.get("flexible_credits", {}).items()
            },
            advance_turns={
                str(advance_id): int(turn)
                for advance_id, turn in data.get("advance_turns", {}).items()
            },
        )
        player.normalize()
        return player


@dataclass(slots=True)
class GameState:
    player_count: int
    players: list[PlayerState]
    game_mode: str = "BOTH"
    ast_variant: str = "BASIC"
    round_number: int = 1
    current_phase: int = 1
    # NOTE: `version` is the save format version, not the game state version.
    # `state_version` is the global counter a client uses to tell whether the
    # snapshot it holds has gone stale.
    version: int = 6
    state_version: int = 0
    saved_at: str = ""

    def normalize(self) -> None:
        self.player_count = len(self.players)
        self.game_mode = self.game_mode.upper()
        if self.game_mode not in {"WEST", "EAST", "BOTH"}:
            self.game_mode = "BOTH" if self.player_count >= 10 else "WEST"
        self.ast_variant = self.ast_variant.upper()
        if self.ast_variant not in {"BASIC", "EXPERT"}:
            self.ast_variant = "BASIC"
        self.round_number = max(1, int(self.round_number))
        self.current_phase = max(1, min(13, int(self.current_phase)))
        self.state_version = max(0, int(self.state_version))
        for player in self.players:
            player.normalize()

    def to_dict(self) -> dict[str, Any]:
        self.normalize()
        self.saved_at = datetime.now().astimezone().isoformat(timespec="seconds")
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        source_version = int(data.get("version", 1))
        players = [
            PlayerState.from_dict(player_data)
            for player_data in data.get("players", [])
        ]
        game = cls(
            player_count=int(data.get("player_count", len(players))),
            players=players,
            game_mode=str(
                data.get(
                    "game_mode",
                    "BOTH" if len(players) >= 10 else "WEST",
                )
            ),
            ast_variant=str(data.get("ast_variant", "BASIC")),
            round_number=int(data.get("round_number", 1)),
            current_phase=int(data.get("current_phase", 1)),
            version=6,
            state_version=int(data.get("state_version", 0)),
            saved_at=str(data.get("saved_at", "")),
        )
        if source_version < 2:
            for player in game.players:
                player.block = default_block(
                    player.civilization,
                    game.player_count,
                )
        game.normalize()
        return game
