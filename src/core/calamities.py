"""Calamity-korttien Sequence of Play -näkymässä tarvittavat tiedot."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MinorCalamity:
    """Minor Calamity ja sen paikka Trade Card -pakoissa."""

    stack: int
    name: str
    effect: str


@dataclass(frozen=True, slots=True)
class MajorCalamity:
    """Major Calamity resoluution mukaisessa järjestyksessä."""

    stack: int
    name: str
    tradeable: bool


MINOR_CALAMITIES = (
    MinorCalamity(
        2,
        "Tempest",
        "Take 2 damage in total from coastal areas of your choice and lose "
        "5 treasury tokens.",
    ),
    MinorCalamity(3, "Squandered Wealth", "Lose 10 treasury tokens."),
    MinorCalamity(
        4,
        "City Riots",
        "Reduce 1 of your cities and lose 5 treasury tokens.",
    ),
    MinorCalamity(
        5,
        "City in Flames",
        "Destroy 1 of your cities. You may pay 10 treasury tokens to prevent "
        "this.",
    ),
    MinorCalamity(6, "Tribal Conflict", "Take 5 damage."),
    MinorCalamity(7, "Minor Uprising", "Destroy 1 of your cities."),
    MinorCalamity(
        8,
        "Banditry",
        "Discard 2 commodity cards of your choice. You may pay 4 treasury "
        "tokens for each discard you prevent.",
    ),
    MinorCalamity(
        9,
        "Coastal Migration",
        "Destroy 1 of your coastal cities and lose 5 treasury tokens.",
    ),
)


# Pakan numero määrää resoluutiojärjestyksen. Saman pakan Non-Tradeable
# ratkaistaan aina ennen Tradeable-korttia.
MAJOR_CALAMITIES = (
    MajorCalamity(2, "Volcanic Eruption", False),
    MajorCalamity(2, "Treachery", True),
    MajorCalamity(3, "Famine", False),
    MajorCalamity(3, "Slave Revolt", True),
    MajorCalamity(4, "Flood", False),
    MajorCalamity(4, "Superstition", True),
    MajorCalamity(5, "Civil War", False),
    MajorCalamity(5, "Barbarian Hordes", True),
    MajorCalamity(6, "Cyclone", False),
    MajorCalamity(6, "Epidemic", True),
    MajorCalamity(7, "Tyranny", False),
    MajorCalamity(7, "Civil Disorder", True),
    MajorCalamity(8, "Corruption", False),
    MajorCalamity(8, "Iconoclasm and Heresy", True),
    MajorCalamity(9, "Regression", False),
    MajorCalamity(9, "Piracy", True),
)
