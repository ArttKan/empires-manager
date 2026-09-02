"""Local JSON persistence for the game state."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from .core.models import GameState


# On a server install the saves must not live in the source directory, because
# a git-based update replaces its contents. An environment variable therefore
# overrides the repo's default directory. It is resolved at call time so that
# systemd can set the variable before the process starts.
DATA_DIRECTORY_VARIABLE = "MEGA_EMPIRES_DATA_DIR"
REPO_SAVE_DIRECTORY = Path(__file__).resolve().parent.parent / "tallennukset"
DEFAULT_SAVE_NAME = "nykyinen_peli.json"


def data_directory() -> Path:
    """Return the save directory from the environment, or the repo default."""

    configured = os.environ.get(DATA_DIRECTORY_VARIABLE, "").strip()
    return Path(configured).expanduser() if configured else REPO_SAVE_DIRECTORY


def default_save_path() -> Path:
    """Return the default save path inside the current save directory."""

    return data_directory() / DEFAULT_SAVE_NAME


@dataclass(frozen=True, slots=True)
class SavedGame:
    name: str
    path: Path
    saved_at: str
    player_count: int
    game_mode: str


def save_path_for_name(name: str, directory: Path | None = None) -> Path:
    """Turn a user-supplied game name into a safe JSON path."""

    directory = data_directory() if directory is None else directory
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Enter a name for the saved game.")
    if any(character in clean_name for character in '<>:"/\\|?*'):
        raise ValueError('The game name cannot contain < > : " / \\ | ? *.')
    filename = re.sub(r"\s+", " ", clean_name).rstrip(". ")
    if not filename:
        raise ValueError("Enter a valid name for the saved game.")
    return directory / f"{filename}.json"


def list_saved_games(directory: Path | None = None) -> tuple[SavedGame, ...]:
    """List the openable saves, newest first."""

    directory = data_directory() if directory is None else directory
    if not directory.is_dir():
        return ()
    saves: list[SavedGame] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            saves.append(
                SavedGame(
                    name=path.stem,
                    path=path,
                    saved_at=str(data.get("saved_at", "")),
                    player_count=int(
                        data.get("player_count", len(data.get("players", [])))
                    ),
                    game_mode=str(data.get("game_mode", "")).upper(),
                )
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return tuple(
        sorted(
            saves,
            key=lambda save: (save.saved_at, save.path.stat().st_mtime),
            reverse=True,
        )
    )


def archive_existing(path: Path) -> Path | None:
    """Move an existing save aside under a timestamped name.

    The server reads one file only, so installing a new game would otherwise
    overwrite the previous one for good — and the server has no named saves to
    fall back on. Archiving costs kilobytes and saves a whole game.

    Returns the archive path, or None if there was nothing to move.
    """

    if not path.is_file():
        return None
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}-{stamp}{path.suffix}")
    counter = 2
    while target.exists():
        target = path.with_name(f"{path.stem}-{stamp}-{counter}{path.suffix}")
        counter += 1
    path.replace(target)

    # The command log is a sibling of the save and belongs to the same game. If
    # it were left behind, a new game would continue the previous audit trail in
    # the same file and the two would be spliced together.
    log = path.with_suffix(".jsonl")
    if log.is_file():
        log.replace(target.with_suffix(".jsonl"))
    return target


def save_game(game: GameState, path: Path | None = None) -> None:
    path = default_save_path() if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(game.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_game(path: Path | None = None) -> GameState:
    path = default_save_path() if path is None else path
    data = json.loads(path.read_text(encoding="utf-8"))
    return GameState.from_dict(data)


def save_exists(path: Path | None = None) -> bool:
    path = default_save_path() if path is None else path
    return path.is_file()
