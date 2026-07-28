"""Civilization Advance -krediittien ja ostohintojen laskenta."""

from __future__ import annotations

from dataclasses import dataclass

from .data import (
    ADVANCE_BY_ID,
    ADVANCE_CHAINS,
    ADVANCE_GROUPS,
    Advance,
)
from .models import PlayerState


@dataclass(frozen=True, slots=True)
class AdvancePrice:
    base_cost: int
    color_discount: int
    special_discount: int
    effective_cost: int
    applied_group: str


def starting_color_credit(player_count: int) -> int:
    """Palauta sääntöjen mukainen kaikille väreille annettava alkukrediitti."""

    if player_count == 5:
        return 10
    if player_count == 6:
        return 5
    return 0


def flexible_credit_entitlement(advance_ids: list[str]) -> int:
    """Palauta Written Recordin ja Monumentin vapaasti jaettava krediittimäärä."""

    return (
        (10 if "written_record" in advance_ids else 0)
        + (20 if "monument" in advance_ids else 0)
    )


def color_credits(
    player: PlayerState,
    player_count: int,
    flexible_credits: dict[str, int] | None = None,
) -> dict[str, int]:
    """Laske aiemmin tallennettujen korttien pysyvät värikrediitit."""

    base = starting_color_credit(player_count)
    allocations = (
        player.flexible_credits
        if flexible_credits is None
        else flexible_credits
    )
    totals = {
        group: base + max(0, int(allocations.get(group, 0)))
        for group in ADVANCE_GROUPS
    }
    for advance_id in player.advances:
        advance = ADVANCE_BY_ID.get(advance_id)
        if advance is None:
            continue
        for group, amount in advance.credits:
            totals[group] += amount
    return totals


def special_credit(
    target_advance_id: str,
    owned_advance_ids: list[str],
) -> int:
    """Laske saman referenssirivin 10/20 pisteen erityisalennus."""

    owned = set(owned_advance_ids)
    for low, middle, high in ADVANCE_CHAINS:
        if target_advance_id == middle and low in owned:
            return 10
        if target_advance_id == high and middle in owned:
            return 20
    return 0


def advance_price(
    advance: Advance,
    player: PlayerState,
    player_count: int,
    flexible_credits: dict[str, int] | None = None,
) -> AdvancePrice:
    """Laske kortin hinta aiemmin tallennetuilla krediiteillä.

    Kaksivärisellä kortilla käytetään vain suurempaa värikrediittiä.
    """

    totals = color_credits(player, player_count, flexible_credits)
    applied_group = max(advance.groups, key=lambda group: totals[group])
    color_discount = totals[applied_group]
    row_discount = special_credit(advance.id, player.advances)
    return AdvancePrice(
        base_cost=advance.cost,
        color_discount=color_discount,
        special_discount=row_discount,
        effective_cost=max(0, advance.cost - color_discount - row_discount),
        applied_group=applied_group,
    )
