<template>
    <v-container>
        <div class="books-head">
            <div>
                <h1 class="books-head__title">Kochbücher</h1>
                <div class="books-head__sub" v-if="!loading">{{ books.length }} Bücher</div>
            </div>
            <div class="books-head__tools">
                <v-text-field v-model="search" class="books-search" density="compact" variant="solo-filled"
                              flat hide-details clearable prepend-inner-icon="$search"
                              placeholder="Kochbuch suchen"></v-text-field>
                <v-btn color="create" variant="flat" prepend-icon="$create" class="books-new"
                       @click="createOpen = true">Neues Kochbuch
                </v-btn>
            </div>
        </div>

        <model-edit-dialog v-model="createOpen" model="RecipeBook"
                           @create="(b: RecipeBook) => { books.push(b); createOpen = false }"></model-edit-dialog>

        <template v-if="loading">
            <v-row>
                <v-col v-for="i in 6" :key="i" cols="6" md="4">
                    <div class="books-ghost">
                        <div class="books-ghost__cover"></div>
                        <div class="books-ghost__line"></div>
                        <div class="books-ghost__line books-ghost__line--short"></div>
                    </div>
                </v-col>
            </v-row>
        </template>

        <template v-else>
            <section v-for="section in sections" :key="section.key" class="books-section">
                <div class="books-section__head">
                    <h2>{{ section.label }}</h2>
                    <span>· {{ section.books.length }}</span>
                </div>
                <v-row>
                    <v-col v-for="b in section.books" :key="b.id" cols="6" md="4">
                        <book-card :book="b" @deleted="removeBook"></book-card>
                    </v-col>
                </v-row>
            </section>

            <div class="books-empty" v-if="sections.length === 0">
                Kein Kochbuch heißt „{{ search }}“.
            </div>
        </template>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from "vue";
import {ApiApi, RecipeBook} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import BookCard from "@/components/display/BookCard.vue";

const loading = ref(true)
const books = ref<RecipeBook[]>([])
const search = ref('')
const createOpen = ref(false)

onMounted(loadBooks)

async function loadBooks() {
    const api = new ApiApi()
    loading.value = true
    try {
        const r = await api.apiRecipeBookList({pageSize: 200})
        books.value = r.results
    } catch (e) {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR)
    } finally {
        loading.value = false
    }
}

function removeBook(book: RecipeBook) {
    books.value = books.value.filter(b => b.id !== book.id)
}

/**
 * The shelf, in three groups. The names carry the group: a Herkunft book is
 * "<Land> Küche" with the space, a Grundlagen book starts with "Grundlagen",
 * everything else is a dish collection. The space matters — "Feierabendküche" is
 * one word and a dish book, not an origin. Order inside a group is alphabetical.
 */
const SECTION_DEFS = [
    {key: 'herkunft', label: 'Herkunft'},
    {key: 'gerichte', label: 'Gerichte'},
    {key: 'grundlagen', label: 'Grundlagen'},
]

function groupOf(book: RecipeBook): string {
    const name = (book.name ?? '').trim()
    if (/^grundlagen/i.test(name)) return 'grundlagen'
    if (/\sKüche$/i.test(name)) return 'herkunft'
    return 'gerichte'
}

const sections = computed(() => {
    const needle = search.value.trim().toLowerCase()
    const matches = (b: RecipeBook) =>
        needle === '' || (b.name ?? '').toLowerCase().includes(needle) ||
        (b.description ?? '').toLowerCase().includes(needle)

    return SECTION_DEFS
        .map(def => ({
            ...def,
            books: books.value
                .filter(b => groupOf(b) === def.key && matches(b))
                .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'de')),
        }))
        .filter(section => section.books.length > 0)
})
</script>

<style scoped>
.books-head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
    margin: 4px 0 20px;
}

.books-head__title {
    font-size: 1.9rem;
    font-weight: 650;
    letter-spacing: -.01em;
    line-height: 1.1;
}

.books-head__sub {
    margin-top: 4px;
    font-size: .82rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

.books-head__tools {
    display: flex;
    align-items: center;
    gap: 10px;
}

.books-search {
    flex: none;
    width: 300px;
}

.books-section + .books-section {
    margin-top: 18px;
}

.books-section__head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin: 0 0 8px 2px;
}

.books-section__head h2 {
    font-size: .95rem;
    font-weight: 600;
    letter-spacing: .02em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .62);
}

.books-section__head span {
    font-size: .8rem;
    color: rgba(var(--v-theme-on-surface), .45);
}

.books-empty {
    padding: 40px 0;
    font-size: .95rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

.books-ghost__cover {
    aspect-ratio: 4 / 3;
    border-radius: 14px;
    background: rgba(var(--v-theme-on-surface), .07);
}

.books-ghost__line {
    height: 12px;
    margin-top: 10px;
    border-radius: 6px;
    background: rgba(var(--v-theme-on-surface), .07);
}

.books-ghost__line--short {
    width: 55%;
}

@media (max-width: 599px) {
    .books-head__title {
        font-size: 1.55rem;
    }

    .books-head__tools {
        width: 100%;
        flex-direction: column;
        align-items: stretch;
    }

    .books-new {
        justify-content: center;
    }

    .books-search {
        flex: 1 1 auto;
        width: auto;
        min-width: 0;
    }

    .books-new {
        flex-shrink: 0;
    }
}
</style>
