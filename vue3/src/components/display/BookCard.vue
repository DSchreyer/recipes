<template>
    <div ref="root" class="book-tile" role="link" tabindex="0"
         @click="open" @keydown.enter="open" @keydown.space.prevent="open">

        <div class="book-tile__cover">
            <v-img v-if="hero" :src="hero" cover :alt="''" class="book-tile__img book-tile__hero"></v-img>
            <div v-else class="book-tile__mosaic">
                <div class="book-tile__cell" v-for="i in 4" :key="i">
                    <v-img v-if="covers[i - 1]" :src="covers[i - 1]" cover :alt="''" class="book-tile__img"></v-img>
                    <div v-else class="book-tile__blank"></div>
                </div>
            </div>
            <div class="book-tile__scrim"></div>

            <v-btn class="book-tile__menu" :icon="'$menu'" size="default" variant="flat"
                   density="comfortable" :aria-label="'Aktionen für ' + book.name"
                   @click.stop="actionsOpen = true"></v-btn>
        </div>

        <div class="book-tile__body">
            <div class="book-tile__name">{{ book.name }}</div>
            <div class="book-tile__desc">{{ book.description }}</div>
            <div class="book-tile__meta">
                <span v-if="loaded">{{ count }} {{ count === 1 ? 'Rezept' : 'Rezepte' }}</span>
                <span v-else class="book-tile__skeleton"></span>
            </div>
        </div>

        <model-edit-dialog v-model="editOpen" model="RecipeBook" :item="book"
                           @save="emit('changed')" @delete="emit('deleted', book)"></model-edit-dialog>

        <v-dialog v-model="actionsOpen" max-width="360">
            <v-card>
                <v-card-title class="text-body-1 font-weight-bold">{{ book.name }}</v-card-title>
                <v-list>
                    <v-list-item prepend-icon="$edit" title="Bearbeiten"
                                 @click="actionsOpen = false; editOpen = true"></v-list-item>
                    <v-list-item prepend-icon="$delete" base-color="error" title="Löschen"
                                 @click="actionsOpen = false; confirmDelete = true"></v-list-item>
                </v-list>
            </v-card>
        </v-dialog>

        <v-dialog v-model="confirmDelete" max-width="420">
            <v-card>
                <v-card-title>Kochbuch löschen?</v-card-title>
                <v-card-text>„{{ book.name }}“ verschwindet. Die Rezepte darin bleiben erhalten.</v-card-text>
                <v-card-actions>
                    <v-btn variant="text" @click="confirmDelete = false">Abbrechen</v-btn>
                    <v-btn color="error" variant="flat" @click="remove">Löschen</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from "vue";
import {useRouter} from "vue-router";
import {ApiApi, RecipeBook, RecipeOverview} from "@/openapi";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";

const props = defineProps<{ book: RecipeBook }>()
const emit = defineEmits(['deleted', 'changed'])

const router = useRouter()
const root = ref<HTMLElement | null>(null)

const covers = ref<string[]>([])
/** fewer than four photos: one of them fills the whole cover instead of a mosaic */
const hero = computed(() => covers.value.length > 0 && covers.value.length < 4 ? covers.value[0] : '')
const count = ref(0)
const loaded = ref(false)

const actionsOpen = ref(false)
const editOpen = ref(false)
const confirmDelete = ref(false)

let observer: IntersectionObserver | null = null

onMounted(() => {
    observer = new IntersectionObserver(entries => {
        if (entries.some(e => e.isIntersecting)) {
            observer?.disconnect()
            observer = null
            load()
        }
    }, {rootMargin: '400px'})
    if (root.value) observer.observe(root.value)
    else load()
})

onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
})

function open() {
    router.push({name: 'BookViewPage', params: {bookId: props.book.id!}})
}

/**
 * A book's cards, cover and count all come from its recipes: the book model has no
 * image and no count, and a filter book holds no entries of its own. One request
 * per book, only when the tile is near the viewport — 33 books are 33 requests.
 */
async function load() {
    const api = new ApiApi()
    try {
        if (props.book.filter) {
            const r = await api.apiRecipeList({filter: props.book.filter.id!, pageSize: 12})
            count.value = r.count ?? r.results.length
            covers.value = r.results.map((o: RecipeOverview) => o.image).filter((i): i is string => !!i).slice(0, 4)
        } else if (props.book.id) {
            const r = await api.apiRecipeBookEntryList({book: props.book.id, pageSize: 12})
            const overviews = r.results.map(e => e.recipeContent).filter((o): o is RecipeOverview => !!o)
            count.value = r.count ?? overviews.length
            covers.value = overviews.map(o => o.image).filter((i): i is string => !!i).slice(0, 4)
        }
    } catch (e) {
        // a book whose recipes cannot be read keeps its placeholder cover; the
        // page must not fail because one filter is stale
    } finally {
        loaded.value = true
    }
}

async function remove() {
    confirmDelete.value = false
    try {
        await new ApiApi().apiRecipeBookDestroy({id: props.book.id!})
        emit('deleted', props.book)
    } catch (e) {
        emit('changed')
    }
}
</script>

<style scoped>
.book-tile {
    display: flex;
    flex-direction: column;
    width: 100%;
    background: rgb(var(--v-theme-surface));
    border-radius: 14px;
    overflow: hidden;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(60, 40, 25, .10), 0 8px 24px -18px rgba(60, 40, 25, .55);
    transition: transform .18s ease, box-shadow .18s ease;
    outline: none;
}

.book-tile:hover,
.book-tile:focus-visible {
    transform: translateY(-2px);
    box-shadow: 0 2px 4px rgba(60, 40, 25, .12), 0 18px 34px -22px rgba(60, 40, 25, .65);
}

.book-tile:focus-visible {
    box-shadow: 0 0 0 2px rgb(var(--v-theme-primary)), 0 18px 34px -22px rgba(60, 40, 25, .65);
}

/* a definite 4:3 box via padding, so no flex maths can squash the cover */
.book-tile__cover {
    position: relative;
    flex: none;
    height: 0;
    padding-top: 75%;
    background: rgb(var(--v-theme-recipeImagePlaceholderBg));
    overflow: hidden;
}

.book-tile__mosaic {
    position: absolute;
    inset: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 2px;
    height: 100%;
    transition: transform .35s ease;
}

.book-tile:hover .book-tile__mosaic {
    transform: scale(1.03);
}

.book-tile__cell {
    overflow: hidden;
    background: rgb(var(--v-theme-recipeImagePlaceholderBg));
}

.book-tile__img {
    height: 100%;
    width: 100%;
}

.book-tile__hero {
    position: absolute;
    inset: 0;
    transition: transform .35s ease;
}

.book-tile:hover .book-tile__hero {
    transform: scale(1.03);
}

.book-tile__blank {
    height: 100%;
    background: linear-gradient(135deg, rgba(185, 135, 102, .16), rgba(130, 170, 139, .16));
}

.book-tile__scrim {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(30, 22, 16, .30), rgba(30, 22, 16, 0) 45%);
    pointer-events: none;
}

.book-tile__menu {
    position: absolute;
    top: 8px;
    right: 8px;
    background: rgba(255, 255, 255, .92);
    color: rgba(30, 22, 16, .8);
    box-shadow: 0 1px 4px rgba(30, 22, 16, .28);
    opacity: 0;
    transition: opacity .15s ease;
}

.book-tile:hover .book-tile__menu,
.book-tile__menu:focus-visible {
    opacity: 1;
}

@media (hover: none) {
    .book-tile__menu {
        opacity: 1;
    }
}

.book-tile__body {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px 14px;
}

.book-tile__name {
    font-size: 1.02rem;
    font-weight: 600;
    line-height: 1.25;
    min-height: 2.5em;
    color: rgb(var(--v-theme-on-surface));
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.book-tile__desc {
    font-size: .84rem;
    line-height: 1.35;
    min-height: 2.7em;
    color: rgba(var(--v-theme-on-surface), .68);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.book-tile__meta {
    margin-top: auto;
    padding-top: 2px;
    font-size: .82rem;
    letter-spacing: .01em;
    color: rgba(var(--v-theme-on-surface), .62);
}

.book-tile__skeleton {
    display: inline-block;
    width: 62px;
    height: 10px;
    border-radius: 6px;
    background: rgba(var(--v-theme-on-surface), .12);
}
</style>
