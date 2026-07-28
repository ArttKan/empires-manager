"""Sequence of Play -vaiheet ja niiden pelaajajärjestykset."""

from __future__ import annotations

from dataclasses import dataclass

from .data import CIVILIZATION_BY_NAME
from .models import PlayerState


@dataclass(frozen=True, slots=True)
class Phase:
    number: int
    name: str
    order_summary: str
    rules: tuple[str, ...]
    player_order: str | None = None
    player_order_heading: str = ""


PHASES = (
    Phase(
        1,
        "Tax Collection",
        "All players simultaneously",
        (
            "Default tax rate: transfer 2 population tokens per city from "
            "stock to treasury.",
            "If several players suffer tax revolts, resolve those revolts in "
            "A.S.T.-Ranking order.",
        ),
        "ast_ranking",
        "A.S.T.-Ranking reference for multiple tax revolts",
    ),
    Phase(
        2,
        "Population Expansion & Census",
        "Simultaneous; A.S.T.-Ranking on request",
        (
            "All players expand simultaneously. A player may insist on "
            "A.S.T.-Ranking order when it could affect a decision.",
            "After expansion, count population tokens on the board and update "
            "Census. Cities and ships are not counted.",
        ),
        "ast_ranking",
        "A.S.T.-Ranking reference when an order is requested",
    ),
    Phase(
        3,
        "Movement",
        "Highest Census first; Military moves last",
        (
            "Tokens move 1 area by land or embark a ship; a token may move "
            "by land or ship during a turn, never both.",
            "Ships move up to 4 water areas, carry up to 5 tokens, and may "
            "not cross open sea areas by default. All carried tokens must "
            "disembark after the ship's final step.",
            "Build a new ship for 2 tokens, 2 treasury, or 1 token plus "
            "1 treasury. If tokens are paid, at least 1 must come from the "
            "ship's area.",
            "Before using an existing ship, maintain it with 1 token from "
            "anywhere on the board or 1 treasury. Return unmaintained old "
            "ships to stock at the end of Movement.",
            "Non-Military players move in descending Census order. "
            "A.S.T.-Ranking breaks Census ties.",
            "All Military holders move after all non-holders. Their mutual "
            "order is again descending Census with A.S.T.-Ranking ties.",
            "Players may move simultaneously where their decisions cannot "
            "affect each other.",
        ),
        "movement",
        "Current movement order",
    ),
    Phase(
        4,
        "Conflict",
        "Situational; token conflicts before city attacks",
        (
            "There is no single global player order: resolve all token "
            "conflicts before any city attacks.",
            "Token removal follows minority order. Advanced Military may "
            "change who is allowed to wait.",
            "City-attack order depends on the defenders and attackers; "
            "A.S.T.-Ranking resolves the specified ties.",
        ),
        "ast_ranking",
        "A.S.T.-Ranking reference for situational ties",
    ),
    Phase(
        5,
        "City Construction",
        "Simultaneous; A.S.T.-Ranking on request",
        (
            "Construct cities, remove surplus population, then check city "
            "support.",
            "All players act simultaneously, but a player may insist on "
            "A.S.T.-Ranking order when decisions could be affected.",
        ),
        "ast_ranking",
        "A.S.T.-Ranking reference when an order is requested",
    ),
    Phase(
        6,
        "Trade Cards Acquisition",
        "Fewest cities first; A.S.T.-Ranking ties",
        (
            "Players with at least 1 city receive trade cards in ascending "
            "city-count order. A.S.T.-Ranking breaks ties.",
            "Additional purchases are made in the same order after the "
            "regular cards have been dealt.",
        ),
        "city_count",
        "Current trade-card order",
    ),
    Phase(
        7,
        "Trade",
        "All players simultaneously",
        (
            "All players trade simultaneously during the agreed time limit.",
            "When time expires, current negotiations may be completed but no "
            "new negotiations may begin.",
        ),
    ),
    Phase(
        8,
        "Calamity Selection",
        "All players simultaneously",
        (
            "Reveal the number of calamities held and discard randomly until "
            "the applicable calamity limit is met.",
        ),
    ),
    Phase(
        9,
        "Calamity Resolution",
        "Minor simultaneous; Major by card order",
        (
            "Resolve Minor Calamities simultaneously. A player may wait for "
            "players higher in A.S.T.-Ranking.",
            "Resolve Major Calamities by ascending stack number, with the "
            "Non-Tradeable calamity before the Tradeable calamity.",
            "Victims of the same calamity act simultaneously, but may insist "
            "on A.S.T.-Ranking order.",
        ),
        "ast_ranking",
        "A.S.T.-Ranking reference for victim-order decisions",
    ),
    Phase(
        10,
        "Special Abilities",
        "A.S.T.-Progress; A.S.T.-Ranking ties",
        (
            "Players who own Special Ability advances act from the succession "
            "marker furthest right to the marker furthest left.",
            "A.S.T.-Ranking breaks equal-progress ties. Each player may use "
            "their abilities in any order.",
        ),
        "special_progress",
        "Players currently able to use a Special Ability",
    ),
    Phase(
        11,
        "Surplus Population & City Support",
        "All players simultaneously",
        (
            "Resolve any remaining conflict situations first.",
            "Then all players simultaneously remove surplus population and "
            "check city support.",
        ),
    ),
    Phase(
        12,
        "Civilization Advances Acquisition",
        "A.S.T.-Progress; simultaneous when safe",
        (
            "Purchase Civilization Advances in A.S.T.-Progress order: "
            "furthest-right succession marker first.",
            "Players often purchase simultaneously, but the progress order "
            "may be insisted upon when choices depend on other purchases.",
            "A.S.T.-Ranking breaks equal-progress ties.",
        ),
        "ast_progress",
        "Current A.S.T.-Progress order",
    ),
    Phase(
        13,
        "A.S.T.-Alteration",
        "A.S.T.-Ranking",
        (
            "In fixed A.S.T.-Ranking order, check each civilization's "
            "requirements and move eligible succession markers.",
            "If the game does not end, return discarded trade cards to their "
            "stacks and begin the next turn.",
        ),
        "ast_ranking",
        "Current A.S.T.-Ranking order",
    ),
)

PHASE_BY_NUMBER = {phase.number: phase for phase in PHASES}

SPECIAL_ABILITY_ADVANCES = frozenset(
    {
        "diaspora",
        "fundamentalism",
        "monotheism",
        "politics",
        "provincial_empire",
        "trade_routes",
        "universal_doctrine",
    }
)


def ast_ranking_order(players: list[PlayerState]) -> list[PlayerState]:
    """Palauta pelaajat sivilisaatioiden kiinteässä A.S.T.-järjestyksessä."""

    return sorted(
        players,
        key=lambda player: CIVILIZATION_BY_NAME[player.civilization].ast_rank,
    )


def ast_progress_order(players: list[PlayerState]) -> list[PlayerState]:
    """Palauta pisimmällä A.S.T.:lla olevat ensin, ranking tasakriteerinä."""

    return sorted(
        players,
        key=lambda player: (
            -player.ast_step,
            CIVILIZATION_BY_NAME[player.civilization].ast_rank,
        ),
    )


def movement_order(players: list[PlayerState]) -> list[PlayerState]:
    """Palauta Census-järjestys niin, että Militaryn omistajat ovat lopussa."""

    return sorted(
        players,
        key=lambda player: (
            "military" in player.advances,
            -player.census,
            CIVILIZATION_BY_NAME[player.civilization].ast_rank,
        ),
    )


def trade_card_order(players: list[PlayerState]) -> list[PlayerState]:
    """Palauta kortteihin oikeutetut pelaajat nousevassa kaupunkijärjestyksessä."""

    return sorted(
        (player for player in players if player.cities > 0),
        key=lambda player: (
            player.cities,
            CIVILIZATION_BY_NAME[player.civilization].ast_rank,
        ),
    )


def special_ability_order(players: list[PlayerState]) -> list[PlayerState]:
    """Palauta Special Ability -korttien omistajat A.S.T.-Progress-järjestyksessä."""

    eligible = [
        player
        for player in players
        if SPECIAL_ABILITY_ADVANCES.intersection(player.advances)
    ]
    return ast_progress_order(eligible)


def phase_order(phase: Phase, players: list[PlayerState]) -> list[PlayerState]:
    """Laske vaiheen pelaajalista sen määrittämän järjestyssäännön mukaan."""

    if phase.player_order == "ast_ranking":
        return ast_ranking_order(players)
    if phase.player_order == "ast_progress":
        return ast_progress_order(players)
    if phase.player_order == "movement":
        return movement_order(players)
    if phase.player_order == "city_count":
        return trade_card_order(players)
    if phase.player_order == "special_progress":
        return special_ability_order(players)
    return []


def adjacent_phase(
    round_number: int,
    current_phase: int,
    direction: int,
) -> tuple[int, int]:
    """Siirrä vaihetta eteen- tai taaksepäin kierrosrajojen yli."""

    turn = max(1, int(round_number))
    phase = max(1, min(len(PHASES), int(current_phase)))
    if direction > 0:
        return (turn + 1, 1) if phase == len(PHASES) else (turn, phase + 1)
    if direction < 0:
        if phase > 1:
            return turn, phase - 1
        if turn > 1:
            return turn - 1, len(PHASES)
    return turn, phase
