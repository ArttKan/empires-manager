"""Per-player tokens and the join flow.

The tokens are kept out of `GameState` deliberately. Game state is serialised
into saves, next to the command log and into the laptop's mirror copy; if the
tokens were in it, every player's secret would leak into all of those places.
This file exists only on the server.

The permission model is deliberately coarse, because the group is small and
known to each other:

* **admin** — the laptop. May do anything.
* **player** — a phone. May change only its own civilization's cities, Census
  and Advances. A.S.T. step, bonus, turn and new game are admin-only.
* **elevated player** — a phone that joined with the admin code as well. Claims
  its own seat normally, but may change those same three fields on anyone's
  row, and bypasses the phase gates as the laptop does. A.S.T. and the turn
  still stay on the laptop: elevation is the game master's tool for fixing a
  neighbour's row, not a second full admin.

Standard library only.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

# The join code is read aloud at the table, so characters that are confused in
# speech or on screen are left out (0/O, 1/I/L).
_JOIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 5
TOKEN_BYTES = 16

TOKENS_FILENAME = "tokens.json"

ADMIN = "admin"
PLAYER = "player"

# The routes a phone may call. The A.S.T. step is deliberately absent: it
# decides the outcome of the game and stays on the laptop.
PLAYER_COMMANDS = frozenset({"cities", "census", "advances"})


@dataclass(frozen=True, slots=True)
class Principal:
    kind: str
    civilization: str = ""
    # An elevated player: own seat claimed, but write access to everyone's rows.
    # This does not make them an admin — `is_admin` still decides the A.S.T., the
    # turn, a new game and the lobby.
    elevated: bool = False

    @property
    def is_admin(self) -> bool:
        return self.kind == ADMIN

    @property
    def bypasses_gates(self) -> bool:
        """Whether the phase gates and card permanence may be bypassed.

        An elevated phone may, because the whole point of elevation is to fix
        someone else's row when it is wrong — and wrong is usually noticed only
        once the phase has already moved on.
        """

        return self.is_admin or self.elevated

    def may_command(self, civilization: str, command: str) -> bool:
        if self.is_admin:
            return True
        if command not in PLAYER_COMMANDS:
            return False
        return self.elevated or civilization == self.civilization


def tokens_path(directory: Path) -> Path:
    return directory / TOKENS_FILENAME


class TokenStore:
    """The per-civilization tokens and the state of joining."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self._data = data

    # -- creation and loading -----------------------------------------------

    @staticmethod
    def _code() -> str:
        return "".join(
            secrets.choice(_JOIN_ALPHABET) for _ in range(JOIN_CODE_LENGTH)
        )

    @classmethod
    def create(cls, civilizations, path: Path) -> "TokenStore":
        join_code = cls._code()
        admin_code = cls._code()
        # Drawing the same code twice is unlikely but not impossible, and then every
        # player joining would be elevated by accident.
        while admin_code == join_code:
            admin_code = cls._code()
        data = {
            "join_code": join_code,
            "admin_code": admin_code,
            "players": {
                name: {
                    "token": secrets.token_urlsafe(TOKEN_BYTES),
                    "claimed_at": None,
                    "elevated": False,
                }
                for name in civilizations
            },
        }
        store = cls(path, data)
        store.save()
        return store

    @classmethod
    def load(cls, path: Path) -> "TokenStore | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or "players" not in data:
            return None
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # The tokens are secrets: owner-read only.
        temporary.chmod(0o600)
        temporary.replace(self.path)

    # -- queries ------------------------------------------------------------

    @property
    def join_code(self) -> str:
        return str(self._data.get("join_code", ""))

    def civilizations(self) -> tuple:
        return tuple(self._data.get("players", {}))

    @property
    def admin_code(self) -> str:
        return str(self._data.get("admin_code", ""))

    def code_kind(self, code: str) -> str:
        """Which code was given: ADMIN, PLAYER, or "" for neither.

        There are two codes but one field: at the table one string is spoken,
        with no explaining which of two boxes it belongs in. Elevation follows
        from which code the joiner knew.
        """

        wanted = code.strip().upper()
        if not wanted:
            return ""
        if self.join_code and secrets.compare_digest(wanted, self.join_code):
            return PLAYER
        if self.admin_code and secrets.compare_digest(wanted, self.admin_code):
            return ADMIN
        return ""

    def is_elevated(self, civilization: str) -> bool:
        entry = self._data.get("players", {}).get(civilization)
        return bool(entry and entry.get("elevated"))

    def is_claimed(self, civilization: str) -> bool:
        entry = self._data.get("players", {}).get(civilization)
        return bool(entry and entry.get("claimed_at"))

    def status(self) -> tuple:
        """(civilization, claimed) for every player, in order."""

        return tuple(
            (name, self.is_claimed(name)) for name in self.civilizations()
        )

    def principal_for(self, token: str, admin_token: str) -> Principal | None:
        """Identify a token. Return None if it is not valid.

        The comparison uses `compare_digest` so the response time does not
        reveal how far into the token the guess was correct.
        """

        if not token:
            return None
        if admin_token and secrets.compare_digest(token, admin_token):
            return Principal(ADMIN)
        for name, entry in self._data.get("players", {}).items():
            stored = str(entry.get("token", ""))
            if stored and secrets.compare_digest(token, stored):
                return Principal(
                    PLAYER, name, elevated=bool(entry.get("elevated"))
                )
        return None

    # -- joining -------------------------------------------------------------

    def claim(self, join_code: str, civilization: str, when: str) -> str:
        """Claim a civilization and return its token.

        Raises ValueError if the code is wrong, the civilization does not exist
        or it is already claimed. A claimed seat cannot be taken from someone
        without an admin release — that is what stops two players ending up on
        the same row.

        Either of the two codes is accepted. A seat claimed with the admin code
        is marked elevated; joining itself takes the same path.
        """

        kind = self.code_kind(join_code)
        if not kind:
            raise ValueError("Wrong join code.")
        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        if entry.get("claimed_at"):
            raise ValueError(f"{civilization} has already been claimed.")
        entry["claimed_at"] = when
        entry["elevated"] = kind == ADMIN
        self.save()
        return str(entry["token"])

    def release(self, civilization: str) -> None:
        """Release a claim, for instance when a phone is swapped."""

        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        entry["claimed_at"] = None
        # Releasing is also the only way to cancel elevation: the seat returns to
        # fully empty, and the next joiner gets only what their code earns them.
        entry["elevated"] = False
        self.save()
