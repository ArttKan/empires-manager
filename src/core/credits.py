"""Civilization Advance credits and purchase prices."""

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


def discount_advances(player: PlayerState, round_number: int) -> list[str]:
    """The cards that grant a discount on this turn.

    The acquisition phase is simultaneous: cards bought on the same turn do not
    discount each other, even when the player records them in several batches.
    Only cards from earlier turns therefore grant a discount.

    An unstamped card counts as old. That way games saved before this change
    behave as they did and do not lose their discounts mid-game.
    """

    turns = player.advance_turns
    if not turns:
        return list(player.advances)
    return [
        advance_id
        for advance_id in player.advances
        if turns.get(advance_id, 0) < round_number
    ]


def starting_color_credit(player_count: int) -> int:
    """Return the starting credit granted to every colour by the rules."""

    if player_count in {3, 5}:
        return 10
    if player_count in {4, 6}:
        return 5
    return 0


def flexible_credit_entitlement(advance_ids: list[str]) -> int:
    """Return the freely assignable credit from Written Record and Monument."""

    return (
        (10 if "written_record" in advance_ids else 0)
        + (20 if "monument" in advance_ids else 0)
    )


def color_credits(
    player: PlayerState,
    player_count: int,
    flexible_credits: dict[str, int] | None = None,
    owned: list[str] | None = None,
) -> dict[str, int]:
    """Total the permanent colour credits of the cards already recorded.

    `owned` limits the calculation to a given set of cards; for pricing it is
    `discount_advances()`, so same-turn purchases do not discount each other.
    """

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
    for advance_id in (player.advances if owned is None else owned):
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
    """The 10/20 point row-chain discount from the same reference row."""

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
    owned: list[str] | None = None,
) -> AdvancePrice:
    """Price a card against the credits already recorded.

    A two-colour card uses only the larger of its two colour credits, never
    the sum.

    `owned` is the set of cards that grants the discount. The caller must pass
    `discount_advances(player, round_number)` there, otherwise same-turn
    purchases discount each other — which the rules do not allow.
    """

    totals = color_credits(player, player_count, flexible_credits, owned)
    applied_group = max(advance.groups, key=lambda group: totals[group])
    color_discount = totals[applied_group]
    row_discount = special_credit(
        advance.id, player.advances if owned is None else owned
    )
    return AdvancePrice(
        base_cost=advance.cost,
        color_discount=color_discount,
        special_discount=row_discount,
        effective_cost=max(0, advance.cost - color_discount - row_discount),
        applied_group=applied_group,
    )
