<template>
    <v-container>
        <v-btn variant="text" size="small" :to="{name: 'BooksPage'}" prepend-icon="$books" class="book-back">
            Kochbücher
        </v-btn>

        <header class="book-head">
            <h1 class="book-head__title">{{ book.name }}</h1>
            <div class="book-head__shared" v-if="book.shared && book.shared.length">
                <span>Geteilt mit</span>
                <v-chip v-for="u in book.shared" :key="u.id" size="x-small" label variant="tonal">
                    {{ u.displayName }}
                </v-chip>
            </div>
            <p class="book-head__lede" v-if="book.description">{{ book.description }}</p>
            <div class="book-head__count" v-if="!loading">{{ recipes.length }} Rezepte</div>
        </header>

        <v-row v-if="loading">
            <v-col v-for="i in 6" :key="i" cols="6" md="4">
                <div class="book-ghost">
                    <div class="book-ghost__cover"></div>
                    <div class="book-ghost__line"></div>
                </div>
            </v-col>
        </v-row>

        <v-row v-else>
            <v-col v-for="recipe in recipes" :key="recipe.id" cols="6" md="4">
                <book-recipe-tile :recipe="recipe"></book-recipe-tile>
            </v-col>
        </v-row>

        <div class="book-empty" v-if="!loading && recipes.length === 0">
            In diesem Kochbuch liegt noch kein Rezept.
        </div>
    </v-container>
</template>

<script setup lang="ts">
import {onMounted, ref} from "vue";
import {ApiApi, RecipeBook, RecipeOverview} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import BookRecipeTile from "@/components/display/BookRecipeTile.vue";

const props = defineProps({bookId: {type: String, required: true}})

const loading = ref(true)
const book = ref<RecipeBook>({} as RecipeBook)
const recipes = ref<RecipeOverview[]>([])

onMounted(load)

/**
 * A book is its manual entries plus the recipes its saved filter matches. The
 * whole book loads at once — a cookbook is a shelf, not a slideshow — so there is
 * no pagination here on purpose.
 */
async function load() {
    const api = new ApiApi()
    loading.value = true
    try {
        const loaded = await api.apiRecipeBookRetrieve({id: props.bookId})
        book.value = loaded

        const overviews: RecipeOverview[] = []
        const seen = new Set<number>()

        const push = (overview?: RecipeOverview) => {
            if (!overview || !overview.id || seen.has(overview.id)) return
            seen.add(overview.id)
            overviews.push(overview)
        }

        if (loaded.id) {
            const entries = await api.apiRecipeBookEntryList({book: loaded.id, pageSize: 200})
            entries.results.forEach(entry => push(entry.recipeContent))
        }
        if (loaded.filter && loaded.filter.id) {
            const filtered = await api.apiRecipeList({filter: loaded.filter.id, pageSize: 500})
            filtered.results.forEach(push)
        }

        recipes.value = await mostCookedFirst(api, overviews)
    } catch (e) {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, e)
    } finally {
        loading.value = false
    }
}

/** most cooked first, then alphabetically; falls back to A–Z when nothing is logged */
async function mostCookedFirst(api: ApiApi, list: RecipeOverview[]): Promise<RecipeOverview[]> {
    const byName = (a: RecipeOverview, b: RecipeOverview) =>
        (a.name ?? '').localeCompare(b.name ?? '', 'de')

    const cooks = new Map<number, number>()
    try {
        const logs = await api.apiCookLogList({pageSize: 1000})
        for (const log of logs.results) {
            const recipe = log.recipe
            const id = typeof recipe === 'number' ? recipe : (recipe as { id?: number } | undefined)?.id
            if (id) cooks.set(id, (cooks.get(id) ?? 0) + 1)
        }
    } catch (e) {
        // an unreadable cook log only costs the sorting, not the book
    }

    if (cooks.size === 0) return [...list].sort(byName)
    return [...list].sort((a, b) => {
        const ca = cooks.get(a.id!) ?? 0
        const cb = cooks.get(b.id!) ?? 0
        return ca === cb ? byName(a, b) : cb - ca
    })
}
</script>

<style scoped>
.book-back {
    margin-bottom: 2px;
}

.book-head {
    margin: 2px 0 20px;
}

.book-head__title {
    font-size: 1.9rem;
    font-weight: 650;
    letter-spacing: -.01em;
    line-height: 1.1;
}

.book-head__shared {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
    font-size: .78rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

.book-head__lede {
    margin-top: 8px;
    max-width: 68ch;
    font-size: .95rem;
    line-height: 1.45;
    color: rgba(var(--v-theme-on-surface), .72);
}

.book-head__count {
    margin-top: 8px;
    font-size: .8rem;
    color: rgba(var(--v-theme-on-surface), .5);
}

.book-ghost__cover {
    aspect-ratio: 4 / 3;
    border-radius: 14px;
    background: rgba(var(--v-theme-on-surface), .07);
}

.book-ghost__line {
    height: 12px;
    margin-top: 10px;
    border-radius: 6px;
    background: rgba(var(--v-theme-on-surface), .07);
}

.book-empty {
    padding: 40px 0;
    font-size: .95rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

@media (max-width: 599px) {
    .book-head__title {
        font-size: 1.55rem;
    }
}
</style>
