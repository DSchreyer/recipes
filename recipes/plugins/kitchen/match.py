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

# --- the cookbook shelves ----------------------------------------------------
# The keyword tree owns the regions: `Herkunft::<Shelf>::<Country>[::<Region>]`.
# The maps below only read a tree that predates the rename (country at level 1)
# and give two shelves a label that reads like a cookbook chapter. Twelve
# shelves, because that is how cookbooks split the world -- not one chip per
# country (84) and not five continents (a shelf called "Europa" decides nothing).
SHELVES: dict[str, tuple[str, ...]] = {
    "DACH": ("Deutschland", "Österreich", "Schweiz"),
    "Mittelmeer": ("Italien", "Spanien", "Portugal", "Griechenland"),
    "Westeuropa": ("Frankreich", "Grossbritannien", "Belgien"),
    "Nordeuropa": ("Dänemark", "Schweden"),
    "Osteuropa": ("Polen", "Russland", "Ukraine", "Bosnien"),
    "Naher Osten": ("Türkei", "Libanon", "Syrien", "Israel"),
    "Südasien": ("Indien", "Nepal"),
    "Ostasien": ("China", "Japan", "Korea"),
    "Südostasien": ("Thailand", "Vietnam", "Indonesien", "Malaysia", "Philippinen"),
    "Lateinamerika": ("Mexiko",),
    "Nordamerika": ("USA",),
    "Afrika": ("Marokko", "Nigeria"),
}

SHELF_LABELS: dict[str, str] = {
    "DACH": "Deutschland · Österreich · Schweiz",
    "Osteuropa": "Osteuropa & Balkan",
}

COUNTRY_SHELF: dict[str, str] = {
    country: shelf for shelf, countries in SHELVES.items() for country in countries
}

# The gate. `Ernaehrung::Fleisch` is a not-vegetarian flag that includes fish
# (161 tagged, 50 of them fish), so the four classes below are the only
# partition that neither double-counts nor loses a recipe:
# 114 Fleisch / 47 Fisch / 53 Vegetarisch / 56 ohne Angabe on 2026-11-25.
MEAT: frozenset[str] = frozenset({
    "Hauptzutat::Hähnchen", "Hauptzutat::Kalb", "Hauptzutat::Lamm",
    "Hauptzutat::Pute", "Hauptzutat::Rind", "Hauptzutat::Schwein",
    "Hauptzutat::Wild",
})
FISH: frozenset[str] = frozenset({"Hauptzutat::Fisch", "Hauptzutat::Meeresfrüchte"})
VEG: frozenset[str] = frozenset({"Ernaehrung::Vegetarisch", "Ernaehrung::Vegan"})

CLASSES: tuple[str, ...] = ("fleisch", "fisch", "vegetarisch", "ohne")
CLASS_LABELS: dict[str, str] = {
    "fleisch": "Fleisch",
    "fisch": "Fisch",
    "vegetarisch": "Vegetarisch",
    "ohne": "ohne Angabe",
}

# Seven carb kinds from nine keywords: `Nudeln` and `Teig` are synonyms of
# `Pasta` and `Brot` (measured 2026-11-25: 41 = 25 + 16, 42 = 41 + 1, no
# recipe carries both spellings). `ohne` also catches recipes with no Beilage
# tag at all, so nothing becomes unreachable once a carb is picked.
CARB_KINDS: dict[str, tuple[str, ...]] = {
    "Reis": ("Beilage::Reis",),
    "Kartoffel": ("Beilage::Kartoffel",),
    "Pasta": ("Beilage::Pasta", "Beilage::Nudeln"),
    "Brot/Teig": ("Beilage::Brot", "Beilage::Teig"),
    "Hülsenfrüchte": ("Beilage::Hülsenfrüchte",),
    "Getreide": ("Beilage::Getreide",),
    "ohne": ("Beilage::Ohne Beilage",),
}

# `Aufwand::` carries bilingual twins; the row has two chips, not four.
EFFORT_KINDS: dict[str, tuple[str, ...]] = {
    "schnell": ("Aufwand::Schnell", "Aufwand::quick"),
    "wochenende": ("Aufwand::Wochenende", "Aufwand::weekend"),
}
EFFORT_LABELS: dict[str, str] = {"schnell": "Schnell", "wochenende": "Wochenende"}


def herkunft(name: str) -> tuple[str, str, str] | None:
    """(shelf, country, region) for a Herkunft keyword, in either tree shape.

    New: `Herkunft::Mittelmeer::Italien::Toskana`; old: `Herkunft::Italien`.
    Reading both means the code is correct before and after the rename.
    """
    parts = name.split("::")
    if len(parts) < 2 or parts[0] != "Herkunft":
        return None
    rest = parts[1:]
    if len(rest) >= 2 and rest[0] in SHELVES:
        return rest[0], rest[1], "::".join(rest[2:])
    return COUNTRY_SHELF.get(rest[0], ""), rest[0], "::".join(rest[1:])


def shelf_label(shelf: str) -> str:
    return SHELF_LABELS.get(shelf, shelf)


def carb_kind(value: str) -> str:
    """A kind key (`Pasta`) or a raw keyword (`Beilage::Nudeln`) -> kind key."""
    if value in CARB_KINDS:
        return value
    for kind, names in CARB_KINDS.items():
        if value in names:
            return kind
    return value  # unknown: matches nothing, and the page says so


def class_of(names: frozenset[str]) -> str:
    """The gate partition for one recipe's keyword set."""
    if names & MEAT:
        return "fleisch"
    if names & FISH:
        return "fisch"
    if names & VEG:
        return "vegetarisch"
    return "ohne"


def matches(names: frozenset[str], axes: dict[str, str]) -> bool:
    """One recipe against every active axis: AND across axes, one value each."""
    for key, value in axes.items():
        if not value:
            continue
        if key == "region":
            if not any((h := herkunft(name)) and h[0] == value for name in names):
                return False
        elif key == "land":
            if not any((h := herkunft(name)) and h[1] == value for name in names):
                return False
        elif key == "sub":
            if not any((h := herkunft(name)) and h[2] == value for name in names):
                return False
        elif key == "klasse":
            if class_of(names) != value:
                return False
        elif key == "protein":
            if value not in names:
                return False
        elif key == "carb":
            kind = carb_kind(value)
            if kind == "ohne":
                if any(n.startswith("Beilage::") and n != "Beilage::Ohne Beilage" for n in names):
                    return False
            elif not (names & set(CARB_KINDS.get(kind, ()))):
                return False
        elif key == "effort":
            if not (names & set(EFFORT_KINDS.get(value, ()))):
                return False
        else:
            return False
    return True


def keyword_sets() -> dict[int, frozenset[str]]:
    """Recipe id -> its keyword names, one query for the whole library.

    Counts per chip are then pure Python over ~270 sets instead of one COUNT
    per chip; the picker stays one query plus a prefetch.
    """
    rows = (
        Recipe.objects.exclude(keywords__name=EXCLUDED_KEYWORD)
        .filter(steps__isnull=False)
        .values_list("id", "keywords__name")
    )
    found: dict[int, set[str]] = {}
    for recipe_id, name in rows:
        found.setdefault(recipe_id, set())
        if name:
            found[recipe_id].add(name)
    return {recipe_id: frozenset(names) for recipe_id, names in found.items()}


def count_matching(sets: dict[int, frozenset[str]], axes: dict[str, str]) -> int:
    return sum(1 for names in sets.values() if matches(names, axes))


def recipe_ids(sets: dict[int, frozenset[str]], axes: dict[str, str]) -> set[int]:
    return {recipe_id for recipe_id, names in sets.items() if matches(names, axes)}


def subregions(shelf: str, country: str) -> list[str]:
    """The `Herkunft::<Shelf>::<Country>::<Region>` names under one country."""
    def found(prefix: str) -> list[str]:
        names = Keyword.objects.filter(name__startswith=prefix).values_list("name", flat=True)
        return sorted({n.split("::")[3] for n in names if len(n.split("::")) > 3})

    regions = found(f"Herkunft::{shelf}::{country}::")
    return regions or found(f"Herkunft::{country}::")


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
    # Cooked at least twice and never rated: the card says so instead of
    # quietly recommending a dish the household keeps making and never judges.
    cooked_unrated: bool = False

    @property
    def rating_number(self) -> str:
        """The average as a German decimal, without the sample size."""
        if self.rating is None:
            return ""
        return f"{self.rating:.2f}".rstrip("0").rstrip(".").replace(".", ",")

    @property
    def rating_label(self) -> str:
        """The household number, German decimal comma, with its sample size."""
        if self.rating is None:
            return ""
        return f"{self.rating_number} · {self.rating_count}×" if self.rating_count else self.rating_number


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


def cook_counts() -> dict[int, int]:
    """Recipe id -> number of cooks in the space, rated or not.

    One aggregate instead of a query per card; the picker only needs to know
    whether a dish has been cooked twice.
    """
    rows = CookLog.objects.values("recipe").annotate(cooks=Count("pk"))
    return {row["recipe"]: row["cooks"] for row in rows}


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
    "AXIS_LABEL", "AXIS_PREFIX", "CARB_KINDS", "CLASSES", "CLASS_LABELS",
    "COUNTRY_SHELF", "Candidate", "DEFAULT_CARDS", "EFFORT_KINDS", "EFFORT_LABELS",
    "EXCLUDED_KEYWORD", "FISH", "MAX_CARDS", "MEAT", "NEUTRAL_RATING", "SHELVES",
    "SHELF_LABELS", "STAPLES", "STAPLE_SUFFIXES", "VEG", "axis_values", "carb_kind",
    "class_of", "cook_counts", "count_matching", "food_names", "herkunft",
    "household_ratings", "is_staple", "keyword_sets", "last_notes", "matches", "missing",
    "rank", "recipe_ids", "recipes_for", "search_foods", "shelf_label", "short_label",
    "subregions", "toggle",
]
