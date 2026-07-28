"""Pelitilan paikallinen JSON-tallennus."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import GameState


SAVE_DIRECTORY = Path(__file__).resolve().parent.parent / "tallennukset"
DEFAULT_SAVE_PATH = SAVE_DIRECTORY / "nykyinen_peli.json"


@dataclass(frozen=True, slots=True)
class SavedGame:
    name: str
    path: Path
    saved_at: str
    player_count: int
    game_mode: str


def save_path_for_name(name: str, directory: Path = SAVE_DIRECTORY) -> Path:
    """Muodosta käyttäjän antamasta pelinimestä turvallinen JSON-polku."""

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Enter a name for the saved game.")
    if any(character in clean_name for character in '<>:"/\\|?*'):
        raise ValueError('The game name cannot contain < > : " / \\ | ? *.')
    filename = re.sub(r"\s+", " ", clean_name).rstrip(". ")
    if not filename:
        raise ValueError("Enter a valid name for the saved game.")
    return directory / f"{filename}.json"


def list_saved_games(directory: Path = SAVE_DIRECTORY) -> tuple[SavedGame, ...]:
    """Listaa avattavissa olevat tallennukset uusimmasta vanhimpaan."""

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


def save_game(game: GameState, path: Path = DEFAULT_SAVE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(game.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_game(path: Path = DEFAULT_SAVE_PATH) -> GameState:
    data = json.loads(path.read_text(encoding="utf-8"))
    return GameState.from_dict(data)


def save_exists(path: Path = DEFAULT_SAVE_PATH) -> bool:
    return path.is_file()
