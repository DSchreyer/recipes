"""The page. All state lives in the query string; every chip is a link.

No JavaScript and no writes: a tap is a page load, and the page can be
bookmarked or shared because the URL carries the whole question. Read-only is a
deliberate constraint -- the stale `mealie_*` tools taught that a write which
lands in the wrong app is a silent lie (docs/tandoor-agent-tools-gap.md).
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from django.views.generic import TemplateView

from . import match

PARAMS = (*match.AXIS_PREFIX, "foods", "q", "seed", "n", "missing")


def current(request) -> dict[str, str]:
    """Only the parameters this page understands, so junk in the URL dies here."""
    return {key: request.GET[key] for key in PARAMS if request.GET.get(key)}


def href(params: dict[str, str], **changes: str) -> str:
    """The same question with one thing changed. Empty means "remove"."""
    merged = dict(params)
    for key, value in changes.items():
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)
    return "?" + urlencode(merged) if merged else "?"


def values_of(params: dict[str, str], key: str) -> list[str]:
    return [value for value in params.get(key, "").split(",") if value]


def chip_href(params: dict[str, str], axis: str, value: str) -> str:
    return href(params, **{axis: ",".join(match.toggle(values_of(params, axis), value))})


def food_href(params: dict[str, str], name: str) -> str:
    return href(params, foods=",".join(match.toggle(values_of(params, "foods"), name)))


def drop_narrowest(active: dict[str, list[str]]) -> tuple[str, dict[str, list[str]]]:
    """No recipe fits. Remove the axis whose removal opens the most recipes.

    Chosen over "drop the last tap" because the URL does not remember tap order,
    and because the axis that opens the most doors is the one narrowing hardest.
    """
    labels = ", ".join(match.short_label(v) for values in active.values() for v in values)
    best: tuple[dict[str, list[str]], int, str] | None = None
    for key in active:
        trial = {k: v for k, v in active.items() if k != key}
        count = match.recipes_for(trial).count()
        if count and (best is None or count > best[1]):
            best = (trial, count, key)
    if best is None:
        return f"Nichts passt zu {labels}. Hier ist der ganze Bestand.", {}
    trial, count, key = best
    return f"Nichts mit {labels}. Ohne {match.AXIS_LABEL[key]}: {count} Treffer.", trial


def build(request) -> dict:
    params = current(request)
    axes = {key: values_of(params, key) for key in match.AXIS_PREFIX}
    foods = values_of(params, "foods")
    food_set = set(foods)
    note = ""

    active = {key: values for key, values in axes.items() if values}
    qs = match.recipes_for(active)
    if active and not qs.exists():
        note, active = drop_narrowest(active)
        qs = match.recipes_for(active)

    limit = match.MAX_CARDS if params.get("n") == "12" else match.DEFAULT_CARDS
    allow = 2 if params.get("missing") == "2" else 1
    seed = params.get("seed", "")

    candidates = []
    for recipe in qs.prefetch_related("steps__ingredients__food"):
        names = match.food_names(recipe)
        have = tuple(sorted(name for name in names if name in food_set)) if foods else ()
        # A recipe that uses none of what the kitchen has is not an answer to
        # "what can I make with this", however few other things it needs.
        # Measured 2026-11-21: without this floor `foods=Kokosmilch` returned
        # Cacio e Pepe, because it is only short by two ingredients.
        if foods and not have:
            continue
        miss = tuple(match.missing(names, food_set)) if foods else ()
        candidates.append(match.Candidate(
            recipe_id=recipe.pk,
            name=recipe.name,
            working_time=recipe.working_time,
            image_url=recipe.image.url if recipe.image else "",
            have=have,
            missing=miss,
        ))

    # With no ingredient list there is nothing to be missing, so every recipe
    # qualifies. With one, the tier rule applies -- and if even "short by two"
    # is empty, say so and show the closest anyway rather than an empty page.
    cards = match.rank(candidates, allow_missing=allow if foods else 99, seed=seed, limit=limit)
    if foods and not cards and candidates:
        note = "Alles braucht mehr als zwei Extras. Hier die nächsten."
        cards = match.rank(candidates, allow_missing=99, seed=seed, limit=limit)

    rows = [
        {
            "key": key,
            "label": match.AXIS_LABEL[key],
            "chips": [
                {
                    "label": match.short_label(value),
                    "href": chip_href(params, key, value),
                    "active": value in axes[key],
                }
                for value in match.axis_values(prefix)
            ],
        }
        for key, prefix in match.AXIS_PREFIX.items()
    ]

    return {
        "params": params,
        "rows": rows,
        "note": note,
        "cards": cards,
        "picked": [
            {"name": name, "href": food_href(params, name)} for name in foods
        ],
        "q": params.get("q", ""),
        "food_results": [
            {"name": name, "href": food_href(params, name)}
            for name in match.search_foods(params.get("q", ""))
            if name not in food_set
        ],
        "reroll": href(params, seed=secrets.token_hex(3)),
        "more": href(params, n="") if params.get("n") == "12" else href(params, n="12"),
        "more_label": "weniger" if params.get("n") == "12" else "mehr zeigen",
        "allow2": href(params, missing="") if params.get("missing") == "2" else href(params, missing="2"),
        "allow2_active": params.get("missing") == "2",
        "reset": "?",
        "limit": limit,
    }


class PickerView(TemplateView):
    template_name = "kitchen/picker.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build(self.request))
        return context


__all__ = ["PickerView", "build", "chip_href", "current", "drop_narrowest", "href"]
