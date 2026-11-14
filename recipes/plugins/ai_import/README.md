# AI import plugin — what it does, what it deliberately does not

Written 2026-11-13, after the first working slice.

## The gap it fills

Tandoor already has two AI features and an import dialog:

| What exists | What it does | What it does not do |
|---|---|---|
| `POST /api/recipe-from-source/` | Downloads a URL, parses schema.org | Produces what the site published. A page with no structured data becomes "Spaghetti Carbonara - schnell & einfach" with three steps and one serving |
| `POST /api/ai-import/` | Reads an uploaded photo/PDF into a recipe | Needs a file. Cannot crawl a URL |
| `POST /api/ai-step-sort/` | Reorders the steps of a recipe being edited | Does not write them |
| `POST /api/recipe/{id}/aiproperties/` | Fills `Property` rows | Not the recipe |

So there is no way to say "here is a URL, give me a proper recipe" and no way
to say "I want to cook X" at all. That is the gap.

## What the plugin does

`POST /api/plugins/ai-import/from-source/`

```json
{"url": "https://...", "ai_provider_id": 3}
{"text": "Mach mir ein Carbonara für vier", "ai_provider_id": 3}
```

It fetches the page (or takes the text), asks the shared model for one JSON
object, then checks every field against the household's own data and returns
the shape Tandoor's import dialog already consumes:

```json
{"recipe": {...}, "duplicates": [], "unknown_foods": [...], "rejected_tags": [...]}
```

**It does not save the recipe.** The dialog shows it, the household corrects
it and saves it in Tandoor. That is deliberate: an import nobody reviewed is
how a recipe library rots.

## What it enforces, and why each one exists

- **Every ingredient gets a `unit`**, even an empty one. Tandoor drops a
  nested ingredient without it, answers 201, and the recipe page shows a
  hole. Measured in the import contract.
- **Foods are matched to existing names, plural-aware.** `Eier` resolves to
  `Ei` instead of creating a second food. Live measurement 2026-11-13: on a
  fresh Chefkoch page with the real 701-food list, all seven ingredients came
  back matched, none invented.
- **Tags must already exist.** Anything else is returned in `rejected_tags`,
  never created. The live instance already carries three overlapping
  taxonomies (`Ernaehrung`/`Ernährung`, `Rezepttyp`/`Rezeptkategorie`,
  `Methode`/`Zubereitung`); a model adding a fourth on every import is the
  last thing the filters need.
- **Numbers and amounts stay out of instruction text**, so a recipe scales
  with servings.
- **`file://`, `ftp://` and anything not http(s) are refused.** The endpoint
  is reachable from the web UI; an importer that follows local paths is a
  file reader.
- **A failed answer is a 422, not a half-recipe.** No steps or no name means
  the request fails loudly.

## What it reuses instead of rebuilding

`AiProvider` (which in Atlas points at LiteLLM `atlas-recipe-global`),
`Space.ai_enabled` and the monthly credits as the per-space off switch,
`AI_ALLOWED_URLS` as the provider guard, `AiCallbackHandler` for cost and
token accounting in `AiLog`. A household with no provider configured sees the
existing "you must select an AI provider" path, not a new one.

## The plugin loader, which had no example

Tandoor's loader (`recipes/settings.py`) resolves a plugin's app class as
`dir(module)[1]` — the second name sorted. `from django.apps import AppConfig`
therefore wins over a class called `AiImportConfig`. The plugin aliases its
config to a name that sorts first (`AAiImportConfig`); without it the app is
registered as `...apps.AppConfig` and startup fails.

## What is not built yet

Each needs its own slice, its own tests and its own verification:

1. **A button in the web UI.** The endpoint works; the Vue import page does
   not know about it. Needs `vue3/src/pages/RecipeImportPage.vue` plus a
   rebuilt frontend bundle in the image.
2. **Image and PDF input** at the same endpoint (Tandoor's own `/api/ai-import/`
   already covers files; this would only merge the two entry points).
3. **Batch import from a folder** — network share/WebDAV, one recipe per file.
4. **Enhance an existing recipe**: tags, cuisine, difficulty, restructured
   steps. Decided design: preview a diff, apply on click, food merges only as
   suggestions with a checkbox. Not started.
5. **Pantry to dinner**, menu and drink suggestions, trivia. Not started, and
   the pantry photo would need a data-policy decision first: the recipe alias
   is on OpenRouter's global endpoint (ADR-0063).
6. **Nutrition.** Deliberately deferred in the planning conversation: an AI
   estimate on the page is confidently wrong data.

## Running it

The fork is a plugin in a clone of `vabene1111/recipes`; the test suite runs
against Postgres:

```
TEST_DB_ENGINE=django.db.backends.postgresql TEST_POSTGRES_HOST=127.0.0.1 \
TEST_POSTGRES_PORT=55432 TEST_POSTGRES_USER=test TEST_POSTGRES_PASSWORD=test \
TEST_POSTGRES_DB=test python -m pytest recipes/plugins/ai_import/tests -o addopts=""
```

32 tests. The only mock is `litellm.completion`; provider lookup, the space
switch, allowlisting, keyword resolution and the response shape run for real.
