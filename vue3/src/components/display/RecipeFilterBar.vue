<template>
    <div class="rfb">
        <div class="rfb__row">
            <!-- Sortieren -->
            <v-menu location="bottom start">
                <template v-slot:activator="{ props: menu }">
                    <div class="rfb__chip" :class="{ 'rfb__chip--on': !!state.sort }" v-bind="menu" role="button" tabindex="0">
                        <i class="fa-solid fa-arrow-down-wide-short rfb__icon"/>
                        <span class="rfb__label">{{ sortLabel }}</span>
                        <button v-if="state.sort" class="rfb__x" type="button" aria-label="Sortierung zurücksetzen"
                                @click.stop="setSort('')"><i class="fa-solid fa-xmark"/></button>
                        <i v-else class="fa-solid fa-chevron-down rfb__chev"/>
                    </div>
                </template>
                <v-list density="compact" class="rfb__panel">
                    <v-list-item v-for="option in sortOptions" :key="option.value"
                                 :active="state.sort === option.value"
                                 @click="setSort(option.value)">
                        <v-list-item-title>{{ option.title }}</v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>

            <!-- Bewertung -->
            <v-menu location="bottom start">
                <template v-slot:activator="{ props: menu }">
                    <div class="rfb__chip" :class="{ 'rfb__chip--on': state.rating !== null }" v-bind="menu" role="button" tabindex="0">
                        <i class="fa-solid fa-star rfb__icon"/>
                        <span class="rfb__label">{{ ratingLabel }}</span>
                        <button v-if="state.rating !== null" class="rfb__x" type="button" aria-label="Bewertung zurücksetzen"
                                @click.stop="setRating(state.rating)"><i class="fa-solid fa-xmark"/></button>
                        <i v-else class="fa-solid fa-chevron-down rfb__chev"/>
                    </div>
                </template>
                <v-list density="compact" class="rfb__panel">
                    <v-list-item v-for="step in ratingSteps" :key="step" :active="state.rating === step"
                                 @click="setRating(step)">
                        <v-list-item-title>
                            <span class="rfb__stars"><rating-stars :value="step" size="xs" :show-value="false"/></span>
                            <span class="rfb__hint">{{ countOf.rating[step] ?? 0 }}</span>
                        </v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>

            <!-- Arbeitszeit -->
            <v-menu location="bottom start">
                <template v-slot:activator="{ props: menu }">
                    <div class="rfb__chip" :class="{ 'rfb__chip--on': state.time !== null }" v-bind="menu" role="button" tabindex="0">
                        <i class="fa-solid fa-clock rfb__icon"/>
                        <span class="rfb__label">{{ state.time !== null ? `bis ${state.time} Min` : 'Arbeitszeit' }}</span>
                        <button v-if="state.time !== null" class="rfb__x" type="button" aria-label="Arbeitszeit zurücksetzen"
                                @click.stop="setTime(state.time)"><i class="fa-solid fa-xmark"/></button>
                        <i v-else class="fa-solid fa-chevron-down rfb__chev"/>
                    </div>
                </template>
                <v-list density="compact" class="rfb__panel">
                    <v-list-item v-for="step in timeSteps" :key="step" :active="state.time === step"
                                 @click="setTime(step)">
                        <v-list-item-title>
                            bis {{ step }} Minuten
                            <span class="rfb__hint">{{ countOf.time[step] ?? 0 }}</span>
                        </v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>

            <!-- one chip per keyword axis the library actually carries -->
            <v-menu v-for="axis in axes" :key="axis.name" location="bottom start">
                <template v-slot:activator="{ props: menu }">
                    <div class="rfb__chip" :class="{ 'rfb__chip--on': !!state.axes[axis.name] }" v-bind="menu" role="button" tabindex="0">
                        <i :class="`fa-solid ${axis.icon} rfb__icon`"/>
                        <span class="rfb__label">
                            {{ state.axes[axis.name] ? `${axis.name}: ${selectedLabel(axis)}` : axis.name }}
                        </span>
                        <button v-if="state.axes[axis.name]" class="rfb__x" type="button" :aria-label="`${axis.name} zurücksetzen`"
                                @click.stop="setAxis(axis.name, null)"><i class="fa-solid fa-xmark"/></button>
                        <i v-else class="fa-solid fa-chevron-down rfb__chev"/>
                    </div>
                </template>
                <div class="rfb__panel">
                    <v-text-field v-if="axis.values.length > 10" v-model="searches[axis.name]" density="compact"
                                  variant="underlined" hide-details placeholder="filtern …"
                                  prepend-inner-icon="$search" class="rfb__filter"/>
                    <v-list density="compact" class="rfb__list rfb__list--scroll">
                        <v-list-item v-if="state.axes[axis.name]" @click="setAxis(axis.name, null)">
                            <v-list-item-title class="rfb__clear">
                                <i class="fa-solid fa-xmark"/> {{ axis.name }} zurücksetzen
                            </v-list-item-title>
                        </v-list-item>
                        <v-list-item v-for="value in visible(axis)" :key="value.id"
                                     :active="state.axes[axis.name] === value.id"
                                     @click="setAxis(axis.name, value.id)">
                            <v-list-item-title>
                                <span :style="{ paddingLeft: `${(value.depth - 1) * 12}px` }">
                                    {{ value.label }}<span v-if="value.depth > 1" class="rfb__parent">{{ value.parent }}</span>
                                </span>
                                <span class="rfb__hint">{{ value.count }}</span>
                            </v-list-item-title>
                        </v-list-item>
                        <v-list-item v-if="visible(axis).length === 0">
                            <v-list-item-title class="rfb__hint">nichts gefunden</v-list-item-title>
                        </v-list-item>
                    </v-list>
                </div>
            </v-menu>

            <button v-if="activeCount" class="rfb__reset" type="button" @click="reset">
                alles zurücksetzen <span class="rfb__reset-count">{{ activeCount }}</span>
            </button>
        </div>
    </div>
</template>

<script setup lang="ts">
/**
 * The chip bar: sort, rating, working time, and one menu per keyword axis that the
 * library actually carries ("Herkunft", "Zubereitung", "Mahlzeit", …).
 *
 * Counts come from the recipes rather than from the server: the page already holds the
 * whole shelf, and a chip that says "Italien 39" is worth more than one that says
 * "Italien". Every value is counted at every level of its path, so "Italien" includes
 * the Tuscan dishes — which is also how the server's `include_children` matches them.
 */
import {computed, reactive, ref, watch} from "vue"
import {RecipeOverview} from "@/openapi"
import RatingStars from "@/components/display/RatingStars.vue"

export interface RecipeFilterState {
    sort: string
    rating: number | null
    time: number | null
    axes: Record<string, number | null>
}

const props = defineProps<{
    recipes: RecipeOverview[]
    modelValue: RecipeFilterState
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: RecipeFilterState): void }>()

const state = reactive<RecipeFilterState>({
    sort: props.modelValue.sort,
    rating: props.modelValue.rating,
    time: props.modelValue.time,
    axes: {...props.modelValue.axes},
})

watch(state, () => emit('update:modelValue', {
    sort: state.sort,
    rating: state.rating,
    time: state.time,
    axes: {...state.axes},
}), {deep: true})

/** the page may reset the chips from outside (the Reset button), so follow the prop */
watch(() => props.modelValue, (value) => {
    if (value.sort === state.sort && value.rating === state.rating && value.time === state.time
        && Object.keys(value.axes).every(k => value.axes[k] === state.axes[k])) return
    state.sort = value.sort
    state.rating = value.rating
    state.time = value.time
    for (const key of Object.keys(state.axes)) state.axes[key] = value.axes[key] ?? null
    for (const key of Object.keys(value.axes)) if (!(key in state.axes)) state.axes[key] = value.axes[key]
}, {deep: true})

const sortOptions = [
    {value: '', title: 'Beste Übereinstimmung'},
    {value: '-lastcooked', title: 'Zuletzt gekocht'},
    {value: '-rating', title: 'Bewertung'},
    {value: '-timescooked', title: 'Am häufigsten gekocht'},
    {value: 'name', title: 'Alphabetisch'},
    {value: 'random', title: 'Zufällige Reihenfolge'},
]
const sortLabel = computed(() => state.sort
    ? (sortOptions.find(o => o.value === state.sort)?.title ?? 'Sortieren')
    : 'Sortieren')

const ratingSteps = [4, 3.5, 3, 2.5, 2]
const timeSteps = [15, 30, 45, 60, 90, 120]

const ratingLabel = computed(() => state.rating === null
    ? 'Bewertung'
    : `ab ${String(state.rating).replace('.', ',')} Sternen`)

/**
 * The axes a cook scans for, in reading order. The library also carries `Rezepttyp`,
 * `Quelle`, `Temperatur`, `Saison`, `Vorbereitung`, `Basis` and `Eigenschaft`; they are
 * deliberately left out — thirteen chips already fill two rows, and a bar that needs
 * three reads as a wall. Those remain reachable through the Filter panel.
 */
const AXIS_ORDER: { name: string, icon: string }[] = [
    {name: 'Herkunft', icon: 'fa-earth-europe'},
    {name: 'Rezeptkategorie', icon: 'fa-folder-open'},
    {name: 'Mahlzeit', icon: 'fa-utensils'},
    {name: 'Anlass', icon: 'fa-champagne-glasses'},
    {name: 'Zubereitung', icon: 'fa-fire-burner'},
    {name: 'Methode', icon: 'fa-kitchen-set'},
    {name: 'Ernährung', icon: 'fa-leaf'},
    {name: 'Aufwand', icon: 'fa-gauge-high'},
    {name: 'Hauptzutat', icon: 'fa-drumstick-bite'},
    {name: 'Beilage', icon: 'fa-bowl-rice'},
    {name: 'Fleisch', icon: 'fa-cow'},
    {name: 'Kohlenhydrate', icon: 'fa-bread-slice'},
    {name: 'Protein', icon: 'fa-egg'},
]

/** the same shelf under two spellings is one shelf */
function canonicalAxis(axis: string): string {
    return axis === 'Ernaehrung' ? 'Ernährung' : axis
}

interface AxisValue {
    id: number
    label: string
    depth: number
    parent: string
    count: number
}

/** keyword id for a label, so a click can filter on the server */
const idByLabel = computed(() => {
    const map = new Map<string, number>()
    for (const recipe of props.recipes) {
        for (const keyword of recipe.keywords ?? []) {
            if (keyword.label) map.set(keyword.label, keyword.id)
        }
    }
    return map
})

/** axis name -> its values with counts, counted at every level of the path */
const axes = computed(() => {
    const perAxis = new Map<string, Map<string, Set<number>>>()

    for (const recipe of props.recipes) {
        if (!recipe.id) continue
        for (const keyword of recipe.keywords ?? []) {
            const label = keyword.label
            if (!label || !label.includes('::')) continue
            const path = label.split('::').filter(Boolean)
            if (path.length < 2) continue
            const axis = canonicalAxis(path[0])
            for (let depth = 2; depth <= path.length; depth++) {
                const node = path.slice(0, depth).join('::')
                if (!perAxis.has(axis)) perAxis.set(axis, new Map())
                const nodes = perAxis.get(axis)!
                if (!nodes.has(node)) nodes.set(node, new Set())
                nodes.get(node)!.add(recipe.id)
            }
        }
    }

    const result: { name: string, icon: string, values: AxisValue[] }[] = []
    for (const axis of AXIS_ORDER) {
        const nodes = perAxis.get(axis.name)
        if (!nodes) continue
        const values: AxisValue[] = []
        for (const [node, ids] of nodes) {
            const path = node.split('::')
            const id = idByLabel.value.get(node)
            if (!id) continue
            values.push({
                id,
                label: capitalise(path[path.length - 1]),
                depth: path.length - 1,
                parent: path.length > 2 ? capitalise(path[path.length - 2]) : '',
                count: ids.size,
            })
        }
        if (values.length === 0) continue
        values.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'de'))
        result.push({name: axis.name, icon: axis.icon, values})
    }
    return result
})

/** counts for the two non-keyword chips, over the same shelf */
const countOf = computed(() => {
    const rating: Record<number, number> = {}
    for (const step of ratingSteps) rating[step] = props.recipes.filter(r => (r.rating ?? 0) >= step).length
    const time: Record<number, number> = {}
    for (const step of timeSteps) time[step] = props.recipes.filter(r => !!r.workingTime && r.workingTime <= step).length
    return {rating, time}
})

const searches = reactive<Record<string, string>>({})

function visible(axis: { name: string, values: AxisValue[] }): AxisValue[] {
    const needle = (searches[axis.name] ?? '').trim().toLowerCase()
    if (!needle) return axis.values
    return axis.values.filter(v => v.label.toLowerCase().includes(needle) || v.parent.toLowerCase().includes(needle))
}

function selectedLabel(axis: { name: string, values: AxisValue[] }): string {
    const id = state.axes[axis.name]
    return axis.values.find(v => v.id === id)?.label ?? '—'
}

function setSort(value: string) {
    state.sort = state.sort === value ? '' : value
}

function setRating(value: number) {
    state.rating = state.rating === value ? null : value
}

function setTime(value: number) {
    state.time = state.time === value ? null : value
}

function setAxis(axis: string, id: number | null) {
    state.axes[axis] = state.axes[axis] === id ? null : id
}

const activeCount = computed(() =>
    (state.sort ? 1 : 0) + (state.rating !== null ? 1 : 0) + (state.time !== null ? 1 : 0)
    + Object.values(state.axes).filter(v => v !== null).length)

function reset() {
    state.sort = ''
    state.rating = null
    state.time = null
    for (const key of Object.keys(state.axes)) state.axes[key] = null
}

defineExpose({reset})

function capitalise(value: string): string {
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : value
}
</script>

<style scoped>
.rfb {
    margin: 18px 0 4px;
}

.rfb__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
}

.rfb__chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border: 1px solid rgba(var(--v-theme-on-surface), .18);
    border-radius: 12px;
    background: transparent;
    color: rgba(var(--v-theme-on-surface), .88);
    font-size: .88rem;
    font-weight: 600;
    line-height: 1.1;
    cursor: pointer;
    transition: border-color .15s ease, background-color .15s ease;
}

.rfb__chip:hover {
    border-color: rgba(var(--v-theme-on-surface), .38);
}

.rfb__chip--on {
    border-color: rgba(var(--v-theme-primary), .8);
    background: rgba(var(--v-theme-primary), .16);
    color: rgba(var(--v-theme-on-surface), .98);
}

.rfb__chip--on .rfb__label {
    font-weight: 700;
}

/* the chip stays a menu, but an active one also says how to undo itself */
.rfb__x {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    margin-right: -2px;
    padding: 0;
    border: none;
    border-radius: 6px;
    background: rgba(var(--v-theme-on-surface), .1);
    color: rgba(var(--v-theme-on-surface), .7);
    font-size: .6rem;
    cursor: pointer;
}

.rfb__x:hover {
    background: rgba(var(--v-theme-on-surface), .2);
    color: rgba(var(--v-theme-on-surface), .95);
}

.rfb__chip {
    cursor: pointer;
}

.rfb__icon {
    font-size: .82rem;
    opacity: .68;
}

.rfb__chip--on .rfb__icon {
    opacity: .9;
}

.rfb__chev {
    font-size: .58rem;
    opacity: .45;
}

.rfb__label {
    white-space: nowrap;
}

.rfb__panel {
    min-width: 240px;
    max-width: 340px;
    padding: 4px 0 6px;
    background: rgb(var(--v-theme-surface));
    border-radius: 12px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, .16);
}

.rfb__filter {
    padding: 0 12px;
}

.rfb__list {
    background: transparent;
}

.rfb__list--scroll {
    max-height: 340px;
    overflow-y: auto;
}

.rfb__list :deep(.v-list-item-title) {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 18px;
    font-size: .88rem;
}

.rfb__stars {
    opacity: .75;
}

.rfb__hint {
    font-size: .76rem;
    font-variant-numeric: tabular-nums;
    color: rgba(var(--v-theme-on-surface), .45);
    white-space: nowrap;
}

.rfb__parent {
    margin-left: 6px;
    font-size: .72rem;
    color: rgba(var(--v-theme-on-surface), .4);
}

.rfb__clear {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: .84rem;
    color: rgba(var(--v-theme-on-surface), .6);
}

.rfb__reset {
    margin-left: 2px;
    padding: 6px 4px;
    border: none;
    background: none;
    font-size: .82rem;
    color: rgba(var(--v-theme-on-surface), .55);
    cursor: pointer;
}

.rfb__reset:hover {
    color: rgba(var(--v-theme-on-surface), .85);
}

.rfb__reset-count {
    margin-left: 4px;
    padding: 1px 6px;
    border-radius: 6px;
    background: rgba(var(--v-theme-primary), .16);
    font-size: .74rem;
}

@media (max-width: 700px) {
    .rfb__row {
        gap: 8px;
    }

    .rfb__chip {
        padding: 7px 10px;
        font-size: .82rem;
    }
}
</style>
