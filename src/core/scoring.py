"""Pistelaskenta ja sijoitusten järjestäminen."""

from __future__ import annotations

from dataclasses import dataclass

from .data import ADVANCE_BY_ID, CIVILIZATION_BY_NAME
from .models import PlayerState


@dataclass(frozen=True, slots=True)
class Score:
    cities: int
    ast: int
    advances: int
    bonus: int

    @property
    def total(self) -> int:
        return self.cities + self.ast + self.advances + self.bonus


def calculate_score(player: PlayerState) -> Score:
    advance_points = sum(
        ADVANCE_BY_ID[advance_id].victory_points
        for advance_id in player.advances
        if advance_id in ADVANCE_BY_ID
    )
    return Score(
        cities=player.cities,
        ast=player.ast_step * 5,
        advances=advance_points,
        bonus=5 if player.ast_bonus else 0,
    )


def _tie_break_key(player: PlayerState) -> tuple[int, ...]:
    advances = [
        ADVANCE_BY_ID[advance_id]
        for advance_id in player.advances
        if advance_id in ADVANCE_BY_ID
    ]
    six_point_count = sum(advance.victory_points == 6 for advance in advances)
    three_point_count = sum(advance.victory_points == 3 for advance in advances)
    total_cost = sum(advance.cost for advance in advances)
    ast_rank = CIVILIZATION_BY_NAME[player.civilization].ast_rank
    return (
        player.ast_step,
        six_point_count,
        three_point_count,
        total_cost,
        player.cities,
        player.census,
        -ast_rank,
    )


def ranked_players(players: list[PlayerState]) -> list[PlayerState]:
    """Järjestä pelaajat pisteiden ja käytettävissä olevien tasakriteerien mukaan."""

    return sorted(
        players,
        key=lambda player: (calculate_score(player).total, *_tie_break_key(player)),
        reverse=True,
    )


def players_in_ast_order(players: list[PlayerState]) -> list[PlayerState]:
    """Järjestä pelaajat sivilisaatioiden pysyvään A.S.T.-järjestykseen."""

    return sorted(
        players,
        key=lambda player: CIVILIZATION_BY_NAME[player.civilization].ast_rank,
    )


def visible_rankings(players: list[PlayerState]) -> dict[str, int]:
    """Anna sama sijoitus saman pistemäärän pelaajille.

    Virallisia credit-tokenien tasakriteerejä ei tallenneta minimiversiossa,
    joten näkyvä sijoitus perustuu pisteisiin. Rivien keskinäinen järjestys
    voi silti käyttää saatavilla olevia tasakriteerejä.
    """

    rankings: dict[str, int] = {}
    previous_score: int | None = None
    visible_rank = 0
    for index, player in enumerate(ranked_players(players), start=1):
        score = calculate_score(player).total
        if score != previous_score:
            visible_rank = index
            previous_score = score
        rankings[player.civilization] = visible_rank
    return rankings
