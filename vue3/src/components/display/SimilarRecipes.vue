<template>
    <section v-if="picks.length" class="similar">
        <div class="similar__head">
            <h2 class="similar__title">Passt dazu</h2>
            <span v-if="why" class="similar__why">{{ why }}</span>
        </div>
        <div class="similar__grid">
            <book-recipe-tile v-for="pick in picks" :key="pick.id" :recipe="pick"></book-recipe-tile>
        </div>
    </section>
</template>

<script setup lang="ts">
import {computed, onMounted, ref, watch} from "vue";
import {ApiApi, Keyword, Recipe, RecipeOverview} from "@/openapi";
import BookRecipeTile from "@/components/display/BookRecipeTile.vue";

const props = defineProps({
    recipe: {type: Object as () => Recipe, required: true},
})

const picks = ref<RecipeOverview[]>([])
const reason = ref('')

/**
 * Two anchors, no model: the most specific branch of the cuisine tree and what the dish is
 * made of. "Italien" alone returns half the shelf; "Italien und Haehnchen" returns the four
 * dishes that are actually interchangeable.
 */
const AXES = ['Herkunft', 'Hauptzutat', 'Beilage']

function deepest(axis: string): Keyword | null {
    const branch = (props.recipe.keywords ?? []).filter(keyword => keyword.name.startsWith(`${axis}::`))
    if (!branch.length) return null
    // the deepest path is the most specific one: Herkunft::Mittelmeer::Italien::Toskana
    return branch.reduce((deepestSoFar, keyword) =>
        keyword.name.split('::').length > deepestSoFar.name.split('::').length ? keyword : deepestSoFar)
}

const anchors = computed(() => {
    return AXES.map(axis => ({axis, keyword: deepest(axis)})).filter(entry => entry.keyword !== null) as
        {axis: string, keyword: Keyword}[]
})

const why = computed(() => reason.value)

let lastLoaded: number | null = null

function load() {
    const id = props.recipe.id
    if (!id || id === lastLoaded) return
    const found = anchors.value
    if (!found.length) return
    lastLoaded = id
    const ids = found.map(entry => entry.keyword.id as number)
    new ApiApi().apiRecipeList({
        keywordsOr: ids,
        pageSize: 13,
        // the ones the household actually cooks, not the newest import
        sortOrder: '-times_cooked',
    }).then((response) => {
        const others = (response.results ?? []).filter(recipe => recipe.id !== id)
        picks.value = others.slice(0, 4)
        reason.value = found.map(entry => entry.keyword.label).join(' · ')
    }).catch(() => {
        picks.value = []
    })
}

onMounted(load)
watch(() => props.recipe.id, () => {
    lastLoaded = null
    load()
})
</script>

<style scoped>
.similar {
    margin-top: 2.2rem;
    padding-top: 1.4rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .1);
}

.similar__head {
    display: flex;
    align-items: baseline;
    gap: .7rem;
    flex-wrap: wrap;
    margin-bottom: .9rem;
}

.similar__title {
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: -.01em;
}

.similar__why {
    font-size: .82rem;
    color: rgba(var(--v-theme-on-surface), .5);
}

.similar__grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .9rem;
}

@media (min-width: 700px) {
    .similar__grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
}
</style>
