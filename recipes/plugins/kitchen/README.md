# Kitchen plugin — the picker, the history, and the cook that reaches the diary

Written 2026-11-23, when the diary bridge was added.

## The gap it fills

Tandoor is the recipe library (270 recipes) plus a cook log (`CookLog`: recipe,
person, space, rating, comment, when). SparkyFitness is the calorie diary, and
it already has this Tandoor instance configured as a food provider, so it can
resolve a recipe to per-serving calories. Nobody carried the fact between them:
every cooked meal was entered twice or not at all.

`recipes/plugins/kitchen/diary.py` carries it, in both directions of intent:

| Tandoor | SparkyFitness | When |
|---|---|---|
| a `CookLog` row (picker form **or** `POST /api/cook-log/`) | one food entry on the cook's day | automatically, via `post_save` |
| a `MealPlan` row on a day | one *planned* food entry | `manage.py diary-push` |

Neither write path in Tandoor was changed. The signal is connected in
`KitchenConfig.ready()` and covers the picker and upstream's Vue cook-log
dialog alike.

## The contract

**Environment.**

| Variable | Default | Meaning |
|---|---|---|
| `SPARKY_FITNESS_URL` | `http://atlas-sparkyfitness-server-1:3010` | Diary base URL. Both that name and `server` resolve on the shared `frontdoor` network |
| `SPARKY_FITNESS_API_KEY` | *(unset)* | Sent as `x-api-key`. **Unset means inert** |
| `SPARKY_FITNESS_USERS` | *(unset)* | `daniel:<uuid>,anna:<uuid>` — Tandoor username → SparkyFitness user id, so the person who cooked gets the entry. Unset: everything lands in the key owner's diary, with a warning |
| `SPARKY_FITNESS_TANDOOR_PROVIDER_ID` | *(unset)* | Pin the Sparky provider when the instance has more than one Tandoor provider; otherwise the first one wins |
| `SPARKY_FITNESS_BUDGET_SECONDS` | `5` | Whole-push request budget. Sparky's Tandoor provider runs one search plus ten parallel detail fetches — 6–8 s measured on Atlas — so the stack sets `20`. The push is a background thread; a larger budget costs nothing |

**Inert mode is the fallback.** With no key nothing is built and no request is
made: one INFO line at startup says so, no line per cook. The deployed instance
has been wired since 2026-11-24 (daniel's SparkyFitness API key from
`/srv/atlas/secrets/sparkyfitness/tandoor_api_key`, mounted as
`SPARKY_FITNESS_API_KEY_FILE`; `SPARKY_FITNESS_BUDGET_SECONDS=20` because
Sparky's Tandoor provider needs ~7 s per resolve) — inert is what you get when
that file is missing or unreadable.

**The cook log survives the diary.** The push is scheduled with
`transaction.on_commit` (a rolled-back cook is not a meal), runs in a daemon
thread, shares a request budget across its calls (5 s by default,
`SPARKY_FITNESS_BUDGET_SECONDS`), and swallows every failure into a warning. A 500 in Tandoor because SparkyFitness is down is the
one outcome this is built to make impossible.

**Saving twice is not eating twice.** SparkyFitness upserts diary entries on
`(user_id, source, source_id)` — partial unique index
`idx_food_entries_user_source_source_id` and `ON CONFLICT (…) DO UPDATE` in
`models/foodEntry.ts`. Every entry is sent with `source='tandoor'` and
`source_id='cooklog:<pk>'` or `'mealplan:<pk>'`, so a retried or repeated save
rewrites that one row. A process-local set (512 entries) additionally skips the
request when the same row is pushed twice from the same worker; `--force` (and
`force=True`) bypasses it. Nothing is written onto the cook log itself.

**No guessed calories.** If SparkyFitness cannot resolve the recipe, the cook
is skipped with a warning. A diary with a made-up number in it is worse than a
diary with a gap.

## Which SparkyFitness endpoints, and why

Read from the running container on 2026-11-23 (`routes/*.ts`,
`services/foodIntegrationService.ts`, `integrations/tandoor/tandoorService.ts`,
`models/foodEntry.ts`, `db/migrations/`):

1. `GET /api/external-providers` — find the Tandoor provider id (its result is
   cached for ten minutes).
2. `GET /api/foods/tandoor/search?query=<recipe name>` with header
   `x-provider-id` — runs Tandoor's own search *through Sparky* and maps the
   recipe to a food with one variant (`serving_size 1`, `serving_unit serving`,
   per-serving calories/macros). The result is matched on
   `provider_external_id == str(recipe.pk)`, i.e. the Tandoor recipe id, so a
   renamed recipe still resolves and a lookalike is never picked.
3. `POST /api/food-entries` — the diary write.

The entry is sent as a **nutrition snapshot** (`food_name`, `serving_*`,
`calories`, macros …) with no `food_id`: the provider search returns a food
object, not a row in Sparky's `foods` table, and persisting it would copy all
270 recipes into the household's food library. Sparky stores per-entry snapshots
anyway, so the diary shows the same numbers either way.

Meal buckets: SparkyFitness seeds exactly `breakfast`, `lunch`, `dinner`,
`snacks` (`db/migrations/20260111180656_custom_meal_feature.sql`). A plan sends
its own meal type, translated from the household's German names
(`Mittagessen` → `lunch`, …). A cook log has no meal type — Tandoor records
*when* it was cooked — so the clock decides: before 11:00 breakfast, before
15:00 lunch, before 21:00 dinner, otherwise a snack. One serving per cook;
how much of it someone ate is a diary question, not something Tandoor knows.

Auth is `x-api-key` (`middleware/authMiddleware.ts`). A **read-only** key is
refused for `POST /api/food-entries` with 403 (`utils/apiKeyScope.ts`) — that
arrives as a warning and an unlogged meal, never as a failed cook.

## The plan command

```
manage.py diary-push [--date YYYY-MM-DD] [--dry-run] [--user NAME] [--force]
```

Walks the `MealPlan` rows that *start* on the day (a plan spanning several days
is only pushed on its first), skips plans without a recipe, and posts each
planned recipe with `source_id='mealplan:<pk>'`. Default target is whoever
planned the meal; `--user` moves the entries to another person's diary.
`--dry-run` resolves and prints the exact payload and writes nothing.

Django names a management command after its module, and a module name cannot
contain a dash, so the implementation is `management/commands/diary_push.py`
with a three-line `diary-push.py` beside it. Both spellings work.

## Smoke test

Proven 2026-11-24 (image `kitchen-v23`): a cook log becomes one diary entry in
the cook's diary with the provider's per-serving numbers, and the entry upserts
on `cooklog:<pk>`. To re-prove it after a deploy, from the Atlas host:

```sh
# 1. The key authenticates and the Tandoor provider resolves a recipe.
docker exec atlas-tandoor-recipes-1 /opt/recipes/venv/bin/python3 - <<'PY'
import requests
key = open('/run/secrets/sparky_fitness_api_key').read().strip()
base = 'http://atlas-sparkyfitness-server-1:3010'
h = {'x-api-key': key, 'Accept': 'application/json'}
r = requests.get(f'{base}/api/external-providers', headers=h, timeout=5)
assert r.ok, r.status_code
pid = [p for p in r.json() if p.get('provider_type') == 'tandoor'][0]['id']
s = requests.get(f'{base}/api/foods/tandoor/search',
                 headers={**h, 'x-provider-id': pid},
                 params={'query': 'Linsen'}, timeout=30)
assert s.ok and s.json(), (s.status_code, s.text[:120])
print('resolve ok:', s.json()[0]['name'], s.json()[0]['default_variant'].get('calories'), 'kcal')
PY

# 2. One cook log becomes one diary entry, then both sides are cleaned up.
docker exec -i atlas-tandoor-recipes-1 sh -c   'export POSTGRES_PASSWORD=$(cat /run/secrets/tandoor_db_password); cd /opt/recipes && /opt/recipes/venv/bin/python3 manage.py shell' <<'PY'
import datetime, requests
from django_scopes import scopes_disabled
from cookbook.models import CookLog, Recipe
from recipes.plugins.kitchen import diary

with scopes_disabled():
    recipe = Recipe.objects.get(name__icontains='Linsen')
    log = CookLog.objects.create(recipe=recipe, created_by_id=1, space=recipe.space,
                                 servings=2, comment='Smoke test (wird geloescht)')
diary.wait_for_pending(30)
key = open('/run/secrets/sparky_fitness_api_key').read().strip()
h = {'x-api-key': key, 'Accept': 'application/json'}
base = 'http://atlas-sparkyfitness-server-1:3010'
today = datetime.date.today().isoformat()
g = requests.get(f'{base}/api/food-entries', headers=h, params={'selectedDate': today}, timeout=10)
rows = g.json()
if isinstance(rows, dict):
    rows = rows.get('foodEntries') or rows.get('entries') or []
hit = [r for r in rows if r.get('food_name') == recipe.name and r.get('source') == 'tandoor'
       and r.get('notes', '').endswith('Daniel')]
assert hit, 'bridge entry missing'
print('entry ok:', hit[0]['food_name'], hit[0]['calories'], 'kcal', hit[0]['meal_type'])
with scopes_disabled():
    log.delete()
d = requests.delete(f"{base}/api/food-entries/{hit[0]['id']}", headers=h, timeout=10)
assert d.ok, d.status_code
print('cleaned up')
PY

# 3. The plan command answers even on a day without plans.
docker exec atlas-tandoor-recipes-1 sh -c \
  'export POSTGRES_PASSWORD=$(cat /run/secrets/tandoor_db_password); cd /opt/recipes && /opt/recipes/venv/bin/python3 manage.py diary-push --dry-run'
```

Notes for whoever runs this: the list endpoint does **not** expose
`source_id`, so match the entry on `food_name` + `notes`; a diary entry whose
cook log was deleted is cleaned up by hand (the bridge never deletes). The
`:3010` server has no published port — run the probes from inside a container
on the `frontdoor` network, as above.

## What it deliberately does not do

- **No deletion.** Deleting a cook log or a plan leaves the diary entry alone;
  the entry is a record of a meal, and SparkyFitness is where it is edited.
- **No servings arithmetic.** A recipe serving is one entry.
- **No automatic plan push.** A plan changes; a diary entry that appears at
  planning time and is wrong at dinner time is worse than a command an operator
  runs in a cron.
- **No library import.** Nothing is created in Sparky's `foods` table.

## Running the tests

```
docker run -d --rm --name tt-pg-diary -e POSTGRES_PASSWORD=test \
  -e POSTGRES_USER=test -e POSTGRES_DB=test -p 55443:5432 postgres:16-alpine

TEST_DB_ENGINE=django.db.backends.postgresql TEST_POSTGRES_HOST=127.0.0.1 \
TEST_POSTGRES_PORT=55443 TEST_POSTGRES_USER=test TEST_POSTGRES_PASSWORD=test \
TEST_POSTGRES_DB=test python -m pytest recipes/plugins/kitchen/tests -o addopts=""
```

35 tests cover the bridge: inert without a key, the three requests of a
successful push, HTTP errors and a dead diary not propagating, the signal on
`post_save`, one push for two saves, two cook logs of the same recipe staying
two entries, the meal buckets, and the command with `--dry-run`. The only mock
is `requests.request`; the cook log, the plan, the scoped manager and the
management command run for real.
