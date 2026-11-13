# The Website mode for AI import

Branch `ai-import-ui`, commit `93d2192`. Built in a worktree at
`/tmp/opencode/tandoor-ui` so it cannot collide with the session that owns
`/tmp/opencode/recipes-upstream`.

## What was missing

The `ai_import` plugin (`POST /plugins/ai-import/from-source/`) turns a URL
into a validated recipe draft. Nothing in the web UI called it: the import
dialog offered File and Text under AI, and a plain URL field that talks to
Tandoor's own scraper.

So the feature existed and was unreachable without curl.

## What this adds

A third AI mode in the import dialog: **File · Text · Website**.

```
vue3/src/composables/useFileApi.ts     doAiImportFromSource(providerId, url, text)
vue3/src/pages/RecipeImportPage.vue    aiMode 'link', URL field, handler
vue3/src/locales/{de,en}.json          AIImportLinkHint
```

The handler posts to `plugins/ai-import/from-source/` with the session token
and CSRF header, then feeds the answer into the dialog's existing flow — the
same `importResponse`, the same image chooser, the same keyword chooser.

**It does not save.** The draft goes through the review step the other modes
already use, which is the whole point of the plugin: an import nobody read is
how a library rots.

## Why a third mode and not a replacement

`/api/recipe-from-source/` is right for pages that publish usable schema.org
data, and it costs nothing. The new mode is for pages that do not — a Chefkoch
page without structured data currently imports as *"Spaghetti Carbonara -
schnell & einfach"* with three steps under a marketing title.

## Verified

Against a container built from this branch, talking to the live LiteLLM and
the same database as production:

```
POST /plugins/ai-import/from-source/  {"url": "https://holunderweg18.de/zimtschnecken-rezept/"}
→ name: Schwedische Zimtschnecken
  steps: 8
  unknown_foods: []
  rejected_tags: ['Zubereitung::Backen und Überbacken', 'Mahlzeit::Frühstück']
```

The two rejected tags are the feature working: the model proposed tags the
space does not have, and the plugin returned them instead of creating a fourth
overlapping taxonomy.

**The Zimtschnecken case is the one my script failed at.** 75 g butter in the
dough and 75 g in the filling ended up as 150 g in the dough. The plugin keeps
them apart, because it assigns ingredients per group rather than per name.

Frontend verified by serving the chunk:
`GET /static/vue3/assets/RecipeImportPage-*.js` contains
`value:\`link\`` next to `$t(\`Website\`)`.

## Three configuration facts, all found by hitting the failure

1. `AI_ALLOWED_URLS` must contain the provider URL or every AI call fails with
   *"AI provider URL not allowed"*, which reads like a bad key.
2. The model name needs an `openai/` prefix when the provider is an
   OpenAI-compatible gateway reached via `api_base`, or LiteLLM answers
   *"LLM Provider NOT provided"*.
3. The container must be on the gateway's Docker network. Attached by hand it
   survives until the next restart and fails as a bare connection error.

## Testing note

`Client.force_login` plus a direct `POST` is the fastest way to exercise the
endpoint; the HTTP route needs a session cookie *and* the CSRF token, and a
missing one returns the SPA's HTML with status 200 rather than an error. A test
that only checks the status code sees success.

Running the check inside the container needs `PYTHONPATH=/opt/recipes` and the
database password in `POSTGRES_PASSWORD`, because `*_FILE` secrets are only
read by the entrypoint.

## Still open

The plugin is not deployed. Production runs upstream `vabene1111/recipes:2.7.2`,
so this branch has to be built and the compose image repointed before the
household sees the tab.
