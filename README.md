# Tandoor — a household fork

A fork of [Tandoor Recipes](https://github.com/vabene1111/recipes), pinned at
**2.7.8**, run for one household. Everything below is the difference; for
installation, configuration and features take upstream's documentation:
<https://docs.tandoor.dev>.

## What differs from upstream

| Area | Where | Difference |
|---|---|---|
| Cookbook shelf | `vue3/src/pages/BooksPage.vue`, `components/display/BookCard.vue` | covers are a 2x2 mosaic of the book's own recipe photos, the whole card is the link, Bearbeiten/Löschen sit behind a kebab, live name filter, three sections by name |
| Inside a book | `vue3/src/pages/BookViewPage.vue`, `BookRecipeTile.vue`, `utils/recipe_axes.ts` | compact tiles instead of full recipe cards, four axis chips, remaining keywords grouped by axis, most-cooked first, one scroll instead of 19 pages |
| Kitchen plugin | `recipes/plugins/kitchen/` | picker page, quarter-star ratings, cook log, diary bridge to SparkyFitness — see its README |
| AI import | `recipes/plugins/ai_import/` | URL and text import through the plugin's own `/api/` endpoint, per-space prompt and preview — see its README |
| Search and lists | `cookbook/` | search by ingredient food name, the caller's rating on every recipe list; a search costs about 1.1 s |

40 commits on top of the `2.7.8` tag. Nothing upstream was removed.

## Build and deploy

The frontend changes on almost every deploy:

```bash
./deploy-vue.sh 52          # next free tag number
```

The script runs the Vite build, assembles a clean docker context from `HEAD`
plus this worktree's `vue3/src` and the built `cookbook/static/vue3`, builds
`atlas-tandoor:2.7.8-kitchen-v<tag>`, bumps the image tag in
`/opt/atlas/compose/tandoor/compose.yml` and calls `atlasctl deploy tandoor`.
`HEAD` is the base on purpose: this checkout is shared with other work in
progress, and the image must not ship it.

A backend or plugin change needs a full build, same tag, no frontend step:

```bash
docker build -t atlas-tandoor:2.7.8-kitchen-v<tag> .
```

`atlasctl deploy tandoor` only runs `up -d`; the image has to exist first.

After a deploy the browser may keep serving the old bundle from the PWA service
worker — unregister it (or use a private window) before judging a UI change.

## Upstream

Upstream repository, docs and release notes:
<https://github.com/vabene1111/recipes> · <https://docs.tandoor.dev>. Licence
and copyright are upstream's.
