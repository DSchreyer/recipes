"""A cook log in Tandoor becomes a food entry in SparkyFitness.

Tandoor is the recipe library and the cook log; SparkyFitness is the calorie
diary. Both are true, and until now every cooked meal was entered twice or not
at all. This module carries the one fact Tandoor knows and Sparky does not:
*this recipe was cooked, by this person, at this time*.

Four rules decide the shape of the code.

* **The cook log is never at risk.** The push is scheduled with
  ``transaction.on_commit`` -- a rolled back cook is not a meal -- and then runs
  in a daemon thread with a five second budget. Every failure is logged and
  dropped. A diary that is down must never turn a saved cook into a 500.
* **Inert without a key.** ``SPARKY_FITNESS_API_KEY`` unset means no request is
  ever built. That is the deployed state today, so it is the state that is
  tested first.
* **Saving twice is not eating twice.** Sparky upserts diary entries on
  ``(user_id, source, source_id)``: partial unique index
  ``idx_food_entries_user_source_source_id`` plus ``ON CONFLICT DO UPDATE`` in
  ``models/foodEntry.ts`` (``createFoodEntry``). We send ``source='tandoor'``
  and ``source_id='cooklog:<pk>'`` (or ``'mealplan:<pk>'``), so a retried save
  rewrites that one row instead of adding a second.
* **No guessed calories.** The recipe is resolved through Sparky's own Tandoor
  food provider -- the same path the web UI uses -- and matched by Tandoor
  recipe id. A recipe Sparky cannot resolve is skipped with a warning rather
  than logged with a number nobody checked.

What is sent, and why it is a snapshot rather than a library row: the provider
search returns a *food object*, not a row in Sparky's ``foods`` table. Posting
``food_id`` would require persisting it, which would copy all 270 recipes into
the household's food library. A diary entry stores its own nutrition snapshot
anyway (``food_name``, ``serving_*``, ``calories`` ...), so the entry is sent as
a snapshot with no ``food_id``: one write, no library pollution.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Where the shared frontdoor network puts the diary server. Both this name and
# the ``server`` alias resolve from inside the Tandoor container (verified
# 2026-11-23); the long one is what Atlas's compose uses.
DEFAULT_URL = 'http://atlas-sparkyfitness-server-1:3010'

# Every request of one push shares this budget: the thread must be gone long
# before anyone notices it was there.
BUDGET_SECONDS = 5.0

# Stamped on every entry we write. ``source_id`` carries the Tandoor row, so
# the pair is stable across restarts, workers and retries.
SOURCE = 'tandoor'

# Sparky seeds exactly these four meal buckets
# (db/migrations/20260111180656_custom_meal_feature.sql); anything else makes
# ``createFoodEntry`` raise "Invalid meal type".
MEALS = ('breakfast', 'lunch', 'dinner', 'snacks')

# Tandoor's meal types are household-defined and German here. Matched as
# substrings of the lowercased name; the first hit wins.
MEAL_ALIASES = (
    ('breakfast', ('breakfast', 'frühstück', 'fruehstueck', 'brunch', 'morgens')),
    ('lunch', ('lunch', 'mittag', 'mittagessen', 'zu mittag')),
    ('dinner', ('dinner', 'abend', 'abendessen', 'suppe', 'nachtessen')),
    ('snacks', ('snack', 'snacks', 'zwischenmahlzeit', 'jause', 'kaffee', 'kuchen')),
)

# Only fields Sparky's food_entries table actually has. The provider mapping
# fills most of them; missing ones stay out so Sparky's own defaults apply.
NUTRIENTS = (
    'calories', 'protein', 'carbs', 'fat', 'saturated_fat', 'polyunsaturated_fat',
    'monounsaturated_fat', 'trans_fat', 'cholesterol', 'sodium', 'potassium',
    'dietary_fiber', 'sugars', 'vitamin_a', 'vitamin_c', 'calcium', 'iron',
)

# How long a resolved provider id is trusted. One cook log per meal does not
# justify a lookup each time, and a provider is configuration, not data.
PROVIDER_TTL_SECONDS = 600

# Bounded memory for "already pushed by this process". The database upsert is
# the actual guarantee; this only spares the second request on a double submit.
_SEEN_LIMIT = 512


@dataclass(frozen=True)
class Config:
    url: str
    api_key: str
    # Tandoor username -> SparkyFitness user uuid. Empty means "the key owner".
    users: dict[str, str]
    provider_id: str | None = None


class DiaryError(RuntimeError):
    """A request was refused, unanswered, or over budget. Never escapes a push."""


class Deadline:
    """The whole push shares one budget, not each request."""

    def __init__(self, seconds: float = BUDGET_SECONDS):
        self.started = time.monotonic()
        self.seconds = seconds

    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.started)

    def check(self) -> float:
        left = self.remaining()
        if left <= 0:
            raise DiaryError('time budget exhausted')
        return left


def _split_map(raw: str) -> dict[str, str]:
    """``daniel:<uuid>,anna:<uuid>`` -> dict. Junk is dropped, not guessed."""
    mapping: dict[str, str] = {}
    for pair in (raw or '').split(','):
        name, _, value = pair.partition(':')
        name, value = name.strip().lower(), value.strip()
        if name and value:
            mapping[name] = value
    return mapping


def config() -> Config | None:
    """Read the environment. ``None`` means inert -- the deployed default."""
    api_key = os.getenv('SPARKY_FITNESS_API_KEY', '').strip()
    if not api_key:
        return None
    return Config(
        url=os.getenv('SPARKY_FITNESS_URL', DEFAULT_URL).rstrip('/'),
        api_key=api_key,
        users=_split_map(os.getenv('SPARKY_FITNESS_USERS', '')),
        provider_id=os.getenv('SPARKY_FITNESS_TANDOOR_PROVIDER_ID', '').strip() or None,
    )


def enabled() -> bool:
    return config() is not None


def startup_notice() -> None:
    """One line at startup, not one line per cook.

    Called from ``KitchenConfig.ready()``. It says which mode the instance is
    in, so an operator can tell "bridge is off" from "bridge is broken".
    """
    cfg = config()
    if cfg is None:
        logger.info(
            'kitchen.diary: inert (SPARKY_FITNESS_API_KEY unset); cook logs stay in Tandoor'
        )
        return
    logger.info(
        'kitchen.diary: pushing cook logs to %s%s',
        cfg.url,
        '' if cfg.users else ' (no SPARKY_FITNESS_USERS: the key owner gets every entry)',
    )


_provider_lock = threading.Lock()
_provider: dict[str, Any] = {}
_seen: OrderedDict[str, bool] = OrderedDict()


def reset_cache() -> None:
    """Forget the provider lookup and the pushed-ids. Tests and ops only."""
    with _provider_lock:
        _provider.clear()
    _seen.clear()


def _remember(source_id: str) -> bool:
    """True the first time this process sees ``source_id``, False afterwards."""
    if source_id in _seen:
        return False
    _seen[source_id] = True
    while len(_seen) > _SEEN_LIMIT:
        _seen.popitem(last=False)
    return True


def _send(cfg: Config, method: str, path: str, *, timeout: float,
          params: dict | None = None, payload: dict | None = None,
          headers: dict | None = None) -> Any:
    """One request. Raises ``DiaryError`` on anything that is not a 2xx."""
    merged = {'x-api-key': cfg.api_key, 'Accept': 'application/json'}
    merged.update(headers or {})
    if payload is not None:
        merged['Content-Type'] = 'application/json'
    url = f'{cfg.url}{path}'
    try:
        response = requests.request(
            method, url, params=params, json=payload, headers=merged,
            timeout=max(0.5, timeout),
        )
    except requests.RequestException as exc:
        raise DiaryError(f'{method} {path}: {exc.__class__.__name__}') from exc
    if response.status_code >= 400:
        raise DiaryError(
            f'{method} {path}: HTTP {response.status_code} {response.text[:160]}'
        )
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise DiaryError(f'{method} {path}: response is not JSON') from exc


def _provider_for(cfg: Config, deadline: Deadline) -> str:
    """Sparky's Tandoor provider id, from the provider list the UI also reads."""
    if cfg.provider_id:
        return cfg.provider_id
    with _provider_lock:
        cached = _provider.get(cfg.url)
        if cached and time.monotonic() - cached[1] < PROVIDER_TTL_SECONDS:
            return cached[0]
    providers = _send(cfg, 'GET', '/api/external-providers', timeout=deadline.check()) or []
    tandoor = [
        provider for provider in providers
        if isinstance(provider, dict)
        and str(provider.get('provider_type', '')).lower() == 'tandoor'
    ]
    if not tandoor:
        raise DiaryError('no Tandoor data provider configured in SparkyFitness')
    provider_id = str(tandoor[0].get('id'))
    with _provider_lock:
        _provider[cfg.url] = (provider_id, time.monotonic())
    return provider_id


def _resolve(cfg: Config, recipe_id: int, name: str, deadline: Deadline) -> dict | None:
    """Ask Sparky's Tandoor provider for this recipe, by id.

    The provider runs Tandoor's own search and maps the recipe to a food with
    one variant ("serving") carrying the per-serving numbers. Matching on
    ``provider_external_id`` -- the Tandoor recipe id -- rather than on the name
    keeps a renamed recipe resolvable and a lookalike from being picked.
    """
    provider_id = _provider_for(cfg, deadline)
    results = _send(
        cfg, 'GET', '/api/foods/tandoor/search',
        timeout=deadline.check(),
        params={'query': name},
        headers={'x-provider-id': provider_id},
    )
    for item in results or []:
        if isinstance(item, dict) and str(item.get('provider_external_id', '')) == str(recipe_id):
            return item
    return None


def _numeric(value: Any, fallback: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _variant(food: dict) -> dict:
    variant = food.get('default_variant')
    if not isinstance(variant, dict):
        variants = food.get('variants') or []
        variant = variants[0] if variants and isinstance(variants[0], dict) else {}
    return variant


def _localtime(when: datetime) -> datetime:
    return timezone.localtime(when) if timezone.is_aware(when) else when


def meal_for(name: str | None, when: datetime) -> str:
    """Which of Sparky's four buckets a meal belongs to.

    A planned meal knows its type; a cook log does not -- Tandoor records when
    it was cooked, not which meal it was. So: the name if it is one we know,
    otherwise the clock. Anything outside the three meal windows is a snack.
    """
    # Whole words, not substrings: "Snack am Nachmittag" contains "mittag" and
    # would otherwise land in lunch.
    lowered = (name or '').strip().lower()
    if lowered:
        words = set(re.split(r'[^0-9a-zäöüß]+', lowered))
        for meal, aliases in MEAL_ALIASES:
            for alias in aliases:
                hit = alias in lowered if ' ' in alias else alias in words
                if hit:
                    return meal
    hour = _localtime(when).hour
    if hour < 11:
        return 'breakfast'
    if hour < 15:
        return 'lunch'
    if hour < 21:
        return 'dinner'
    return 'snacks'


def entry_payload(*, name: str, when: datetime, meal: str, source_id: str,
                  user_id: str | None, notes: str, food: dict | None = None) -> dict:
    """The ``POST /api/food-entries`` body for one serving of one recipe."""
    resolved = food or {'name': name}
    variant = _variant(resolved)
    payload: dict[str, Any] = {
        'food_name': resolved.get('name') or name,
        'serving_size': _numeric(variant.get('serving_size'), 1.0),
        'serving_unit': variant.get('serving_unit') or 'serving',
        # One serving per cook. How much of it a person ate is a diary
        # question, not something Tandoor knows.
        'quantity': 1,
        'unit': 'serving',
        'meal_type': meal if meal in MEALS else 'snacks',
        'entry_date': _localtime(when).date().isoformat(),
        'entry_time': _localtime(when).strftime('%H:%M'),
        'source': SOURCE,
        'source_id': source_id,
        'notes': notes,
    }
    for key in NUTRIENTS:
        value = _numeric(variant.get(key))
        if value is not None:
            payload[key] = value
    if user_id:
        payload['user_id'] = user_id
    return payload


def _target_user(cfg: Config, username: str) -> str | None:
    if not cfg.users:
        return None
    return cfg.users.get((username or '').lower())


def _display(person) -> str:
    user = getattr(person, 'created_by', None)
    if user is None:
        return ''
    return (user.get_full_name() or '').strip() or user.username


def _push(*, recipe_id: int | None, name: str, when: datetime, meal: str,
          source_id: str, username: str, notes: str, dry_run: bool = False,
          force: bool = False) -> dict | None:
    """Resolve, build and send one entry. Returns what was (or would be) sent.

    Never raises: every failure is a warning and a ``None``. A diary problem is
    not a reason for a cook log to fail.
    """
    cfg = config()
    if cfg is None:
        return None
    if recipe_id is None:
        logger.warning('kitchen.diary: %s has no recipe; skipped', source_id)
        return None
    deadline = Deadline()
    try:
        user_id = _target_user(cfg, username)
        if cfg.users and user_id is None:
            logger.warning(
                'kitchen.diary: %s has no SparkyFitness user for "%s"; '
                'the key owner gets the entry', source_id, username,
            )
        food = _resolve(cfg, recipe_id, name, deadline)
        if food is None:
            logger.warning(
                'kitchen.diary: SparkyFitness cannot resolve Tandoor recipe %s ("%s"); '
                'skipped', recipe_id, name,
            )
            return None
        payload = entry_payload(
            name=name, when=when, meal=meal,
            source_id=source_id, user_id=user_id, notes=notes, food=food,
        )
        if dry_run:
            return payload
        if not force and not _remember(source_id):
            logger.info('kitchen.diary: %s already pushed by this process', source_id)
            return payload
        _send(cfg, 'POST', '/api/food-entries', timeout=deadline.check(), payload=payload)
        logger.info(
            'kitchen.diary: %s -> %s %s (%s kcal)',
            source_id, payload['entry_date'], payload['meal_type'], payload.get('calories'),
        )
        return payload
    except DiaryError as exc:
        logger.warning('kitchen.diary: %s not pushed: %s', source_id, exc)
    except Exception:  # noqa: BLE001 - the cook log outranks the diary
        logger.warning('kitchen.diary: %s not pushed (unexpected)', source_id, exc_info=True)
    return None


# --------------------------------------------------------------------------
# cook log
# --------------------------------------------------------------------------

_pending_lock = threading.Lock()
_pending: set[threading.Thread] = set()


def _spawn(target, **kwargs) -> threading.Thread:
    thread = threading.Thread(
        target=_run_and_forget, args=(target, kwargs),
        name='kitchen-diary', daemon=True,
    )
    with _pending_lock:
        _pending.add(thread)
    thread.start()
    return thread


def _run_and_forget(target, kwargs) -> None:
    try:
        target(**kwargs)
    except Exception:  # noqa: BLE001 - nothing above may see a diary failure
        logger.warning('kitchen.diary: background push died', exc_info=True)
    finally:
        with _pending_lock:
            _pending.discard(threading.current_thread())


def wait_for_pending(timeout: float = 10.0) -> None:
    """Join the pushes this process started. Tests and shutdown only."""
    with _pending_lock:
        threads = list(_pending)
    for thread in threads:
        thread.join(timeout)


def push_cook(cook_log, *, wait: bool = True, dry_run: bool = False,
              force: bool = False) -> dict | None:
    """Push one ``cookbook.CookLog``.

    ``wait=False`` is what the signal uses: the request returns and the thread
    finishes on its own. Everything the thread needs is read here, on the
    request's own connection -- a daemon thread must not touch the ORM.
    """
    if config() is None:
        return None
    creator = cook_log.created_by
    if creator is None:
        # The column is non-null, but "nobody" has no diary to write to.
        logger.info('kitchen.diary: cook log %s has no author; skipped', cook_log.pk)
        return None
    recipe = cook_log.recipe
    kwargs = {
        'recipe_id': recipe.pk if recipe else None,
        'name': recipe.name if recipe else '',
        'when': cook_log.created_at,
        'meal': meal_for(None, cook_log.created_at),
        'source_id': f'cooklog:{cook_log.pk}',
        'username': creator.username,
        'notes': f'Aus Tandoor · gekocht von {_display(cook_log)}',
        'dry_run': dry_run,
        'force': force,
    }
    if wait:
        return _push(**kwargs)
    _spawn(_push, **kwargs)
    return None


def cook_logged(sender, instance, created=False, raw=False, **kwargs) -> None:
    """``post_save`` on CookLog.

    Both write paths land here: the picker's form (``PickerView.post``) and
    upstream's ``POST /api/cook-log/`` behind the Vue dialog. Neither is
    touched. ``raw`` saves are fixture loads -- not a meal.
    """
    if raw or config() is None:
        return
    # A cook that rolls back must not appear in the diary; a cook that commits
    # must not wait for SparkyFitness.
    transaction.on_commit(lambda: push_cook(instance, wait=False, force=False))


# --------------------------------------------------------------------------
# meal plan
# --------------------------------------------------------------------------


def push_plan(plan, *, user=None, dry_run: bool = False, force: bool = False) -> dict | None:
    """Push one ``cookbook.MealPlan`` row as a planned entry.

    The plan carries its own meal type and time, so neither is guessed. The
    target is the person given on the command line, else whoever planned it.
    """
    recipe = plan.recipe
    owner = user or plan.created_by
    meal = meal_for(getattr(plan.meal_type, 'name', ''), plan.from_date)
    return _push(
        recipe_id=recipe.pk if recipe else None,
        name=recipe.name if recipe else plan.title,
        when=plan.from_date,
        meal=meal,
        source_id=f'mealplan:{plan.pk}',
        username=getattr(owner, 'username', '') or '',
        notes=f'Aus Tandoor · geplant für {meal}',
        dry_run=dry_run,
        force=force,
    )


def plan_rows(day: date):
    """The plans that start on ``day``, in clock order."""
    from cookbook.models import MealPlan
    from django_scopes import scopes_disabled

    # A management command runs outside a request, so no space is active; the
    # scoped manager would answer "nothing" rather than "everything".
    with scopes_disabled():
        return list(
            MealPlan.objects.filter(from_date__date=day)
            .select_related('recipe', 'created_by', 'meal_type')
            .order_by('from_date', 'pk')
        )


def describe(payload: dict | None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else ''
