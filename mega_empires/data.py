"""Pelissä käytettävä muuttumaton perustieto."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Civilization:
    name: str
    ast_rank: int
    color: str
    text_color: str
    original_block: str


@dataclass(frozen=True, slots=True)
class Advance:
    id: str
    name: str
    cost: int
    victory_points: int
    groups: tuple[str, ...]
    credits: tuple[tuple[str, int], ...]


def _vp(cost: int) -> int:
    if cost < 100:
        return 1
    if cost <= 200:
        return 3
    return 6


_CIVILIZATION_ROWS = (
    ("Minoa", 1, "#70b62c", "#101010", "WEST"),
    ("Saba", 2, "#ef6b2f", "#ffffff", "EAST"),
    ("Assyria", 3, "#22a9db", "#101010", "WEST"),
    ("Maurya", 4, "#d92925", "#ffffff", "EAST"),
    ("Celt", 5, "#159447", "#101010", "WEST"),
    ("Babylon", 6, "#6d7c82", "#ffffff", "EAST"),
    ("Carthage", 7, "#efa02c", "#101010", "WEST"),
    ("Dravidia", 8, "#243b9b", "#ffffff", "EAST"),
    ("Hatti", 9, "#e583b4", "#101010", "WEST"),
    ("Kushan", 10, "#5c1725", "#ffffff", "EAST"),
    ("Rome", 11, "#e62b86", "#101010", "WEST"),
    ("Persia", 12, "#754088", "#ffffff", "EAST"),
    ("Iberia", 13, "#d9e8e8", "#101010", "WEST"),
    ("Nubia", 14, "#25a59f", "#ffffff", "EAST"),
    ("Hellas", 15, "#e5dd1e", "#101010", "WEST"),
    ("Indus", 16, "#146b36", "#ffffff", "EAST"),
    ("Egypt", 17, "#e5ddd0", "#101010", "WEST"),
    ("Parthia", 18, "#4a4a20", "#ffffff", "EAST"),
)

CIVILIZATIONS = tuple(Civilization(*row) for row in _CIVILIZATION_ROWS)
CIVILIZATION_BY_NAME = {civilization.name: civilization for civilization in CIVILIZATIONS}


# Kortit on ryhmitelty Advancement Reference v3 -tiedoston riveittäin.
_ADVANCE_ROWS = (
    ("Mysticism", 50, ("ART", "RELIGION")),
    ("Monument", 180, ("CRAFT", "RELIGION")),
    ("Wonder of the World", 290, ("ART", "CRAFT")),
    ("Sculpture", 50, ("ART",)),
    ("Architecture", 140, ("ART",)),
    ("Mining", 230, ("CRAFT",)),
    ("Cloth Making", 50, ("CRAFT",)),
    ("Naval Warfare", 160, ("CIVIC",)),
    ("Diaspora", 270, ("RELIGION",)),
    ("Urbanism", 50, ("CIVIC",)),
    ("Diplomacy", 160, ("ART",)),
    ("Provincial Empire", 260, ("CIVIC",)),
    ("Monarchy", 60, ("CIVIC",)),
    ("Law", 150, ("CIVIC",)),
    ("Cultural Ascendancy", 280, ("ART",)),
    ("Written Record", 60, ("ART", "CIVIC")),
    ("Cartography", 160, ("SCIENCE",)),
    ("Library", 220, ("SCIENCE",)),
    ("Pottery", 60, ("CRAFT",)),
    ("Agriculture", 120, ("CRAFT",)),
    ("Democracy", 220, ("CIVIC",)),
    ("Masonry", 60, ("CRAFT",)),
    ("Engineering", 160, ("CRAFT", "SCIENCE")),
    ("Roadbuilding", 220, ("CRAFT",)),
    ("Mythology", 60, ("RELIGION",)),
    ("Literacy", 110, ("ART", "SCIENCE")),
    ("Mathematics", 250, ("ART", "SCIENCE")),
    ("Empiricism", 60, ("SCIENCE",)),
    ("Medicine", 140, ("SCIENCE",)),
    ("Anatomy", 270, ("SCIENCE",)),
    ("Deism", 70, ("RELIGION",)),
    ("Fundamentalism", 150, ("RELIGION",)),
    ("Monotheism", 240, ("RELIGION",)),
    ("Theocracy", 80, ("CIVIC", "RELIGION")),
    ("Universal Doctrine", 160, ("RELIGION",)),
    ("Theology", 250, ("RELIGION",)),
    ("Drama and Poetry", 80, ("ART",)),
    ("Rhetoric", 130, ("ART",)),
    ("Politics", 230, ("ART",)),
    ("Music", 80, ("ART",)),
    ("Enlightenment", 160, ("RELIGION",)),
    ("Philosophy", 220, ("RELIGION", "SCIENCE")),
    ("Astronavigation", 80, ("SCIENCE",)),
    ("Calendar", 180, ("SCIENCE",)),
    ("Public Works", 230, ("CIVIC",)),
    ("Coinage", 90, ("SCIENCE",)),
    ("Trade Routes", 180, ("CRAFT",)),
    ("Trade Empire", 260, ("CRAFT",)),
    ("Metalworking", 90, ("CRAFT",)),
    ("Military", 170, ("CIVIC",)),
    ("Advanced Military", 240, ("CIVIC",)),
)

# Korttien alareunaan painetut pysyvät värikrediitit. Ryhmät ovat:
# ART=sininen, CIVIC=punainen, CRAFT=oranssi, RELIGION=keltainen,
# SCIENCE=vihreä.
ADVANCE_GROUPS = ("ART", "CIVIC", "CRAFT", "RELIGION", "SCIENCE")
_ADVANCE_CREDITS = {
    "Mysticism": (("ART", 5), ("RELIGION", 5)),
    "Monument": (("CRAFT", 10), ("RELIGION", 10)),
    "Wonder of the World": (("ART", 20), ("CRAFT", 20)),
    "Sculpture": (("ART", 10), ("CIVIC", 5)),
    "Architecture": (("ART", 10), ("SCIENCE", 5)),
    "Mining": (("CRAFT", 20), ("SCIENCE", 5)),
    "Cloth Making": (("ART", 5), ("CRAFT", 10)),
    "Naval Warfare": (("CIVIC", 10), ("CRAFT", 5)),
    "Diaspora": (("ART", 5), ("RELIGION", 20)),
    "Urbanism": (("CIVIC", 10), ("SCIENCE", 5)),
    "Diplomacy": (("ART", 10), ("CIVIC", 5)),
    "Provincial Empire": (("CIVIC", 20), ("RELIGION", 5)),
    "Monarchy": (("CIVIC", 10), ("RELIGION", 5)),
    "Law": (("CIVIC", 10), ("RELIGION", 5)),
    "Cultural Ascendancy": (("ART", 20), ("RELIGION", 5)),
    "Written Record": (("CIVIC", 5), ("SCIENCE", 5)),
    "Cartography": (("ART", 5), ("SCIENCE", 10)),
    "Library": (("ART", 5), ("SCIENCE", 20)),
    "Pottery": (("ART", 5), ("CRAFT", 10)),
    "Agriculture": (("CRAFT", 10), ("SCIENCE", 5)),
    "Democracy": (("ART", 5), ("CIVIC", 20)),
    "Masonry": (("CRAFT", 10), ("SCIENCE", 5)),
    "Engineering": (("CRAFT", 10), ("SCIENCE", 10)),
    "Roadbuilding": (("CRAFT", 20), ("SCIENCE", 5)),
    "Mythology": (("ART", 5), ("RELIGION", 10)),
    "Literacy": (
        ("ART", 10),
        ("CIVIC", 10),
        ("CRAFT", 5),
        ("RELIGION", 5),
        ("SCIENCE", 5),
    ),
    "Mathematics": (
        ("ART", 20),
        ("CIVIC", 10),
        ("CRAFT", 10),
        ("RELIGION", 10),
        ("SCIENCE", 20),
    ),
    "Empiricism": (
        ("ART", 5),
        ("CIVIC", 5),
        ("CRAFT", 5),
        ("RELIGION", 5),
        ("SCIENCE", 10),
    ),
    "Medicine": (("CRAFT", 5), ("SCIENCE", 10)),
    "Anatomy": (("CRAFT", 5), ("SCIENCE", 20)),
    "Deism": (("CRAFT", 5), ("RELIGION", 10)),
    "Fundamentalism": (("ART", 5), ("RELIGION", 10)),
    "Monotheism": (("CIVIC", 5), ("RELIGION", 20)),
    "Theocracy": (("CIVIC", 5), ("RELIGION", 5)),
    "Universal Doctrine": (("CIVIC", 5), ("RELIGION", 10)),
    "Theology": (("RELIGION", 20), ("SCIENCE", 5)),
    "Drama and Poetry": (("ART", 10), ("RELIGION", 5)),
    "Rhetoric": (("ART", 10), ("CIVIC", 5)),
    "Politics": (("ART", 20), ("RELIGION", 5)),
    "Music": (("ART", 10), ("RELIGION", 5)),
    "Enlightenment": (("CRAFT", 5), ("RELIGION", 10)),
    "Philosophy": (("RELIGION", 20), ("SCIENCE", 20)),
    "Astronavigation": (("RELIGION", 5), ("SCIENCE", 10)),
    "Calendar": (("CIVIC", 5), ("SCIENCE", 10)),
    "Public Works": (("CIVIC", 20), ("CRAFT", 5)),
    "Coinage": (("CIVIC", 5), ("SCIENCE", 10)),
    "Trade Routes": (("CRAFT", 10), ("RELIGION", 5)),
    "Trade Empire": (("CIVIC", 5), ("CRAFT", 20)),
    "Metalworking": (("CIVIC", 5), ("CRAFT", 10)),
    "Military": (("CIVIC", 10), ("CRAFT", 5)),
    "Advanced Military": (("CIVIC", 20), ("SCIENCE", 5)),
}


def _advance_id(name: str) -> str:
    return name.lower().replace(" ", "_")


ADVANCES = tuple(
    Advance(
        _advance_id(name),
        name,
        cost,
        _vp(cost),
        groups,
        _ADVANCE_CREDITS[name],
    )
    for name, cost, groups in _ADVANCE_ROWS
)
ADVANCE_BY_ID = {advance.id: advance for advance in ADVANCES}

# Advancement Reference -taulukon jokainen vaakarivi on 1 VP → 3 VP → 6 VP.
ADVANCE_CHAINS = tuple(
    tuple(advance.id for advance in ADVANCES[index : index + 3])
    for index in range(0, len(ADVANCES), 3)
)

AST_MAX_STEP = 15
AST_POINTS = tuple(step * 5 for step in range(AST_MAX_STEP + 1))


GAME_MODE_LABELS = {
    "WEST": "The West only",
    "EAST": "The East only",
    "BOTH": "The West + The East",
}

AST_ERA_NAMES = (
    "Stone Age",
    "Early Bronze Age",
    "Middle Bronze Age",
    "Late Bronze Age",
    "Early Iron Age",
    "Late Iron Age",
)
AST_ERA_ABBREVIATIONS = ("SA", "EBA", "MBA", "LBA", "EIA", "LIA")

# Kunkin aikakauden ensimmäinen askel 18 pelaajan Basic A.S.T.:lla.
# Lähtöruutu 0 kuuluu Stone Ageen. Rajat on luettu AST_1–AST_3-kuvista.
_BASIC_DEFAULT_STARTS = (0, 5, 8, 11, 14, 15)
_BASIC_LATE_EARLY_BRONZE_STARTS = (0, 6, 9, 11, 14, 15)
_BASIC_LONG_EARLY_BRONZE_STARTS = (0, 5, 9, 11, 14, 15)

BASIC_AST_ERA_STARTS = {
    civilization.name: (
        _BASIC_LATE_EARLY_BRONZE_STARTS
        if civilization.name in {"Minoa", "Saba"}
        else _BASIC_LONG_EARLY_BRONZE_STARTS
        if civilization.name
        in {"Celt", "Carthage", "Iberia", "Egypt", "Parthia"}
        else _BASIC_DEFAULT_STARTS
    )
    for civilization in CIVILIZATIONS
}


def ast_era_index(
    civilization_name: str,
    ast_step: int,
    ast_variant: str = "BASIC",
) -> int:
    """Palauta sivilisaation aikakauden indeksi annetulla AST-askeleella."""

    if ast_variant.upper() != "BASIC":
        raise ValueError("Expert A.S.T. era boundaries have not been added yet.")
    step = max(0, min(AST_MAX_STEP, int(ast_step)))
    starts = BASIC_AST_ERA_STARTS[civilization_name]
    era_index = 0
    for index, start in enumerate(starts):
        if step >= start:
            era_index = index
    return era_index


# Perussääntöjen sivujen 12–13 ja Additional Scenarios -oppaan sivujen
# 20–22 viralliset oletuskokoonpanot. Järjestys noudattaa AST-rankingia.
_WEST_SETUPS = {
    5: ("Minoa", "Assyria", "Hatti", "Hellas", "Egypt"),
    6: ("Minoa", "Carthage", "Rome", "Iberia", "Hellas", "Egypt"),
    7: ("Minoa", "Assyria", "Carthage", "Hatti", "Rome", "Hellas", "Egypt"),
    8: (
        "Minoa",
        "Assyria",
        "Carthage",
        "Hatti",
        "Rome",
        "Iberia",
        "Hellas",
        "Egypt",
    ),
    9: (
        "Minoa",
        "Assyria",
        "Celt",
        "Carthage",
        "Hatti",
        "Rome",
        "Iberia",
        "Hellas",
        "Egypt",
    ),
}

_EAST_SETUPS = {
    5: ("Saba", "Babylon", "Persia", "Nubia", "Parthia"),
    6: ("Saba", "Babylon", "Kushan", "Persia", "Indus", "Parthia"),
    7: ("Saba", "Babylon", "Kushan", "Persia", "Nubia", "Indus", "Parthia"),
    8: (
        "Saba",
        "Maurya",
        "Babylon",
        "Dravidia",
        "Kushan",
        "Persia",
        "Indus",
        "Parthia",
    ),
    9: (
        "Saba",
        "Maurya",
        "Babylon",
        "Dravidia",
        "Kushan",
        "Persia",
        "Nubia",
        "Indus",
        "Parthia",
    ),
}

_BOTH_SETUPS = {
    10: (
        "Minoa",
        "Saba",
        "Assyria",
        "Babylon",
        "Hatti",
        "Persia",
        "Nubia",
        "Hellas",
        "Egypt",
        "Parthia",
    ),
    11: (
        "Saba",
        "Maurya",
        "Assyria",
        "Babylon",
        "Dravidia",
        "Kushan",
        "Persia",
        "Nubia",
        "Indus",
        "Egypt",
        "Parthia",
    ),
    12: (
        "Minoa",
        "Saba",
        "Assyria",
        "Carthage",
        "Babylon",
        "Hatti",
        "Rome",
        "Persia",
        "Nubia",
        "Hellas",
        "Egypt",
        "Parthia",
    ),
    13: (
        "Minoa",
        "Saba",
        "Assyria",
        "Carthage",
        "Babylon",
        "Hatti",
        "Rome",
        "Persia",
        "Iberia",
        "Nubia",
        "Hellas",
        "Egypt",
        "Parthia",
    ),
    14: (
        "Minoa",
        "Saba",
        "Assyria",
        "Celt",
        "Carthage",
        "Babylon",
        "Hatti",
        "Rome",
        "Persia",
        "Iberia",
        "Nubia",
        "Hellas",
        "Egypt",
        "Parthia",
    ),
    15: (
        "Minoa",
        "Saba",
        "Assyria",
        "Carthage",
        "Babylon",
        "Hatti",
        "Kushan",
        "Rome",
        "Persia",
        "Iberia",
        "Nubia",
        "Hellas",
        "Indus",
        "Egypt",
        "Parthia",
    ),
    16: (
        "Minoa",
        "Saba",
        "Assyria",
        "Celt",
        "Carthage",
        "Babylon",
        "Hatti",
        "Kushan",
        "Rome",
        "Persia",
        "Iberia",
        "Nubia",
        "Hellas",
        "Indus",
        "Egypt",
        "Parthia",
    ),
    17: (
        "Minoa",
        "Saba",
        "Maurya",
        "Assyria",
        "Carthage",
        "Babylon",
        "Dravidia",
        "Hatti",
        "Kushan",
        "Rome",
        "Persia",
        "Iberia",
        "Nubia",
        "Hellas",
        "Indus",
        "Egypt",
        "Parthia",
    ),
    18: tuple(civilization.name for civilization in CIVILIZATIONS),
}

SCENARIO_SETUPS = {
    "WEST": _WEST_SETUPS,
    "EAST": _EAST_SETUPS,
    "BOTH": _BOTH_SETUPS,
}


def scenario_civilizations(game_mode: str, player_count: int) -> tuple[str, ...]:
    game_mode = game_mode.upper()
    if game_mode not in SCENARIO_SETUPS:
        raise ValueError(f"Tuntematon pelitila: {game_mode}")
    try:
        names = SCENARIO_SETUPS[game_mode][player_count]
        return tuple(
            sorted(
                names,
                key=lambda name: CIVILIZATION_BY_NAME[name].ast_rank,
            )
        )
    except KeyError as error:
        if game_mode == "BOTH":
            message = "Yhdistelmäpeli tukee 10–18 pelaajaa."
        else:
            message = f"{GAME_MODE_LABELS[game_mode]} tukee 5–9 pelaajaa."
        raise ValueError(message) from error


def default_block(civilization_name: str, player_count: int) -> str:
    """Palauta skenaarion tavallisen kartta-asettelun kauppalohko.

    14 pelaajan pelissä Assyria ja Egypt kuuluvat EAST-lohkoon.
    15–16 pelaajan peleissä Assyria kuuluu EAST-lohkoon.
    Muut käyttävät oman pelilaatikkonsa mukaista oletuslohkoa.
    """

    if player_count in {10, 11}:
        return "SINGLE"
    if player_count in {13, 14} and civilization_name in {"Assyria", "Egypt"}:
        return "EAST"
    if player_count in {12, 15, 16} and civilization_name == "Assyria":
        return "EAST"
    return CIVILIZATION_BY_NAME[civilization_name].original_block
