"""The page. All state lives in the query string; every chip is a link.

No JavaScript and no writes: a tap is a page load, and the page can be
bookmarked or shared because the URL carries the whole question. Read-only is a
deliberate constraint -- the stale `mealie_*` tools taught that a write which
lands in the wrong app is a silent lie (docs/tandoor-agent-tools-gap.md).
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, time
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView

from cookbook.models import CookLog, Recipe

from . import match

PARAMS = (*match.AXIS_PREFIX, "foods", "q", "seed", "n", "missing", "minrating")


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
    min_rating = int(params["minrating"]) if params.get("minrating", "").isdigit() else None
    ratings = match.household_ratings()
    notes = match.last_notes()

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
        rating, rating_count = ratings.get(recipe.pk, (None, 0))
        last_date, _who, last_note = notes.get(recipe.pk, (None, "", ""))
        candidates.append(match.Candidate(
            recipe_id=recipe.pk,
            name=recipe.name,
            working_time=recipe.working_time,
            image_url=recipe.image.url if recipe.image else "",
            have=have,
            missing=miss,
            rating=rating,
            rating_count=rating_count,
            last_note=last_note,
            last_date=last_date,
        ))

    # With no ingredient list there is nothing to be missing, so every recipe
    # qualifies. With one, the tier rule applies -- and if even "short by two"
    # is empty, say so and show the closest anyway rather than an empty page.
    cards = match.rank(candidates, allow_missing=allow if foods else 99, seed=seed, limit=limit,
                       min_rating=min_rating)
    if foods and not cards and candidates:
        note = "Alles braucht mehr als zwei Extras. Hier die nächsten."
        cards = match.rank(candidates, allow_missing=99, seed=seed, limit=limit, min_rating=min_rating)

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
        "today": timezone.localdate().isoformat(),
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
        "proven": href(params, minrating="") if min_rating else href(params, minrating="4"),
        "proven_active": min_rating is not None,
        "reset": "?",
        "limit": limit,
    }


class PickerView(TemplateView):
    template_name = "kitchen/picker.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build(self.request))
        context["saved"] = bool(self.request.GET.get("geloggt"))
        return context

    def post(self, request, *args, **kwargs):
        """Log one cook. The only write this plugin makes.

        A rating is a cook event, so the card submits stars, an optional note
        and a date in one form. The recipe is looked up through the scoped
        manager: a card from another space writes nothing, it just falls back
        to the picker.
        """
        raw = request.POST.get("recipe", "")
        recipe = Recipe.objects.filter(pk=raw).first() if raw.isdigit() else None
        if recipe is None:
            return redirect(self._back(request))

        raw_rating = request.POST.get("rating", "")
        rating = int(raw_rating) if raw_rating.isdigit() and 1 <= int(raw_rating) <= 5 else None
        comment = (request.POST.get("note") or "").strip() or None

        CookLog.objects.create(
            recipe=recipe,
            created_by=request.user,
            space=recipe.space,
            rating=rating,
            comment=comment,
            created_at=_when(request.POST.get("date")),
        )
        target = self._back(request)
        separator = "&" if "?" in target else "?"
        return redirect(f"{target}{separator}geloggt=1")

    @staticmethod
    def _back(request) -> str:
        """The query string the card was on, or the bare picker."""
        target = request.POST.get("next", "")
        if target.startswith("/") and not target.startswith("//") and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return target
        return reverse("kitchen:picker")


def _when(raw: str | None) -> datetime:
    """A date input means "we ate at lunchtime", not "at 00:00"."""
    try:
        day: date = date.fromisoformat(raw or "")
    except ValueError:
        return timezone.now()
    return timezone.make_aware(
        datetime.combine(day, time(12, 0)), timezone.get_current_timezone()
    )


MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _month_label(when: datetime) -> str:
    return f"{MONTHS[when.month - 1]} {when.year}"


class CookedView(TemplateView):
    """What we cooked, newest first, grouped by month.

    This is the answer to "wann haben wir das gekocht" -- the recipe page only
    knows the last time. Read-only; logging happens on the picker or the recipe
    page.
    """

    template_name = "kitchen/cooked.html"
    page_size = 200

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        by = self.request.GET.get("by", "")

        logs = CookLog.objects.select_related("recipe", "created_by").order_by("-created_at")
        if by:
            logs = logs.filter(created_by__username=by)

        months: list[dict] = []
        for log in logs[: self.page_size]:
            label = _month_label(log.created_at)
            if not months or months[-1]["label"] != label:
                months.append({"label": label, "logs": []})
            log.stars = "★" * (log.rating or 0)
            months[-1]["logs"].append(log)

        people = (
            CookLog.objects.order_by("created_by__username")
            .values_list("created_by__username", flat=True)
            .distinct()
        )
        context.update(months=months, people=people, by=by)
        return context


__all__ = ["CookedView", "PickerView", "build", "chip_href", "current", "drop_narrowest", "href"]
