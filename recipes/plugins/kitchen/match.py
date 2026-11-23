"""The matching rules, with no HTTP and no template in sight.

Everything here is a pure function over recipes the active space can see. The
view assembles arguments and renders; this module decides what "fits" means, so
that the rule can be tested without a browser and changed without touching
markup.

The measurement that shaped it (2026-11-21, live instance): 251 recipes,
`Beilage` 9 values, `Hauptzutat` 10, `Herkunft` 33. The whole candidate set is
built in one query and ranked in Python; there is no index to keep warm.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from django.db.models import Avg, Count

from cookbook.models import CookLog, Food, Keyword, Recipe

# The five questions a cook asks, in the order they get asked at the stove.
# Every axis is a keyword prefix, so the chip lists are read from the tree the
# household already maintains (docs/tandoor-taxonomy.md) and a rename in
# `scripts/tandoor-organise.py` shows up here on its own.
AXIS_PREFIX: dict[str, str] = {
    "carb": "Beilage::",
    "protein": "Hauptzutat::",
    "cuisine": "Herkunft::",
    "effort": "Aufwand::",
    "diet": "Ernaehrung::",
}

AXIS_LABEL: dict[str, str] = {
    "carb": "Beilage",
    "protein": "Hauptzutat",
    "cuisine": "Herkunft",
    "effort": "Aufwand",
    "diet": "Ernährung",
}

# Assumed to be in the kitchen. Without this every recipe reports three missing
# ingredients and the missing list stops meaning anything -- SuperCook's own
# reviewers call their staples toggle the most important setting on the site.
# Compared case-folded. Exact names plus suffixes, because the live library
# writes the same pantry item in variants: `Salz` 2538 uses, `Meersalz` 450,
# `Olivenöl` 1392, `Rapsöl` 306, `Schwarzer Pfeffer` 1015 (measured 2026-11-21).
# A suffix rule keeps those from showing up as shopping items while a real
# ingredient with no staple family (`Kokosmilch`, `Fischsauce`) stays missing.
STAPLES: frozenset[str] = frozenset({
    "salz", "pfeffer", "wasser", "öl", "oel", "zucker", "mehl", "butter",
    "essig", "sojasauce", "backpulver", "natron", "stärke", "staerke",
    "gewürz", "gewürze", "gewuerz", "gewuerze",
})

STAPLE_SUFFIXES: tuple[str, ...] = (
    "salz", "pfeffer", "öl", "oel", "mehl", "zucker", "essig", "sojasauce",
)

# Reference reading, not dinner. The Grundlagen shelf carries no ingredients, so
# without this it wins every "what fits" ranking by having nothing missing
# (measured 2026-11-21: `foods=Kokosmilch` returned six reference pages).
EXCLUDED_KEYWORD = "Rezepttyp::Grundlagen"

MAX_CARDS = 12
DEFAULT_CARDS = 6


def axis_values(prefix: str) -> list[str]:
    """Every keyword name under one axis, sorted, scoped to the active space."""
    return sorted(Keyword.objects.filter(name__startswith=prefix).values_list("name", flat=True))


def short_label(value: str) -> str:
    """`Beilage::Hülsenfrüchte` reads as `Hülsenfrüchte` on a chip."""
    return value.split("::")[-1]


def toggle(values: Iterable[str], value: str) -> list[str]:
    """Add the value, or remove it if already there. Order is kept."""
    current = list(values)
    if value in current:
        return [v for v in current if v != value]
    return current + [value]


def recipes_for(axes: dict[str, list[str]]) -> "QuerySet[Recipe]":
    """AND across axes, OR inside one. Recipes with no steps are not cookable."""
    qs = Recipe.objects.exclude(keywords__name=EXCLUDED_KEYWORD)
    for values in axes.values():
        if values:
            qs = qs.filter(keywords__name__in=values)
    return qs.filter(steps__isnull=False).distinct()


def food_names(recipe: Recipe) -> set[str]:
    """The recipe's food names. An ingredient with no food is skipped, not a crash.

    Measured 2026-11-21 on recipe 19: two of eight ingredients carry no food
    (a group header and an unparsed line).
    """
    return {
        ingredient.food.name
        for step in recipe.steps.all()
        for ingredient in step.ingredients.all()
        if ingredient.food_id
    }


def is_staple(name: str) -> bool:
    """Salt is salt, oil is oil, however the recipe spells it."""
    folded = name.casefold()
    return folded in STAPLES or folded.endswith(STAPLE_SUFFIXES)


def missing(foods: Iterable[str], have: Iterable[str]) -> list[str]:
    """What the recipe needs that the kitchen does not have, staples excluded."""
    have_keys = {name.casefold() for name in have}
    return sorted(
        name for name in set(foods)
        if not is_staple(name) and name.casefold() not in have_keys
    )


@dataclass(frozen=True)
class Candidate:
    recipe_id: int
    name: str
    working_time: int
    image_url: str
    have: tuple[str, ...]
    missing: tuple[str, ...]
    rating: float | None = None
    rating_count: int = 0
    last_note: str = ""
    last_date: date | None = None

    @property
    def stars(self) -> str:
        """Glyphs for the card, rounded to the nearest whole star."""
        if self.rating is None:
            return ""
        full = max(0, min(5, int(self.rating + 0.5)))
        return "★" * full + "☆" * (5 - full)

    @property
    def rating_label(self) -> str:
        """The household number, German decimal comma, with its sample size."""
        if self.rating is None:
            return ""
        label = f"{self.rating:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{label} · {self.rating_count}×" if self.rating_count else label


# What an unrated recipe is worth in a tie. Not zero: a dish nobody has rated
# yet is unknown, not bad, and the household's first week would otherwise bury
# the whole library under three rated favourites.
NEUTRAL_RATING = 3.0


def household_ratings() -> dict[int, tuple[float, int]]:
    """Recipe id -> (average over every member, number of ratings), space-scoped.

    Zero is not a verdict. Vuetify's clearable star control stores 0 when a
    selected star is clicked again, and upstream's own editors can produce such
    rows; counting them would turn "cleared" into "terrible".
    """
    rows = (
        CookLog.objects.filter(rating__gt=0)
        .values("recipe")
        .annotate(average=Avg("rating"), count=Count("pk"))
    )
    return {row["recipe"]: (float(row["average"]), row["count"]) for row in rows}


def last_notes() -> dict[int, tuple[date, str, str]]:
    """Recipe id -> (date, who, note) for the newest note in the space.

    One query, newest first, first comment per recipe wins. The note is the
    cook's message to their future self, so only a non-empty comment counts.
    """
    rows = (
        CookLog.objects.exclude(comment__isnull=True)
        .exclude(comment="")
        .select_related("created_by")
        .order_by("-created_at")
    )
    found: dict[int, tuple[date, str, str]] = {}
    for log in rows:
        if log.recipe_id in found:
            continue
        found[log.recipe_id] = (
            log.created_at.date(),
            log.created_by.get_user_display_name().strip(),
            log.comment,
        )
    return found


def _shuffle_key(seed: str, recipe_id: int) -> str:
    return hashlib.sha256(f"{seed}:{recipe_id}".encode("utf-8")).hexdigest()


def rank(
    candidates: Iterable[Candidate],
    *,
    allow_missing: int = 1,
    seed: str = "",
    limit: int = DEFAULT_CARDS,
    min_rating: int | None = None,
) -> list[Candidate]:
    """Fewest missing first, then most of your food used, then rating, then shuffle.

    The shuffle is what makes the re-roll button useful: pressing it changes the
    order inside a tier without letting a dish that needs two extra ingredients
    outrank one that needs none.

    Rating sits *below* fit on purpose. At 18:00 a proven dish that needs a
    shopping trip is still a worse answer than an unknown one that is already
    in the kitchen.
    """
    keep = [c for c in candidates if len(c.missing) <= allow_missing]
    if min_rating is not None:
        keep = [c for c in keep if c.rating is not None and c.rating >= min_rating]
    keep.sort(key=lambda c: (
        len(c.missing),
        -len(c.have),
        -(c.rating if c.rating is not None else NEUTRAL_RATING),
        _shuffle_key(seed, c.recipe_id),
    ))
    return keep[:limit]


def search_foods(term: str, limit: int = 20) -> list[str]:
    """Food names for the ingredient box, scoped to the space."""
    if not term.strip():
        return []
    return list(
        Food.objects.filter(name__icontains=term.strip())
        .order_by("name")
        .values_list("name", flat=True)[:limit]
    )


__all__ = [
    "AXIS_LABEL", "AXIS_PREFIX", "Candidate", "DEFAULT_CARDS", "EXCLUDED_KEYWORD",
    "MAX_CARDS", "NEUTRAL_RATING", "STAPLES", "STAPLE_SUFFIXES", "axis_values",
    "food_names", "household_ratings", "is_staple", "last_notes", "missing",
    "rank", "recipes_for", "search_foods", "short_label", "toggle",
]
