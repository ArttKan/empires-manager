"""Pelitilan paikallinen JSON-tallennus."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from .core.models import GameState


# Palvelinasennuksessa tallennukset eivät saa olla lähdekoodihakemistossa, koska
# git-pohjainen päivitys korvaa sen sisällön. Ympäristömuuttuja ohittaa siksi
# repon oletushakemiston. Hakemisto ratkaistaan vasta kutsuhetkellä, jotta
# systemd voi asettaa muuttujan ennen prosessin käynnistystä.
DATA_DIRECTORY_VARIABLE = "MEGA_EMPIRES_DATA_DIR"
REPO_SAVE_DIRECTORY = Path(__file__).resolve().parent.parent / "tallennukset"
DEFAULT_SAVE_NAME = "nykyinen_peli.json"


def data_directory() -> Path:
    """Palauta tallennushakemisto ympäristömuuttujasta tai repon oletuksesta."""

    configured = os.environ.get(DATA_DIRECTORY_VARIABLE, "").strip()
    return Path(configured).expanduser() if configured else REPO_SAVE_DIRECTORY


def default_save_path() -> Path:
    """Palauta oletustallennuksen polku nykyisestä tallennushakemistosta."""

    return data_directory() / DEFAULT_SAVE_NAME


@dataclass(frozen=True, slots=True)
class SavedGame:
    name: str
    path: Path
    saved_at: str
    player_count: int
    game_mode: str


def save_path_for_name(name: str, directory: Path | None = None) -> Path:
    """Muodosta käyttäjän antamasta pelinimestä turvallinen JSON-polku."""

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
    """Listaa avattavissa olevat tallennukset uusimmasta vanhimpaan."""

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
    """Siirrä olemassa oleva tallennus syrjään aikaleimatulla nimellä.

    Palvelin lukee vain yhtä tiedostoa, joten uuden pelin asentaminen korvaisi
    edellisen lopullisesti eikä palvelimella ole nimettyjä tallennuksia joihin
    palata. Arkistointi maksaa kilotavuja ja säästää kokonaisen pelin.

    Palauttaa arkistopolun, tai None jos siirrettävää ei ollut.
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

    # Komentoloki on tallennuksen sisarustiedosto ja kuuluu samaan peliin. Jos
    # se jätettäisiin paikalleen, uusi peli jatkaisi edellisen tarkastusjälkeä
    # samaan tiedostoon ja molemmat menisivät sekaisin.
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
