<template>
    <v-container class="today" fluid>
        <header class="today__head">
            <div>
                <h1 class="today__title">Heute</h1>
                <p class="today__date">{{ todayLabel }}</p>
            </div>
            <div class="today__head-actions">
                <v-btn icon="$search" variant="text" :to="{name: 'SearchPage', params: {query: ''}}"
                       aria-label="Rezepte durchsuchen"></v-btn>
            </div>
        </header>

        <section class="today__section">
            <h2 class="today__h2">
                Geplant
                <span v-if="todayPlan.length" class="today__count">{{ todayPlan.length }}</span>
            </h2>

            <div v-if="todayPlan.length" class="plan">
                <article v-for="entry in todayPlan" :key="entry.id" class="plan__row">
                    <div class="plan__thumb" @click="openPlan(entry)">
                        <recipe-image :recipe="entry.recipe ?? undefined" height="100%" width="100%"></recipe-image>
                    </div>
                    <div class="plan__text" @click="openPlan(entry)">
                        <div class="plan__name">{{ planName(entry) }}</div>
                        <div class="plan__meta">{{ planMeta(entry) }}</div>
                    </div>
                    <cook-log-quick v-if="entry.recipe" :recipe="entry.recipe" :servings="entry.servings" compact
                                    class="plan__log"></cook-log-quick>
                </article>
            </div>

            <div v-else class="today__empty">
                <p class="today__empty-text">Nichts geplant für heute.</p>
                <div class="today__empty-actions">
                    <v-btn variant="tonal" color="create" size="small" prepend-icon="$create">
                        Gericht planen
                        <model-edit-dialog model="MealPlan" :item-defaults="{fromDate: new Date()}"
                                           @create="loadPlan"></model-edit-dialog>
                    </v-btn>
                    <v-btn variant="text" size="small" :to="{name: 'MealPlanPage'}">Wochenplan</v-btn>
                </div>
            </div>
        </section>

        <section v-if="upcomingPlan.length" class="today__section">
            <h2 class="today__h2">Die nächsten Tage</h2>
            <div class="soon">
                <div v-for="day in upcomingPlan" :key="day.key" class="soon__day">
                    <div class="soon__label">{{ day.label }}</div>
                    <div class="soon__entries">
                        <span v-for="entry in day.entries" :key="entry.id" class="soon__entry" @click="openPlan(entry)">
                            {{ planName(entry) }}
                        </span>
                    </div>
                </div>
            </div>
        </section>

        <section v-if="cooked.length" class="today__section">
            <h2 class="today__h2">Zuletzt gekocht</h2>
            <div class="today__grid">
                <book-recipe-tile v-for="recipe in cooked" :key="recipe.id" :recipe="recipe"
                                  :meta="lastCookedLabel(recipe)"></book-recipe-tile>
            </div>
        </section>

        <section v-if="added.length" class="today__section">
            <h2 class="today__h2">Neu in der Sammlung</h2>
            <div class="today__grid">
                <book-recipe-tile v-for="recipe in added" :key="recipe.id" :recipe="recipe"
                                  :meta="addedLabel(recipe)"></book-recipe-tile>
            </div>
        </section>

        <div class="today__foot">
            <v-btn variant="text" :to="{name: 'BooksPage'}">Kochbücher</v-btn>
            <v-btn variant="text" :to="{name: 'SearchPage', params: {query: ''}}">Alle Rezepte</v-btn>
            <v-btn variant="text" :to="{name: 'MealPlanPage'}">Wochenplan</v-btn>
        </div>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from "vue";
import {useRouter} from "vue-router";
import {DateTime} from "luxon";
import {ApiApi, MealPlan, RecipeOverview} from "@/openapi";
import RecipeImage from "@/components/display/RecipeImage.vue";
import BookRecipeTile from "@/components/display/BookRecipeTile.vue";
import CookLogQuick from "@/components/display/CookLogQuick.vue";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";

const api = new ApiApi()
const router = useRouter()

const plan = ref<MealPlan[]>([])
const cooked = ref<RecipeOverview[]>([])
const added = ref<RecipeOverview[]>([])

const today = DateTime.now()

const todayLabel = computed(() => today.setLocale('de').toFormat("EEEE, d. MMMM"))

/** an entry belongs to a day when its span covers it; multi-day entries are common */
function entriesOn(day: DateTime): MealPlan[] {
    const start = day.startOf('day')
    const end = day.endOf('day')
    return plan.value.filter((entry) => {
        const from = DateTime.fromJSDate(entry.fromDate).startOf('day')
        const to = DateTime.fromJSDate(entry.toDate ?? entry.fromDate).endOf('day')
        return from <= end && to >= start
    })
}

const todayPlan = computed(() => entriesOn(today))

const upcomingPlan = computed(() => {
    const days = []
    for (let offset = 1; offset <= 6; offset++) {
        const day = today.plus({days: offset})
        const entries = entriesOn(day)
        if (entries.length) {
            days.push({key: day.toISODate()!, label: day.setLocale('de').toFormat('EEEE, d.M.'), entries})
        }
    }
    return days
})

function planName(entry: MealPlan): string {
    return entry.recipe?.name || entry.title || '(ohne Titel)'
}

function planMeta(entry: MealPlan): string {
    const parts = [entry.mealType?.name ?? entry.mealTypeName ?? '']
    if (entry.servings) parts.push(`${entry.servings} Portionen`)
    if (!entry.recipe) parts.push('Notiz')
    return parts.filter(Boolean).join(' · ')
}

function openPlan(entry: MealPlan) {
    if (!entry.recipe) return
    router.push({
        name: 'RecipeViewPage',
        params: {id: String(entry.recipe.id)},
        query: {servings: String(entry.servings ?? '')},
    })
}

function lastCookedLabel(recipe: RecipeOverview): string {
    if (!recipe.lastCooked) return ''
    const day = DateTime.fromJSDate(recipe.lastCooked).startOf('day')
    const diff = today.startOf('day').diff(day, 'days').days
    if (diff <= 0) return 'heute gekocht'
    if (diff === 1) return 'gestern gekocht'
    if (diff < 31) return `vor ${Math.round(diff)} Tagen gekocht`
    return `zuletzt ${day.setLocale('de').toFormat('d. MMM')}`
}

function addedLabel(recipe: RecipeOverview): string {
    if (!recipe.createdAt) return ''
    return `seit ${DateTime.fromJSDate(recipe.createdAt).setLocale('de').toFormat('d. MMM')}`
}

function loadPlan() {
    api.apiMealPlanList({
        fromDate: today.minus({days: 1}).toISODate()!,
        toDate: today.plus({days: 8}).toISODate()!,
        pageSize: 100,
    }).then((r) => {
        plan.value = r.results ?? []
    }).catch(() => {
        plan.value = []
    })
}

function loadCooked() {
    // -lastcooked keeps recipes that were never cooked out of the way, so the
    // strip is the cook log without a second request per entry
    api.apiRecipeList({sortOrder: '-lastcooked', pageSize: 24}).then((r) => {
        cooked.value = (r.results as RecipeOverview[]).filter((recipe) => recipe.lastCooked).slice(0, 8)
    }).catch(() => {
        cooked.value = []
    })
}

function loadAdded() {
    api.apiRecipeList({sortOrder: '-created_at', pageSize: 8}).then((r) => {
        added.value = (r.results as RecipeOverview[]).slice(0, 8)
    }).catch(() => {
        added.value = []
    })
}

onMounted(() => {
    loadPlan()
    loadCooked()
    loadAdded()
})
</script>

<style scoped>
.today {
    max-width: 1100px;
    padding-bottom: 4rem;
}

.today__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.5rem 0 1.75rem;
}

.today__title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2rem, 5vw, 2.8rem);
    font-weight: 600;
    line-height: 1.05;
    letter-spacing: -.01em;
}

.today__date {
    margin-top: .35rem;
    font-size: .92rem;
    color: rgba(var(--v-theme-on-surface), .6);
}

.today__section + .today__section {
    margin-top: 2.25rem;
}

.today__h2 {
    display: flex;
    align-items: center;
    gap: .5rem;
    margin-bottom: .85rem;
    font-size: .74rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .55);
}

.today__count {
    padding: .05rem .4rem;
    border-radius: 999px;
    background: rgba(var(--v-theme-primary), .12);
    color: rgb(var(--v-theme-primary));
    font-size: .7rem;
}

.plan {
    display: flex;
    flex-direction: column;
    gap: .5rem;
}

.plan__row {
    display: flex;
    align-items: center;
    gap: .85rem;
    padding: .6rem;
    border-radius: 14px;
    background: rgb(var(--v-theme-surface));
    box-shadow: 0 1px 2px rgba(60, 40, 25, .08), 0 10px 26px -22px rgba(60, 40, 25, .5);
}

.plan__thumb {
    flex: none;
    width: 56px;
    height: 56px;
    border-radius: 10px;
    overflow: hidden;
    cursor: pointer;
}

.plan__text {
    flex-grow: 1;
    min-width: 0;
    cursor: pointer;
}

.plan__name {
    font-weight: 600;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.plan__meta {
    margin-top: .15rem;
    font-size: .78rem;
    color: rgba(var(--v-theme-on-surface), .6);
}

.plan__log {
    flex: none;
}

.today__empty {
    padding: 1.4rem 1.25rem;
    border-radius: 14px;
    border: 1px dashed rgba(var(--v-theme-on-surface), .18);
    background: rgba(var(--v-theme-surface), .55);
}

.today__empty-text {
    margin-bottom: .9rem;
    color: rgba(var(--v-theme-on-surface), .7);
}

.today__empty-actions {
    display: flex;
    flex-wrap: wrap;
    gap: .5rem;
}

.soon {
    display: flex;
    flex-direction: column;
    gap: .4rem;
}

.soon__day {
    display: flex;
    align-items: baseline;
    gap: .75rem;
    padding: .45rem .1rem;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07);
}

.soon__label {
    flex: none;
    width: 8.5rem;
    font-size: .78rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

.soon__entries {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem .9rem;
}

.soon__entry {
    font-size: .9rem;
    cursor: pointer;
}

.soon__entry:hover {
    color: rgb(var(--v-theme-primary));
}

.today__grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .9rem;
}

@media (min-width: 700px) {
    .today__grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (min-width: 1100px) {
    .today__grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
}

.today__foot {
    display: flex;
    flex-wrap: wrap;
    gap: .25rem;
    margin-top: 2.5rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .08);
}

@media (max-width: 600px) {
    .soon__label {
        width: 6.5rem;
    }

    .today__grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
