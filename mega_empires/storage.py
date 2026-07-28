"""Pelitilan paikallinen JSON-tallennus."""

from __future__ import annotations

import json
from pathlib import Path

from .models import GameState


DEFAULT_SAVE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tallennukset"
    / "nykyinen_peli.json"
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

