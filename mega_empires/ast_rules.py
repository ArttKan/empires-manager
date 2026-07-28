"""Basic A.S.T. -vaatimusten tarkistus."""

from __future__ import annotations

from dataclasses import dataclass

from .data import ADVANCE_BY_ID, AST_ERA_NAMES, AST_MAX_STEP, ast_era_index
from .models import PlayerState


@dataclass(frozen=True, slots=True)
class AstRequirement:
    era: str
    description: str
    minimum_cities: int = 0
    minimum_advances: int = 0
    minimum_advance_cost: int = 0


BASIC_AST_REQUIREMENTS = (
    AstRequirement("Stone Age", "No requirements"),
    AstRequirement("Early Bronze Age", "At least 2 cities", minimum_cities=2),
    AstRequirement(
        "Middle Bronze Age",
        "At least 3 cities and 3 Civilization Advances",
        minimum_cities=3,
        minimum_advances=3,
    ),
    AstRequirement(
        "Late Bronze Age",
        "At least 3 cities and 3 Advances costing 100+ each",
        minimum_cities=3,
        minimum_advances=3,
        minimum_advance_cost=100,
    ),
    AstRequirement(
        "Early Iron Age",
        "At least 4 cities and 2 Advances costing 200+ each",
        minimum_cities=4,
        minimum_advances=2,
        minimum_advance_cost=200,
    ),
    AstRequirement(
        "Late Iron Age",
        "At least 5 cities and 3 Advances costing 200+ each",
        minimum_cities=5,
        minimum_advances=3,
        minimum_advance_cost=200,
    ),
)

assert tuple(requirement.era for requirement in BASIC_AST_REQUIREMENTS) == (
    AST_ERA_NAMES
)


def meets_basic_ast_requirement(
    player: PlayerState,
    era_index: int,
) -> bool:
    """Tarkista, täyttääkö pelaaja Basic-version aikakausivaatimuksen."""

    requirement = BASIC_AST_REQUIREMENTS[era_index]
    if player.cities < requirement.minimum_cities:
        return False
    qualifying_advances = sum(
        1
        for advance_id in player.advances
        if advance_id in ADVANCE_BY_ID
        and ADVANCE_BY_ID[advance_id].cost >= requirement.minimum_advance_cost
    )
    return qualifying_advances >= requirement.minimum_advances


def ast_marker_state(
    player: PlayerState,
    player_count: int | None = None,
    game_mode: str | None = None,
) -> str:
    """Palauta READY, BLOCKED, WARNING tai FINISHED markkeria varten.

    WARNING tarkoittaa, etteivät nykyisen aikakauden vaatimukset enää täyty.
    Basic-pelissä tämä ei itsessään siirrä markkeria taaksepäin.
    """

    current_era = ast_era_index(
        player.civilization,
        player.ast_step,
        player_count=player_count,
        game_mode=game_mode,
    )
    if not meets_basic_ast_requirement(player, current_era):
        return "WARNING"
    if player.ast_step >= AST_MAX_STEP:
        return "FINISHED"
    next_era = min(current_era + 1, len(BASIC_AST_REQUIREMENTS) - 1)
    return (
        "READY"
        if meets_basic_ast_requirement(player, next_era)
        else "BLOCKED"
    )
