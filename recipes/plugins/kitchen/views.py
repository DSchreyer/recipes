"""The page. All state lives in the query string; every chip is a link.

No JavaScript for the funnel: a tap is a page load, and the page can be
bookmarked or shared because the URL carries the whole question. There are
exactly two writes -- logging a cook here and correcting one entry in
CookedEntryView -- and both go through the scoped manager, because a write that
lands in the wrong app or the wrong space is a silent lie
(docs/tandoor-agent-tools-gap.md).
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Avg, Count, Max, Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from cookbook.models import CookLog, Recipe

from . import match

PARAMS = (
    "region", "land", "sub", "klasse", "protein", "carb", "effort",
    "foods", "q", "seed", "n", "missing", "minrating",
    # Old bookmarks: `cuisine=Herkunft::Italien`, `diet=Ernaehrung::Vegetarisch`.
    # Mapped in `current()` and never written back to a new link.
    "cuisine", "diet",
)

# The funnel, in the order it is asked: where from, what kind, what with.
AXES = ("region", "land", "sub", "klasse", "protein", "carb", "effort")

AXIS_LABEL: dict[str, str] = {
    "region": "Region",
    "land": "Land",
    "sub": "Gegend",
    "klasse": "Klasse",
    "protein": "Hauptzutat",
    "carb": "Beilage",
    "effort": "Aufwand",
}

# A country only means something inside its shelf; a region only inside its
# country. Changing a parent clears its children instead of leaving a filter
# that can match nothing.
DEPENDENTS: dict[str, tuple[str, ...]] = {"region": ("land", "sub"), "land": ("sub",)}

# Monday to Thursday the picker opens on what has already earned four stars;
# Friday to Sunday stay as they were, because the weekend is when there is time
# to try something new.
WEEKDAY_DEFAULT_MINRATING = 4
# Below this many proven dishes the default would hide the library rather than
# narrow it, so it steps aside -- loudly, in one sentence.
WEEKDAY_DEFAULT_MIN_RECIPES = 4
WEEKDAYS = frozenset({0, 1, 2, 3})

# A cleared star is not a verdict; `match.household_ratings` already ignores
# zeros, and the nudge must too, or "nie bewertet" would count cleared rows.
UNRATED = Q(rating__isnull=True) | Q(rating=0)


def current(request) -> dict[str, str]:
    """Only the parameters this page understands, so junk in the URL dies here."""
    params = {key: request.GET[key] for key in PARAMS if request.GET.get(key)}
    _legacy(params.pop("cuisine", ""), params)
    diet = params.pop("diet", "")
    if diet and not params.get("klasse"):
        params["klasse"] = (
            "vegetarisch" if ("Vegetarisch" in diet or "Vegan" in diet)
            else "fleisch" if "Fleisch" in diet else ""
        )
    if params.get("carb"):
        params["carb"] = match.carb_kind(params["carb"])
    return params


def _legacy(cuisine: str, params: dict[str, str]) -> None:
    """Old bookmarks carried `cuisine=Herkunft::Italien[,Herkunft::Spanien]`.

    The new funnel is one shelf and one country; the first value wins, the rest
    would be a different question. A bare shelf name (`Mittelmeer`) is accepted
    too, because that is what the chips write.
    """
    for raw in cuisine.split(","):
        raw = raw.strip()
        if not raw or params.get("region"):
            continue
        name = raw if raw.startswith("Herkunft::") else f"Herkunft::{raw}"
        leaf = name.split("::")[-1]
        if leaf in match.SHELVES:
            params["region"] = leaf
            continue
        parts = match.herkunft(name)
        if parts and parts[0]:
            params["region"], params["land"] = parts[0], parts[1]
            if parts[2]:
                params["sub"] = parts[2]


def axes_of(params: dict[str, str]) -> dict[str, str]:
    """The active value of every axis, normalized. Unknown values stay: a URL
    the user typed is a question, and the page answers it with a sentence."""
    axes = {key: params.get(key, "") for key in AXES}
    if axes["land"] and not axes["region"]:
        axes["region"] = match.COUNTRY_SHELF.get(axes["land"], "")
    return axes


def label_for(key: str, value: str) -> str:
    """The chip language, used by applied filters and by the dead-pair note."""
    if key == "region":
        return match.shelf_label(value)
    if key == "klasse":
        return match.CLASS_LABELS.get(value, value)
    if key == "effort":
        return match.EFFORT_LABELS.get(value, value)
    if key == "protein":
        return match.short_label(value)
    return value


def href(params: dict[str, str], **changes: str) -> str:
    """The same question with one thing changed. Empty means "remove"."""
    merged = dict(params)
    for key, value in changes.items():
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)
    return "?" + urlencode(merged) if merged else "?"


def _today() -> date:
    """The household's calendar day (Europe/Berlin, from TIME_ZONE).

    A function, not a constant, so the tests can stand on a Tuesday.
    """
    return timezone.localdate()


def _fallback_sentence(proven: int) -> str:
    """One sentence saying why the default is not filtering today."""
    if not proven:
        return "Noch nichts bewährt – deshalb heute ohne „nur Bewährtes“."
    if proven == 1:
        return "Nur ein bewährtes Rezept – deshalb heute ohne „nur Bewährtes“."
    return f"Nur {proven} bewährte Rezepte – deshalb heute ohne „nur Bewährtes“."


def _weekday_default(request) -> bool:
    """True only for a bare picker visit on Monday to Thursday.

    Deliberately narrow: any query string is a question the user asked -- a
    filter, a bookmark, a re-roll -- and is answered exactly as written. The
    `geloggt` flash after a save is not a question, so it does not switch the
    default off; otherwise rating a card would silently reload a different page.
    """
    keys = set(request.GET) - {"geloggt"}
    return not keys and _today().weekday() in WEEKDAYS


def values_of(params: dict[str, str], key: str) -> list[str]:
    return [value for value in params.get(key, "").split(",") if value]


def chip_href(params: dict[str, str], axis: str, value: str) -> str:
    return href(params, **{axis: ",".join(match.toggle(values_of(params, axis), value))})


def food_href(params: dict[str, str], name: str) -> str:
    return href(params, foods=",".join(match.toggle(values_of(params, "foods"), name)))


def drop_narrowest(
    sets: dict[int, frozenset[str]], active: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """No recipe fits. Remove the axis whose removal opens the most recipes.

    Chosen over "drop the last tap" because the URL does not remember tap order,
    and because the axis that opens the most doors is the one narrowing hardest.
    """
    labels = ", ".join(label_for(key, value) for key, value in active.items())
    best: tuple[dict[str, str], int, str] | None = None
    for key in active:
        trial = {k: v for k, v in active.items() if k != key}
        count = match.count_matching(sets, trial)
        if count and (best is None or count > best[1]):
            best = (trial, count, key)
    if best is None:
        return f"Nichts passt zu {labels}. Hier ist der ganze Bestand.", {}
    trial, count, key = best
    return f"Nichts mit {labels}. Ohne {AXIS_LABEL[key]}: {count} Treffer.", trial


def build(request) -> dict:
    params = current(request)
    axes = axes_of(params)
    active = {key: value for key, value in axes.items() if value}
    note = ""

    sets = match.keyword_sets()
    ids = match.recipe_ids(sets, active)
    if active and not ids:
        note, active = drop_narrowest(sets, active)
        axes = {key: active.get(key, "") for key in AXES}
        ids = match.recipe_ids(sets, active)

    # A word in the search box narrows the same set the chips narrow. It is added
    # after the "nothing fits" fallback, because the fallback may only drop a chip
    # axis, never the word the user typed.
    term = params.get("q", "").strip()
    if term:
        named = match.recipe_ids_by_name(term)
        if active:
            narrowed = ids & named
            if not narrowed:
                note = f"Nichts heißt „{term}“ mit diesen Filtern."
            ids = narrowed
        else:
            ids = named
            if not named:
                note = f"Nichts heißt „{term}“."

    limit = match.MAX_CARDS if params.get("n") == "12" else match.DEFAULT_CARDS
    allow = 2 if params.get("missing") == "2" else 1
    seed = params.get("seed", "")
    min_rating = int(params["minrating"]) if params.get("minrating", "").isdigit() else None
    # `minrating=0` is how the toggle writes "aus": the bare URL already means
    # "the weekday default" on Monday to Thursday, so removing the key could
    # never switch the filter off -- it would land back on the default.
    if min_rating == 0:
        min_rating = None
    defaulted = min_rating is None and _weekday_default(request)
    if defaulted:
        min_rating = WEEKDAY_DEFAULT_MINRATING
    ratings = match.household_ratings()
    notes = match.last_notes()
    cooks = match.cook_counts()
    foods = values_of(params, "foods")
    food_set = set(foods)

    qs = (
        Recipe.objects.filter(pk__in=ids)
        .prefetch_related("steps__ingredients__food")
        .order_by("name")
    )
    candidates = []
    for recipe in qs:
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
            cooked_unrated=cooks.get(recipe.pk, 0) >= 2 and recipe.pk not in ratings,
        ))

    # The default must never filter silently: with fewer than four proven
    # dishes it would shrink the library instead of curating it, so it gives
    # way and says why. An explicit `minrating` is the user's own answer and is
    # never second-guessed.
    if defaulted:
        proven = sum(
            1 for c in candidates
            if c.rating is not None and c.rating >= WEEKDAY_DEFAULT_MINRATING
        )
        if proven < WEEKDAY_DEFAULT_MIN_RECIPES:
            min_rating = None
            defaulted = False
            note = _fallback_sentence(proven)

    # While the default is on, every link this page builds carries it: a
    # re-roll, "mehr zeigen" or a chip must narrow the proven list, not quietly
    # drop back to the whole library. The page's own URL stays bare, so a
    # bookmark of it still means "today's default".
    if defaulted:
        params["minrating"] = str(WEEKDAY_DEFAULT_MINRATING)

    # What the header promises: every recipe that survives the filters (and
    # "nur Bewährtes"), before the missing-tier and the six-card limit. A
    # header count that ignores the tier is honest; one that ignores the
    # filters is not.
    total = sum(
        1 for c in candidates
        if min_rating is None or (c.rating is not None and c.rating >= min_rating)
    )

    # With no ingredient list there is nothing to be missing, so every recipe
    # qualifies. With one, the tier rule applies -- and if even "short by two"
    # is empty, say so and show the closest anyway rather than an empty page.
    cards = match.rank(candidates, allow_missing=allow if foods else 99, seed=seed, limit=limit,
                       min_rating=min_rating)
    if foods and not cards and candidates:
        note = "Alles braucht mehr als zwei Extras. Hier die nächsten."
        cards = match.rank(candidates, allow_missing=99, seed=seed, limit=limit, min_rating=min_rating)

    def chip(axis: str, value: str, label: str, count: int, clear: tuple[str, ...] = ()) -> dict:
        on = axes.get(axis) == value
        changes = {axis: "" if on else value}
        for key in clear:
            changes[key] = ""
        return {
            "label": label,
            "count": count,
            "active": on,
            # Zero is shown, not hidden: a hidden chip is a vanished option, and
            # the household cannot tell whether it was removed or just empty.
            "disabled": count == 0 and not on,
            "href": href(params, **changes),
        }

    def counted(axis: str, value: str, **extra: str) -> int:
        return match.count_matching(sets, {**axes, axis: value, **extra})

    # Declaration order, not count order: a shelf that moves under the
    # cursor when a filter changes is worse than a shelf found by memory.
    region_chips = [
        chip("region", shelf, match.shelf_label(shelf),
             counted("region", shelf, land="", sub=""), clear=("land", "sub"))
        for shelf in match.SHELVES
    ]

    land_chips: list[dict] = []
    if axes["region"] in match.SHELVES:
        all_land = counted("land", "", sub="")
        land_chips = [{
            "label": "alle",
            "count": all_land,
            "active": not axes["land"],
            "disabled": False,
            "href": href(params, land="", sub=""),
        }]
        land_chips += [
            chip("land", country, country, counted("land", country, sub=""), clear=("sub",))
            for country in match.SHELVES[axes["region"]]
        ]

    sub_chips: list[dict] = []
    if axes["land"]:
        subs = match.subregions(axes["region"], axes["land"])
        if subs:
            sub_chips = [{
                "label": "alle",
                "count": counted("sub", ""),
                "active": not axes["sub"],
                "disabled": False,
                "href": href(params, sub=""),
            }]
            sub_chips += [
                chip("sub", region, region, counted("sub", region))
                for region in sorted(subs)
            ]

    class_chips = [
        chip("klasse", name, match.CLASS_LABELS[name], counted("klasse", name))
        for name in match.CLASSES
    ]

    protein_chips: list[dict] = []
    if axes["klasse"] in ("fleisch", "fisch"):
        pool = match.MEAT if axes["klasse"] == "fleisch" else match.FISH
        protein_chips = [
            chip("protein", name, match.short_label(name), counted("protein", name))
            for name in sorted(pool, key=match.short_label)
        ]

    carb_chips = [
        chip("carb", kind, kind, counted("carb", kind)) for kind in match.CARB_KINDS
    ]

    effort_chips = [
        chip("effort", key, match.EFFORT_LABELS[key], counted("effort", key))
        for key in match.EFFORT_KINDS
    ]

    rows = [
        {"key": "region", "label": "Region", "chips": region_chips, "show": True},
        {"key": "land", "label": "Land", "chips": land_chips, "show": bool(land_chips)},
        {"key": "sub", "label": "Gegend", "chips": sub_chips, "show": bool(sub_chips)},
        {"key": "klasse", "label": "Klasse", "chips": class_chips, "show": True},
        {"key": "protein", "label": "Hauptzutat", "chips": protein_chips, "show": bool(protein_chips)},
        {"key": "carb", "label": "Beilage", "chips": carb_chips, "show": True},
        {"key": "effort", "label": "Aufwand", "chips": effort_chips, "show": True},
    ]

    applied = []
    for key in AXES:
        value = axes.get(key, "")
        if not value:
            continue
        changes = {key: ""}
        for dependent in DEPENDENTS.get(key, ()):
            changes[dependent] = ""
        applied.append({"label": label_for(key, value), "href": href(params, **changes)})

    crumb = None
    if axes["region"] in match.SHELVES:
        crumb = {
            "back": href(params, land="", sub=""),
            "path": match.shelf_label(axes["region"]),
            "leaf": axes["land"] or "alle Länder",
        }

    return {
        "params": params,
        "rows": rows,
        "applied": applied,
        "crumb": crumb,
        "note": note,
        "total": total,
        "today": _today().isoformat(),
        "rating_options": rating_options(),
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
        "proven": href(params, minrating="0") if min_rating is not None else href(params, minrating="4"),
        "proven_active": min_rating is not None,
        "proven_default": defaulted,
        "filters_active": bool(
            active or foods or params.get("q")
        ),
        "filter_count": (
            len(active)
            + len(foods)
            + (1 if params.get("q") else 0)
        ),
        "reset": "?",
        "limit": limit,
    }


class PickerView(TemplateView):
    template_name = "kitchen/picker.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build(self.request))
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
            return redirect(_back(request, "kitchen:picker"))

        rating = _quarter(request.POST.get("rating", ""))
        comment = (request.POST.get("note") or "").strip() or None

        CookLog.objects.create(
            recipe=recipe,
            created_by=request.user,
            space=recipe.space,
            rating=rating,
            comment=comment,
            created_at=_when(request.POST.get("date")),
        )
        messages.success(request, f"„{recipe.name}“ geloggt.")
        return redirect(_back(request, "kitchen:picker"))


def _back(request, fallback: str) -> str:
    """The query string the form was on, or the page named by `fallback`."""
    target = request.POST.get("next", "")
    if target.startswith("/") and not target.startswith("//") and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse(fallback)


def _quarter(raw: str) -> Decimal | None:
    """A rating is 0.25–5.00 in quarter steps. Anything else is no rating."""
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if not (Decimal("0.25") <= value <= 5) or value % Decimal("0.25") != 0:
        return None
    return value


def _day(raw: str | None) -> date | None:
    """A `date` input as a day, or None when it is empty or nonsense."""
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _at_noon(day: date) -> datetime:
    """A date input means "we ate at lunchtime", not "at 00:00"."""
    return timezone.make_aware(
        datetime.combine(day, time(12, 0)), timezone.get_current_timezone()
    )


def _when(raw: str | None) -> datetime:
    day = _day(raw)
    return _at_noon(day) if day else timezone.now()


MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


def _month_label(when: datetime) -> str:
    return f"{MONTHS[when.month - 1]} {when.year}"


def _german_number(value: float) -> str:
    """A rating as the household writes it: 4,25 rather than 4.25."""
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def rating_options() -> list[dict[str, str]]:
    """0,25 to 5,00 in quarter steps -- the only values `_quarter` accepts."""
    return [
        {"value": f"{step / 4:.2f}", "label": _german_number(step / 4)}
        for step in range(1, 21)
    ]


def _nudge(by: str = "") -> dict:
    """Cooks that never got a star, and the dishes that keep coming back.

    Scoped to the space like every other read here, and to the person when the
    page is filtered: two numbers that sit next to each other have to count the
    same rows, or neither can be trusted. A recipe only counts as "nie
    bewertet" when *no* cook of it was ever rated -- one star anywhere means
    somebody has an opinion already.

    `last` is the newest unrated cook of that recipe: the nudge rates *that*
    entry through CookedEntryView instead of inventing a new cook, which is how
    the same dish used to be counted twice.
    """
    logs = CookLog.objects.all()
    if by:
        logs = logs.filter(created_by__username=by)
    rated = CookLog.objects.filter(rating__gt=0).values("recipe")
    rows = (
        logs.filter(UNRATED)
        .exclude(recipe__in=rated)
        .values("recipe", "recipe__name")
        .annotate(cooks=Count("pk"), last=Max("pk"))
        .filter(cooks__gte=2)
        .order_by("-cooks", "recipe__name")[:5]
    )
    return {
        "cooks": logs.count(),
        "unrated": logs.filter(UNRATED).count(),
        "recipes": list(rows),
    }


# The three chips a cook row shows. Region is deliberately absent: a row answers
# "what was on the plate", not "which book was it from".
AXIS_NAMES = ("Herkunft", "Beilage", "Aufwand")


def _axes(recipe) -> list[str]:
    """The three chips a cook row shows: where from, what with, how much work.

    The keyword tree is flat, so one recipe may carry `Herkunft::Mittelmeer`,
    `Herkunft::Mittelmeer::Italien` and `...::Latium` at once. The deepest path
    says the most, and on a row the country is the part a cook recognises --
    "Italien", not the shelf it hangs under.
    """
    deepest: dict[str, str] = {}
    for keyword in recipe.keywords.all():
        axis, _, rest = keyword.name.partition("::")
        if axis not in AXIS_NAMES or not rest:
            continue
        if axis not in deepest or rest.count("::") > deepest[axis].count("::"):
            deepest[axis] = rest

    def label(axis: str, rest: str) -> str:
        parts = rest.split("::")
        # `Shelf::Country::Region` -> the country; a bare `Country` stays as is.
        value = parts[1] if axis == "Herkunft" and parts[0] in match.SHELVES and len(parts) > 1 else parts[0]
        # The library stores `Aufwand::normal` lower case; on a row of chips that
        # starts with "Schnell" and "Wochenende" the label still reads capitalised.
        return value[:1].upper() + value[1:]

    return [label(axis, deepest[axis]) for axis in AXIS_NAMES if axis in deepest]


class CookedView(TemplateView):
    """What we cooked, newest first, grouped by month.

    This is the answer to "wann haben wir das gekocht" -- the recipe page only
    knows the last time. A row shows the dish itself: its photo, the axis
    chips, who cooked it and how it was. Correcting an entry happens here too,
    through CookedEntryView.
    """

    template_name = "kitchen/cooked.html"
    page_size = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        by = self.request.GET.get("by", "")
        query = self.request.GET.get("q", "").strip()

        logs = (
            CookLog.objects.select_related("recipe", "created_by")
            .prefetch_related("recipe__keywords")
            # pk breaks the tie: two cooks entered in the same minute must not
            # change places between the first page and the second.
            .order_by("-created_at", "-pk")
        )
        if by:
            logs = logs.filter(created_by__username=by)
        if query:
            logs = logs.filter(recipe__name__icontains=query)

        # The header describes the whole filtered history, so it is counted
        # before the cursor: paging back must not change the size of the thing
        # being paged.
        totals = logs.aggregate(
            entries=Count("pk"), average=Avg("rating"), last=Max("created_at")
        )
        summary = {
            "entries": totals["entries"] or 0,
            "average": (
                _german_number(float(totals["average"]))
                if totals["average"] is not None
                else ""
            ),
            "rated": logs.filter(rating__gt=0).count(),
            "last": totals["last"],
        }

        # A cursor, not a page number: new cooks arrive at the top while you
        # read, and `?page=2` would slide under the reader. One extra row tells
        # us whether an older page exists, without counting twice.
        before = parse_datetime(self.request.GET.get("before", ""))
        before_pk = self.request.GET.get("before_pk", "")
        older = logs
        if before is not None and before_pk.isdigit():
            # The cursor is a position in a total order, not a timestamp: two
            # cooks entered in the same minute are still two different rows.
            older = older.filter(
                Q(created_at__lt=before) | Q(created_at=before, pk__lt=int(before_pk))
            )
        elif before is not None:
            older = older.filter(created_at__lt=before)
        rows = list(older[: self.page_size + 1])
        more = len(rows) > self.page_size
        rows = rows[: self.page_size]

        months: list[dict] = []
        for log in rows:
            label = _month_label(timezone.localtime(log.created_at))
            if not months or months[-1]["label"] != label:
                months.append({"label": label, "logs": [], "ratings": []})
            log.rating_number = _german_number(float(log.rating)) if log.rating else ""
            log.image_url = log.recipe.image.url if log.recipe.image else ""
            # `get_user_display_name` returns "Daniel " -- the f-string's space.
            log.person_name = log.created_by.get_user_display_name().strip()
            log.axes = _axes(log.recipe)
            months[-1]["logs"].append(log)
            if log.rating:
                months[-1]["ratings"].append(float(log.rating))

        # A month header is a claim about that month, so it counts and averages
        # what the page is actually showing.
        for month in months:
            month["count"] = len(month["logs"])
            month["average"] = (
                _german_number(sum(month["ratings"]) / len(month["ratings"]))
                if month["ratings"]
                else ""
            )

        next_before = rows[-1].created_at.isoformat() if more and rows else ""
        next_before_pk = rows[-1].pk if more and rows else ""

        people = [
            {"username": username, "name": f"{first} {last}".strip() or username}
            for username, first, last in (
                CookLog.objects.order_by("created_by__username")
                .values_list(
                    "created_by__username", "created_by__first_name", "created_by__last_name"
                )
                .distinct()
            )
        ]

        shown = sum(month["count"] for month in months)
        context.update(
            months=months,
            people=people,
            by=by,
            q=query,
            summary=summary,
            shown=shown,
            more=more,
            paged=before is not None,
            next_before=next_before,
            next_before_pk=next_before_pk,
            nudge=_nudge(by),
            rating_options=rating_options(),
            # Three words of confirmation, one per write, so a change is never
            # silent on the page it returns to.
            # The confirmation is a Django message: it has to name the dish, and
            # a dish name does not belong in the URL of a page you can reload.
        )
        return context


class CookedEntryView(View):
    """Change or remove one entry of the cook history.

    The household decided that anyone may correct an entry: a cook log is a
    shared memory, not a personal diary, and a wrong star is worse than a
    borrowed one. Reads go through the scoped manager, so an entry from another
    space answers 404 and writes nothing.
    """

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        log = CookLog.objects.filter(pk=pk).first()
        if log is None:
            raise Http404("Eintrag nicht gefunden")
        target = _back(request, "kitchen:cooked")
        action = request.POST.get("action", "save")

        if action == "delete":
            name = log.recipe.name
            log.delete()
            # Nothing is left on the page to look at, so the message is the whole
            # confirmation: it has to say what is gone.
            messages.success(request, f"„{name}“ gelöscht.")
            return redirect(target)
        if action == "cook":
            # "Nochmal gekocht" has its own form and always means today: it must
            # never pick up a date or a note typed into the form above it.
            again = CookLog.objects.create(
                recipe=log.recipe,
                created_by=request.user,
                space=log.recipe.space,
            )
            messages.success(request, f"„{again.recipe.name}“ noch einmal gekocht.")
            return redirect(f"{target}#cook-{again.pk}")

        # Only the fields the form carried change: a rating from the nudge must
        # not wipe the note that is already there.
        changed = []
        if "rating" in request.POST:
            log.rating = _quarter(request.POST["rating"])
            changed.append("rating")
        if "note" in request.POST:
            log.comment = (request.POST["note"] or "").strip() or None
            changed.append("comment")
        day = _day(request.POST.get("date"))
        if day is not None:
            log.created_at = _at_noon(day)
            changed.append("created_at")
        if changed:
            log.save(update_fields=changed)
        # Land on the row that changed, not at the top of the page: the point of
        # a correction is seeing the corrected value in place.
        messages.success(request, f"„{log.recipe.name}“ gespeichert.")
        return redirect(f"{target}#cook-{log.pk}")


__all__ = [
    "CookedEntryView", "CookedView", "PickerView", "build", "chip_href", "current",
    "drop_narrowest", "href",
]
