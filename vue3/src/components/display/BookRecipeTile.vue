<template>
    <div class="recipe-tile" role="link" tabindex="0"
         @click="open" @keydown.enter="open" @keydown.space.prevent="open">

        <div class="recipe-tile__cover">
            <recipe-image :recipe="recipe" height="100%" width="100%"></recipe-image>
        </div>

        <div class="recipe-tile__body">
            <div v-if="meta" class="recipe-tile__meta">{{ meta }}</div>
            <div class="recipe-tile__name">{{ recipe.name }}</div>
            <div class="recipe-tile__blurb">{{ recipe.description }}</div>
            <div class="recipe-tile__foot">
                <v-chip v-for="chip in chips" :key="chip.axis" size="x-small" label variant="tonal"
                        class="recipe-tile__chip">{{ chip.value }}</v-chip>
                <button v-if="moreCount > 0" class="recipe-tile__more" @click.stop="showAll = true">
                    +{{ moreCount }} Merkmale
                </button>
            </div>
        </div>

        <v-dialog v-model="showAll" max-width="560">
            <v-card>
                <v-card-title class="d-flex align-center">
                    {{ recipe.name }}
                    <v-spacer></v-spacer>
                    <v-btn icon="$close" variant="text" size="small" @click="showAll = false"></v-btn>
                </v-card-title>
                <v-card-subtitle class="pb-2">Alle Merkmale</v-card-subtitle>
                <v-card-text class="merkmale">
                    <section v-for="group in groups" :key="group.axis" class="merkmale__group">
                        <h3 class="merkmale__axis">{{ group.axis }}</h3>
                        <div class="merkmale__chips">
                            <v-chip v-for="value in group.values" :key="value" size="small" label
                                    variant="tonal">{{ value }}</v-chip>
                        </div>
                    </section>
                </v-card-text>
            </v-card>
        </v-dialog>
    </div>
</template>

<script setup lang="ts">
import {computed, ref} from "vue";
import {useRouter} from "vue-router";
import {RecipeOverview} from "@/openapi";
import RecipeImage from "@/components/display/RecipeImage.vue";
import {axisChips, groupedKeywords} from "@/utils/recipe_axes";

const props = defineProps<{ recipe: RecipeOverview, meta?: string }>()

const router = useRouter()
const showAll = ref(false)

const chips = computed(() => axisChips(props.recipe.keywords))

const groups = computed(() => groupedKeywords(props.recipe.keywords))

/** how many Merkmale the dialog holds, counted the same way the groups are built */
const moreCount = computed(() => groups.value.reduce((n, g) => n + g.values.length, 0) - chips.value.length)

function open() {
    router.push({name: 'RecipeViewPage', params: {id: props.recipe.id!}})
}
</script>

<style scoped>
.recipe-tile {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: rgb(var(--v-theme-surface));
    border-radius: 14px;
    overflow: hidden;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(60, 40, 25, .10), 0 8px 24px -18px rgba(60, 40, 25, .55);
    transition: transform .18s ease, box-shadow .18s ease;
    outline: none;
}

.recipe-tile:hover,
.recipe-tile:focus-visible {
    transform: translateY(-2px);
    box-shadow: 0 2px 4px rgba(60, 40, 25, .12), 0 18px 34px -22px rgba(60, 40, 25, .65);
}

.recipe-tile:focus-visible {
    box-shadow: 0 0 0 2px rgb(var(--v-theme-primary)), 0 18px 34px -22px rgba(60, 40, 25, .65);
}

/* definite 4:3 box; the image fills it absolutely so flex cannot squash it */
.recipe-tile__cover {
    position: relative;
    flex: none;
    height: 0;
    padding-top: 75%;
    background: rgb(var(--v-theme-recipeImagePlaceholderBg));
    overflow: hidden;
}

.recipe-tile__cover > * {
    position: absolute;
    inset: 0;
    height: 100%;
    width: 100%;
}

.recipe-tile__body {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px 14px;
    flex-grow: 1;
}

.recipe-tile__meta {
    font-size: .7rem;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: rgb(var(--v-theme-primary));
}

.recipe-tile__name {
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.25;
    min-height: 2.5em;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.recipe-tile__blurb {
    font-size: .82rem;
    min-height: 1.35em;
    line-height: 1.35;
    color: rgba(var(--v-theme-on-surface), .66);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.recipe-tile__foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    align-content: flex-start;
    gap: 4px;
    margin-top: auto;
    padding-top: 6px;
    height: 52px;
    overflow: hidden;
}

/* always on its own line, so every tile in a row is exactly as tall */
.recipe-tile__more {
    flex-basis: 100%;
    text-align: left;
    border: 0;
    background: none;
    padding: 2px 4px;
    font-size: .74rem;
    color: rgba(var(--v-theme-on-surface), .55);
    text-decoration: underline;
    cursor: pointer;
}

.recipe-tile__more:hover {
    color: rgb(var(--v-theme-primary));
}

.merkmale {
    max-height: 55vh;
    overflow-y: auto;
    padding-top: 0;
}

.merkmale__group + .merkmale__group {
    margin-top: 14px;
}

.merkmale__axis {
    margin-bottom: 6px;
    font-size: .68rem;
    font-weight: 600;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .5);
}

.merkmale__chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
</style>
