<template>
    <div class="recipe-tile" role="link" tabindex="0"
         @click="open" @keydown.enter="open" @keydown.space.prevent="open">

        <div class="recipe-tile__cover">
            <recipe-image :recipe="recipe" height="100%" width="100%"></recipe-image>
        </div>

        <div class="recipe-tile__body">
            <!-- The verdict shares the meta line: a rating that costs no row of its
                 own, so an uncooked tile is as short as it was before ratings. -->
            <div class="recipe-tile__meta">
                <span class="recipe-tile__meta-text">{{ meta }}</span>
                <!-- stars only: the number would cost a third of the line, and at
                     quarter steps the fill already says it. The aria label keeps it. -->
                <rating-stars v-if="recipe.rating" :value="recipe.rating" size="xs"
                              :show-value="false" class="recipe-tile__meta-rating"></rating-stars>
            </div>
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
import RatingStars from "@/components/display/RatingStars.vue";

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
    /* Fixed one-line box: the meta text and the star row share it, and a fixed
       height means a rated tile does not start its title lower than its neighbour. */
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    height: 1.55em;
    font-size: .7rem;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: rgb(var(--v-theme-primary));
}

.recipe-tile__meta-text {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

/* On a phone the tile is ~170px wide and has room for one of the two, not both:
   the label alone already needs 156px. Where there is a rating, the stars win and
   the date stays on the recipe page; where there is none, the label keeps its room. */
@media (max-width: 700px) {
    .recipe-tile__meta:has(.rating-stars) .recipe-tile__meta-text {
        display: none;
    }
}

/* no uppercase, no tracking: the stars belong to the page, not to the label */
.recipe-tile__meta-rating {
    flex: none;
    letter-spacing: normal;
    text-transform: none;
    /* the gold at full strength read as a badge; a notch down makes it a footnote */
    opacity: .82;
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
    /* two lines, always reserved: one line of description inside a two-line box
       reads as the card's own gap, and a one-line tile used to look airy while its
       neighbour looked full */
    min-height: 2.7em;
    line-height: 1.35;
    color: rgba(var(--v-theme-on-surface), .66);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.recipe-tile__foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    align-content: flex-start;
    gap: 4px;
    margin-top: auto;
    padding-top: 6px;
    /* one row of chips plus the remainder link; a fixed height used to cut the
       second chip row in half on a phone, min-height never clips */
    min-height: 30px;
}

/* flows after the last chip instead of taking a line of its own */
.recipe-tile__more {
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
