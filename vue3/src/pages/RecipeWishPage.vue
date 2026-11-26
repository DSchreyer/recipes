<template>
    <v-container class="wish" fluid>

        <!-- 1 — der Wunsch: one sentence and four constraints -->
        <section v-if="phase === 'spec'" class="spec">
            <header class="spec__head">
                <h1 class="spec__title">Was soll es sein?</h1>
                <p class="spec__lead">
                    Ein Satz genügt. {{ kitchenName }} entwirft daraus ein Rezept mit Zutaten und Schritten —
                    du liest es, änderst, was nicht passt, und speicherst erst dann.
                </p>
            </header>

            <v-textarea v-model="idea" class="spec__idea" variant="outlined" rows="3" auto-grow hide-details
                        autofocus placeholder="Zum Beispiel: Kartoffelsuppe mit Würstchen, oder etwas Leichtes mit Zucchini"
                        @keydown.ctrl.enter.prevent="design" @keydown.meta.enter.prevent="design"></v-textarea>

            <div class="spec__examples">
                <button v-for="example in examples" :key="example" type="button" class="example"
                        @click="idea = example">{{ example }}</button>
            </div>

            <div class="spec__knobs">
                <div class="knob">
                    <span class="knob__label">Portionen</span>
                    <v-btn-toggle v-model="servings" density="comfortable" variant="outlined" divided mandatory>
                        <v-btn :value="2">2</v-btn>
                        <v-btn :value="4">4</v-btn>
                        <v-btn :value="6">6</v-btn>
                    </v-btn-toggle>
                </div>
                <div class="knob">
                    <span class="knob__label">Zeit</span>
                    <v-btn-toggle v-model="maxMinutes" density="comfortable" variant="outlined" divided mandatory>
                        <v-btn :value="20">20 min</v-btn>
                        <v-btn :value="30">30 min</v-btn>
                        <v-btn :value="45">45 min</v-btn>
                        <v-btn :value="0">egal</v-btn>
                    </v-btn-toggle>
                </div>
                <div class="knob">
                    <span class="knob__label">Ernährung</span>
                    <v-btn-toggle v-model="diet" density="comfortable" variant="outlined" divided mandatory>
                        <v-btn value="">egal</v-btn>
                        <v-btn value="vegetarisch">vegetarisch</v-btn>
                        <v-btn value="vegan">vegan</v-btn>
                    </v-btn-toggle>
                </div>
            </div>

            <div class="spec__lists">
                <div class="knob">
                    <span class="knob__label">Was ist da?</span>
                    <v-combobox v-model="pantry" placeholder="Kürbis, Zwiebel, Reis" multiple chips
                                closable-chips variant="outlined" density="comfortable" hide-details></v-combobox>
                </div>
                <div class="knob">
                    <span class="knob__label">Was soll nicht rein?</span>
                    <v-combobox v-model="avoid" placeholder="Sahne, Pilze" multiple chips
                                closable-chips variant="outlined" density="comfortable" hide-details></v-combobox>
                </div>
            </div>

            <div class="spec__go">
                <v-btn color="primary" size="large" :loading="loading" :disabled="!canDesign" @click="design">
                    Entwerfen
                </v-btn>
                <v-model-select v-if="provider" class="spec__provider" model="AiProvider" hide-details
                                v-model="selectedAiProvider"></v-model-select>
                <span v-else class="spec__hint">
                    Kein KI-Anbieter eingerichtet —
                    <router-link :to="{name: 'ModelListPage', params: {model: 'AiProvider'}}">einen hinzufügen</router-link>.
                </span>
            </div>
            <p class="spec__note">Gespeichert wird nichts, bis du es sagst.</p>

            <!-- the brief the draft is ordered with, editable per space -->
            <div class="prompt">
                <button type="button" class="prompt__toggle" @click="togglePrompt">
                    <span class="prompt__label">
                        Prompt
                        <span class="prompt__state">{{ promptIsCustom ? 'eigener' : 'eingebaut' }}</span>
                    </span>
                    <span class="prompt__chevron" :class="{ 'prompt__chevron--open': promptOpen }">&#8964;</span>
                </button>
                <div class="prompt__body" v-if="promptOpen">
                    <p class="prompt__hint">
                        Damit wird der Entwurf bestellt. Antwortformat, Regeln und die Wortlisten
                        der Sammlung kommen immer dahinter — dieser Text sagt, wie gekocht und
                        geschrieben wird, und gilt für alle Wünsche in {{ kitchenName }}.
                    </p>
                    <v-textarea v-model="promptText" class="prompt__field" variant="outlined" rows="12"
                                auto-grow hide-details spellcheck="false"></v-textarea>
                    <div class="prompt__actions">
                        <v-btn size="small" color="primary" :loading="promptSaving" @click="savePrompt">
                            Prompt speichern
                        </v-btn>
                        <v-btn size="small" variant="text" :disabled="!promptIsCustom" @click="resetPrompt">
                            Eingebauten wiederherstellen
                        </v-btn>
                    </div>
                </div>
            </div>

            <v-alert v-if="error" type="error" variant="tonal" class="mt-6" :text="error"></v-alert>
        </section>

        <!-- 2 — der Entwurf: read it like a recipe, then change what does not fit -->
        <section v-else-if="phase === 'draft' && draft" class="draft">
            <header class="draft__head">
                <div class="draft__art">
                    <recipe-image :recipe="draft" height="100%" width="100%"></recipe-image>
                </div>
                <div class="draft__text">
                    <div class="draft__eyebrow">
                        Entwurf — nicht gespeichert
                    </div>
                    <h1 class="draft__title" v-if="!editing">{{ draft.name }}</h1>
                    <v-text-field v-else v-model="draft.name" class="draft__name" variant="outlined"
                                  density="comfortable" hide-details label="Name"></v-text-field>
                    <p class="draft__desc" v-if="!editing && draft.description">{{ draft.description }}</p>
                    <v-textarea v-if="editing" v-model="draft.description" class="draft__description" variant="outlined"
                                density="comfortable" rows="2" auto-grow hide-details
                                label="Beschreibung"></v-textarea>
                    <ul class="draft__meta" v-if="!editing">
                        <li v-if="draft.servings">{{ draft.servings }} Portionen</li>
                        <li v-if="draft.workingTime">{{ draft.workingTime }} min Arbeit</li>
                        <li v-if="draft.waitingTime">{{ draft.waitingTime }} min warten</li>
                        <li v-if="totalMinutes">{{ totalMinutes }} min gesamt</li>
                    </ul>
                    <div class="draft__numbers" v-else>
                        <v-number-input v-model="draft.servings" :precision="0" :min="1" control-variant="stacked"
                                        variant="outlined" density="compact" hide-details label="Portionen"></v-number-input>
                        <v-number-input v-model="draft.workingTime" :precision="0" :min="0" control-variant="stacked"
                                        variant="outlined" density="compact" hide-details label="Arbeit (min)"></v-number-input>
                        <v-number-input v-model="draft.waitingTime" :precision="0" :min="0" control-variant="stacked"
                                        variant="outlined" density="compact" hide-details label="Warten (min)"></v-number-input>
                    </div>
                </div>
            </header>

            <div class="draft__cols">
                <section class="draft__col">
                    <h2 class="draft__h2">Zutaten</h2>
                    <ul class="zutaten" :class="{ 'zutaten--editing': editing }">
                        <template v-for="(row, index) in ingredients" :key="index">
                            <li v-if="row.header" class="zutaten__group">{{ row.header }}</li>
                            <li v-else class="zutaten__row">
                                <span class="zutaten__amount">
                                    <template v-if="editing">
                                        <input v-model.number="row.source.amount" class="zutaten__input zutaten__input--amount"
                                               type="number" step="0.25" min="0" aria-label="Menge">
                                        <select class="zutaten__unit" :value="row.source.unit?.name ?? ''"
                                                aria-label="Einheit" @change="setUnit(row.source, $event)">
                                            <option value="">—</option>
                                            <option v-for="unit in unitOptions" :key="unit.id" :value="unit.name">
                                                {{ unit.name }}
                                            </option>
                                        </select>
                                    </template>
                                    <template v-else>{{ row.amount }}</template>
                                </span>
                                <span class="zutaten__food">
                                    <input v-if="editing" class="zutaten__input" :value="row.food"
                                           aria-label="Zutat" @input="renameFood(row.source, $event)">
                                    <template v-else>{{ row.food }}</template>
                                </span>
                                <span class="zutaten__note" v-if="row.note">{{ row.note }}</span>
                            </li>
                        </template>
                    </ul>
                    <p class="draft__warn" v-if="unknownFoods.length">
                        Kennt die Sammlung noch nicht und legt sie beim Speichern an:
                        {{ unknownFoods.map(f => f.name).join(', ') }}
                    </p>
                </section>

                <section class="draft__col draft__col--wide">
                    <h2 class="draft__h2">
                        Zubereitung
                        <span class="draft__h2count">{{ draft.steps?.length }} Schritte</span>
                    </h2>
                    <ol class="steps">
                        <li v-for="(step, index) in draft.steps" :key="index" class="steps__row">
                            <span class="steps__n">{{ index + 1 }}</span>
                            <div class="steps__body">
                                <p class="steps__name" v-if="!editing && step.name">{{ step.name }}</p>
                                <v-text-field v-else-if="editing" v-model="step.name" class="steps__title"
                                              variant="outlined" density="compact" hide-details
                                              aria-label="Titel des Schritts"></v-text-field>
                                <p class="steps__text" v-if="!editing">{{ readable(step) }}</p>
                                <v-textarea v-else class="steps__edit" variant="outlined" density="compact" rows="2"
                                            auto-grow hide-details :model-value="readable(step)"
                                            @update:model-value="value => step.instruction = value"></v-textarea>
                            </div>
                        </li>
                    </ol>
                </section>
            </div>

            <section class="draft__tags" v-if="draft.keywords && draft.keywords.length">
                <h2 class="draft__h2">Merkmale</h2>
                <div class="tags">
                    <span v-for="(keyword, index) in draft.keywords" :key="keyword.id ?? keyword.name" class="tags__chip">
                        {{ keyword.name }}
                        <button v-if="editing" type="button" class="tags__x" aria-label="Merkmal entfernen"
                                @click="draft.keywords.splice(index, 1)">✕</button>
                    </span>
                </div>
                <p class="draft__warn" v-if="rejectedTags.length">
                    Nicht übernommen, weil nicht in der Merkmalsliste: {{ rejectedLabel }}
                </p>
                <p class="draft__warn" v-if="warnings.length">
                    {{ warnings.join(' · ') }}
                </p>
            </section>

            <footer class="draft__actions">
                <v-btn color="primary" size="large" :loading="saving" @click="save">Speichern</v-btn>
                <v-btn variant="tonal" size="large" :prepend-icon="editing ? '$check' : 'fa-solid fa-pen'"
                       @click="editing = !editing">{{ editing ? 'Fertig' : 'Bearbeiten' }}</v-btn>
                <v-btn variant="text" size="large" prepend-icon="fa-solid fa-rotate" @click="again = !again">
                    Anders entwerfen
                </v-btn>
                <span class="draft__note">Gespeichert wird nichts, bis du es sagst.</span>
            </footer>

            <div class="draft__again" v-if="again">
                <v-text-field v-model="feedback" variant="outlined" density="comfortable" hide-details
                              label="Was soll anders sein?" placeholder="ohne Käse, dafür mit Spinat"
                              @keydown.enter.prevent="designAgain"></v-text-field>
                <v-btn color="primary" variant="tonal" :loading="loading" :disabled="!feedback.trim()"
                       @click="designAgain">Neu entwerfen</v-btn>
            </div>

            <v-alert v-if="error" type="error" variant="tonal" class="mt-4" :text="error"></v-alert>
        </section>

    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref, watch} from 'vue'
import {useRouter} from 'vue-router'
import {ApiApi, Ingredient, Recipe, RecipeFromSourceResponse, Unit} from '@/openapi'
import {useFileApi} from '@/composables/useFileApi'
import {useUserPreferenceStore} from '@/stores/UserPreferenceStore'
import {ErrorMessageType, MessageType, PreparedMessage, useMessageStore} from '@/stores/MessageStore'
import {useDjangoUrls} from '@/composables/useDjangoUrls'

interface UnknownFood {
    name: string
    folded: string
}

type WishResponse = RecipeFromSourceResponse & {
    unknownFoods?: UnknownFood[]
    rejectedTags?: string[]
    warnings?: string[]
}

const router = useRouter()
const {getDjangoUrl} = useDjangoUrls()
const api = new ApiApi()
const {doAiImportFromSource} = useFileApi()
const userPreferenceStore = useUserPreferenceStore()

const phase = ref<'spec' | 'draft'>('spec')
const editing = ref(false)
const idea = ref('')
const feedback = ref('')
const again = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')

const servings = ref(4)
const maxMinutes = ref(45)
const diet = ref('')
const pantry = ref<string[]>([])
const avoid = ref<string[]>([])

const selectedAiProvider = ref(userPreferenceStore.activeSpace.aiDefaultProvider)
const provider = computed(() => selectedAiProvider.value)

const draft = ref<Recipe | null>(null)
const unknownFoods = ref<UnknownFood[]>([])
const rejectedTags = ref<string[]>([])
const warnings = ref<string[]>([])

/**
 * The units the collection knows. The kitchen's units are a closed list in
 * Tandoor, so the one word in a line that cannot be retyped gets a select:
 * a draft that says "Gramm" where it should say "Stück" is otherwise only
 * fixable in the full editor.
 */
const units = ref<Unit[]>([])

const unitOptions = computed(() => [...units.value]
    .filter(unit => !!unit.name)
    .sort((a, b) => a.name.localeCompare(b.name, 'de')))

function loadUnits() {
    if (units.value.length) {
        return
    }
    api.apiUnitList({pageSize: 500})
        .then(page => {
            units.value = page.results ?? []
        })
        .catch(() => {
            // no list, no select: the draft is still readable and saveable
        })
}

watch(editing, value => {
    if (value) {
        loadUnits()
    }
})

const examples = [
    'Etwas mit Kürbis, vier Portionen, in 45 Minuten',
    'Ein Sonntagsbraten für sechs, aber ohne Ofen',
    'Carbonara, vegetarisch',
]

/**
 * The space is called whatever the household called it: Atlas here, FranDan in
 * the second kitchen. The name is data, so the sentence reads it instead of
 * asserting one -- a page that says "Atlas" to a guest account is a lie.
 */
const kitchenName = computed(() => userPreferenceStore.activeSpace.name || 'Die Küche')

/**
 * The brief the wish is designed with, kept on the server per space. The page
 * shows the text that is in use -- the built-in one until someone edits it --
 * so an edit starts from the real thing instead of from a copy that drifts
 * away from it. Empty on the server means "built-in", which is why resetting
 * is a save of '' and not a second field.
 */
const promptOpen = ref(false)
const promptText = ref('')
const promptSaved = ref('')
const promptDefault = ref('')
const promptSaving = ref(false)

const promptIsCustom = computed(() => !!promptSaved.value.trim())

function settingsUrl() {
    return getDjangoUrl('api/plugins/ai-import/settings/')
}

function csrfToken() {
    const match = document.cookie.match(/(^| )csrftoken=([^;]+)/)
    return match ? decodeURIComponent(match[2]) : ''
}

function loadPrompt() {
    fetch(settingsUrl(), {headers: {Accept: 'application/json'}})
        .then(response => response.ok ? response.json() : null)
        .then(data => {
            if (!data) {
                return
            }
            promptSaved.value = data.wish_prompt ?? ''
            promptDefault.value = data.wish_prompt_default ?? ''
            promptText.value = promptSaved.value.trim() || promptDefault.value
        })
        .catch(() => undefined)
}

function togglePrompt() {
    promptOpen.value = !promptOpen.value
    if (promptOpen.value) {
        promptText.value = promptSaved.value.trim() || promptDefault.value
    }
}

function writePrompt(value: string, done?: () => void) {
    promptSaving.value = true
    fetch(settingsUrl(), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
        body: JSON.stringify({wish_prompt: value}),
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`)
            }
            return response.json()
        })
        .then(data => {
            promptSaved.value = data.wish_prompt ?? ''
            promptDefault.value = data.wish_prompt_default ?? promptDefault.value
            useMessageStore().addMessage(MessageType.SUCCESS,
                promptSaved.value ? 'Prompt gespeichert.' : 'Der eingebaute Prompt gilt wieder.')
            done?.()
        })
        .catch(() => useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, null))
        .finally(() => promptSaving.value = false)
}

function savePrompt() {
    writePrompt(promptText.value)
}

function resetPrompt() {
    writePrompt('', () => {
        promptText.value = promptDefault.value
    })
}

onMounted(loadPrompt)

const canDesign = computed(() => !!provider.value && idea.value.trim().length > 0 && !loading.value)

const totalMinutes = computed(() => {
    const working = draft.value?.workingTime ?? 0
    const waiting = draft.value?.waitingTime ?? 0
    return working + waiting || null
})

/**
 * The model paraphrases the tag list ("Rezeptkategorie::Suppe" for
 * "Rezepttyp::Suppen"), and the plugin refuses anything it cannot resolve.
 * The reason matters; five refused spellings do not, so three are named.
 */
const rejectedLabel = computed(() => {
    const names = rejectedTags.value.slice(0, 3)
    const rest = rejectedTags.value.length - names.length
    return names.join(', ') + (rest > 0 ? ` und ${rest} weitere` : '')
})

/**
 * The draft carries template placeholders for Tandoor's own renderer, which
 * turns them into amount, unit and food. A preview that shows "{{ ingredients[1] }}"
 * answers "what will this look like" with "no idea", so they are resolved here
 * the same way the recipe page will.
 */
function readable(step: any): string {
    const ingredients = step.ingredients || []
    return (step.instruction || '').replace(/\{\{\s*ingredients\[(\d+)\]\s*\}\}/g,
        (_match: string, index: string) => {
            const ingredient = ingredients[Number(index)]
            if (!ingredient) {
                return ''
            }
            return [amountLabel(ingredient), ingredient.food?.name]
                .filter((part: string) => !!part)
                .join(' ')
        })
}

/**
 * The step field shows the sentence, not the template. Typing replaces the
 * placeholders of that one step with the amounts they stand for -- a field that
 * offers "{{ ingredients[1] }}" to type over is not an editor, and the steps
 * nobody touches keep their placeholders and stay scalable.
 */

interface IngredientRow {
    header?: string
    amount: string
    food: string
    note: string
    source: Ingredient
}

const ingredients = computed<IngredientRow[]>(() => {
    const rows: IngredientRow[] = []
    for (const step of draft.value?.steps ?? []) {
        for (const ingredient of step.ingredients ?? []) {
            if (ingredient.isHeader) {
                rows.push({
                    header: ingredient.food?.name ?? ingredient.originalText ?? '',
                    amount: '', food: '', note: '', source: ingredient,
                })
                continue
            }
            rows.push({
                amount: amountLabel(ingredient),
                food: ingredient.food?.name ?? '',
                note: ingredient.note ?? '',
                source: ingredient,
            })
        }
    }
    return rows
})

/**
 * Amounts in the household's own notation: a German comma, no trailing zeros.
 */
function amountLabel(ingredient: Ingredient): string {
    const parts: string[] = []
    if (!ingredient.noAmount && ingredient.amount) {
        const amount = Number(ingredient.amount)
        parts.push(Number.isInteger(amount) ? String(amount) : String(Math.round(amount * 100) / 100).replace('.', ','))
    }
    if (ingredient.unit?.name) {
        parts.push(ingredient.unit.name)
    }
    return parts.join(' ')
}

/**
 * A renamed food drops its id, so Tandoor matches or creates it by name instead
 * of renaming a food the rest of the library shares.
 */
function renameFood(ingredient: any, event: Event) {
    const name = (event.target as HTMLInputElement).value.trim()
    ingredient.food = name ? {name} : null
}

/** A unit is picked from the list, never typed: the recipe endpoint needs an id. */
function setUnit(ingredient: any, event: Event) {
    const name = (event.target as HTMLSelectElement).value
    const unit = units.value.find(candidate => candidate.name === name)
    ingredient.unit = unit ? {id: unit.id, name: unit.name} : null
}

/**
 * The wish as prompt text plus the constraints as fields.
 *
 * The constraints are sent separately instead of being written into the sentence
 * so that the plugin can mark them binding: "vier Portionen" in free text is a
 * suggestion, a servings field of 4 is not.
 */
function wishPayload(): Record<string, unknown> {
    const wish: Record<string, unknown> = {}
    if (servings.value) {
        wish.servings = servings.value
    }
    if (maxMinutes.value) {
        wish.max_minutes = maxMinutes.value
    }
    if (diet.value) {
        wish.diet = diet.value
    }
    if (pantry.value.length) {
        wish.pantry = pantry.value
    }
    if (avoid.value.length) {
        wish.avoid = avoid.value
    }
    return wish
}

/**
 * The sentence to design from, with the correction if this is a second attempt.
 */
function requestText(): string {
    const lines = [idea.value.trim()]
    if (feedback.value.trim()) {
        lines.push('', 'Bitte anders: ' + feedback.value.trim())
    }
    if (feedback.value.trim() && draft.value?.name) {
        lines.push('', `Der letzte Entwurf hieß „${draft.value.name}" — nicht wiederholen.`)
    }
    return lines.join('\n')
}

function messageOf(msg: unknown): string {
    if (!msg) {
        return 'Die Anfrage ist fehlgeschlagen.'
    }
    return typeof msg === 'string' ? msg : JSON.stringify(msg)
}

function design() {
    if (!provider.value || !idea.value.trim()) {
        return
    }
    error.value = ''
    loading.value = true
    doAiImportFromSource(provider.value.id as number, '', requestText(), wishPayload())
        .then((response: WishResponse) => {
            if (response.error) {
                error.value = messageOf(response.msg)
                return
            }
            if (!response.recipe) {
                error.value = 'Die KI hat kein Rezept geliefert.'
                return
            }
            draft.value = response.recipe as unknown as Recipe
            unknownFoods.value = response.unknownFoods ?? []
            rejectedTags.value = response.rejectedTags ?? []
            warnings.value = response.warnings ?? []
            feedback.value = ''
            again.value = false
            editing.value = false
            phase.value = 'draft'
        })
        .catch(() => {
            error.value = 'Die Anfrage ist fehlgeschlagen. Nochmal versuchen?'
        })
        .finally(() => {
            loading.value = false
        })
}

function designAgain() {
    if (!feedback.value.trim()) {
        return
    }
    design()
}

/**
 * One click from the draft into the collection: the draft already has the shape
 * the recipe endpoint takes, so nothing is re-shaped here.
 */
function save() {
    if (!draft.value) {
        return
    }
    saving.value = true
    api.apiRecipeCreate({recipe: draft.value})
        .then(recipe => {
            useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
            router.push({name: 'RecipeViewPage', params: {id: recipe.id}})
        })
        .catch(err => {
            useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
        })
        .finally(() => {
            saving.value = false
        })
}
</script>

<style scoped>
.wish {
    max-width: 940px;
    padding-bottom: 5rem;
}

/* — the wish — */
.spec {
    max-width: 720px;
    margin: 2.5rem auto 0;
}

.spec__title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2rem, 5vw, 2.8rem);
    font-weight: 600;
    line-height: 1.05;
    letter-spacing: -.01em;
}

.spec__lead {
    margin-top: .6rem;
    max-width: 52ch;
    font-size: .98rem;
    line-height: 1.6;
    color: rgba(var(--v-theme-on-surface), .66);
}

.spec__idea {
    margin-top: 1.75rem;
}

.spec__idea :deep(.v-field) {
    border-radius: 14px;
}

.spec__idea :deep(textarea) {
    font-size: 1.05rem;
    line-height: 1.6;
}

.spec__examples {
    display: flex;
    flex-wrap: wrap;
    gap: .4rem;
    margin-top: .75rem;
}

.example {
    padding: .3rem .7rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .16);
    border-radius: 999px;
    background: transparent;
    font-size: .82rem;
    line-height: 1.3;
    color: rgba(var(--v-theme-on-surface), .7);
    transition: border-color .15s, color .15s;
}

.example:hover {
    border-color: rgb(var(--v-theme-primary));
    color: rgb(var(--v-theme-primary));
}

.spec__knobs {
    display: flex;
    flex-wrap: wrap;
    gap: 1.25rem 1.75rem;
    margin-top: 1.75rem;
}

.knob {
    display: flex;
    flex-direction: column;
    gap: .4rem;
}

.knob__label {
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .5);
}

.spec__lists {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-top: 1.5rem;
}

.spec__go {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
    margin-top: 1.75rem;
}

.spec__provider {
    max-width: 220px;
}

.spec__hint {
    font-size: .85rem;
    color: rgba(var(--v-theme-on-surface), .6);
}

.spec__hint a {
    color: rgb(var(--v-theme-primary));
}

/* — the prompt, folded away — */
.prompt {
    margin-top: 2rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .16);
}

.prompt__toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: .85rem 0;
    border: 0;
    background: transparent;
    font: inherit;
    color: rgba(var(--v-theme-on-surface), .7);
    cursor: pointer;
    transition: color .15s ease;
}

.prompt__toggle:hover,
.prompt__toggle:focus-visible {
    color: rgba(var(--v-theme-on-surface), .95);
}

.prompt__label {
    display: flex;
    align-items: center;
    gap: .5rem;
    font-size: .74rem;
    letter-spacing: .1em;
    text-transform: uppercase;
}

.prompt__state {
    padding: .1rem .45rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .18);
    border-radius: 999px;
    font-size: .66rem;
    letter-spacing: .04em;
    text-transform: none;
    color: rgba(var(--v-theme-on-surface), .68);
}

.prompt__chevron {
    font-size: 1rem;
    line-height: 1;
    transition: transform .18s ease;
}

.prompt__chevron--open {
    transform: rotate(180deg);
}

.prompt__body {
    padding-bottom: .5rem;
}

.prompt__hint {
    margin-bottom: .75rem;
    max-width: 62ch;
    font-size: .82rem;
    line-height: 1.5;
    color: rgba(var(--v-theme-on-surface), .55);
}

.prompt__field :deep(textarea) {
    font-family: ui-monospace, 'SF Mono', Menlo, monospace;
    font-size: .8rem;
    line-height: 1.55;
}

.prompt__actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .5rem 1rem;
    margin-top: .85rem;
}

.spec__note {
    margin-top: .6rem;
    font-size: .8rem;
    color: rgba(var(--v-theme-on-surface), .45);
}

/* — the draft — */
.draft__head {
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: 1.75rem;
    align-items: start;
    margin: 1.5rem 0 2rem;
}

.draft__art {
    aspect-ratio: 4 / 3;
    overflow: hidden;
    border-radius: 16px;
    background: rgba(var(--v-theme-on-surface), .05);
}

.draft__eyebrow {
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .45);
}

.draft__title {
    margin-top: .35rem;
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(1.8rem, 4vw, 2.5rem);
    font-weight: 600;
    line-height: 1.1;
}

.draft__name,
.draft__description {
    margin-top: .5rem;
}

.draft__desc {
    margin-top: .6rem;
    max-width: 58ch;
    font-size: .95rem;
    line-height: 1.6;
    color: rgba(var(--v-theme-on-surface), .68);
}

.draft__meta {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem .55rem;
    margin-top: .9rem;
    padding: 0;
    list-style: none;
    font-size: .82rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

.draft__meta li + li::before {
    content: '·';
    margin-right: .55rem;
    color: rgba(var(--v-theme-on-surface), .3);
}

.draft__numbers {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 150px));
    gap: .6rem;
    margin-top: .9rem;
}

.draft__cols {
    display: grid;
    grid-template-columns: .85fr 1.15fr;
    gap: 2.5rem;
}

.draft__h2 {
    margin-bottom: .85rem;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .5);
}

.zutaten {
    list-style: none;
    padding: 0;
}

.zutaten__group {
    margin: 1rem 0 .4rem;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: rgba(var(--v-theme-on-surface), .45);
}

.zutaten__group:first-child {
    margin-top: 0;
}

.zutaten__row {
    display: grid;
    /* one width for every row: each <li> is its own grid, so max-content would
       size the column per row and the food names would stagger */
    grid-template-columns: 8.5rem 1fr;
    column-gap: .9rem;
    padding: .3rem 0;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07);
    font-size: .92rem;
}

.zutaten__amount {
    display: flex;
    align-items: baseline;
    justify-content: flex-end;
    gap: .3rem;
    white-space: nowrap;
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: rgba(var(--v-theme-on-surface), .55);
}

.zutaten__food {
    font-weight: 500;
}

.zutaten__input {
    width: 100%;
    padding: .1rem .25rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .16);
    border-radius: 5px;
    background: rgba(var(--v-theme-surface), 1);
    font: inherit;
    color: inherit;
}

.zutaten__input--amount {
    width: 4.25rem;
    text-align: right;
}

/* the whole amount cell only widens while it holds two fields */
.zutaten--editing .zutaten__row {
    grid-template-columns: 11rem 1fr;
}

.zutaten--editing .zutaten__input--amount {
    flex: 0 0 3.75rem;
    width: 3.75rem;
}

.zutaten__unit {
    font-size: .82rem;
    color: rgba(var(--v-theme-on-surface), .55);
}

select.zutaten__unit {
    flex: 1 1 auto;
    min-width: 0;
    padding: .1rem .1rem .1rem .25rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .16);
    border-radius: 5px;
    background: rgba(var(--v-theme-surface), 1);
    font: inherit;
    font-size: .82rem;
    color: inherit;
    cursor: pointer;
}

select.zutaten__unit:focus {
    outline: 2px solid rgba(var(--v-theme-primary), .5);
}

.zutaten__input:focus {
    outline: 2px solid rgba(var(--v-theme-primary), .5);
    outline-offset: 0;
}

.zutaten__note {
    grid-column: 2;
    font-size: .82rem;
    font-style: italic;
    color: rgba(var(--v-theme-on-surface), .5);
}

.steps {
    list-style: none;
    padding: 0;
}

.steps__row {
    display: grid;
    grid-template-columns: 1.9rem 1fr;
    gap: .75rem;
    padding: .8rem 0;
}

.steps__row + .steps__row {
    border-top: 1px solid rgba(var(--v-theme-on-surface), .07);
}

.draft__h2count {
    margin-left: .5rem;
    font-size: .78rem;
    font-weight: 400;
    letter-spacing: .02em;
    color: rgba(var(--v-theme-on-surface), .45);
}

.steps__name {
    margin-bottom: .2rem;
    font-size: 1.02rem;
    font-weight: 700;
    line-height: 1.25;
    letter-spacing: -.005em;
}

.steps__title {
    margin-bottom: .4rem;
}

.steps__n {
    display: grid;
    place-items: center;
    width: 1.9rem;
    height: 1.9rem;
    border: 1px solid rgba(var(--v-theme-primary), .4);
    border-radius: 50%;
    background: rgba(var(--v-theme-primary), .1);
    color: rgba(var(--v-theme-on-surface), .85);
    font-size: .82rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.steps__text {
    font-size: .96rem;
    line-height: 1.6;
}

.steps__edit :deep(textarea) {
    font-size: .92rem;
    line-height: 1.55;
}

.draft__tags {
    margin-top: 2rem;
}

.tags {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem;
}

.tags__chip {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    padding: .2rem .6rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .14);
    border-radius: 999px;
    font-size: .78rem;
    color: rgba(var(--v-theme-on-surface), .68);
}

.tags__x {
    border: none;
    background: none;
    padding: 0;
    font-size: .7rem;
    line-height: 1;
    color: rgba(var(--v-theme-on-surface), .45);
}

.tags__x:hover {
    color: rgb(var(--v-theme-error));
}

.draft__warn {
    margin-top: .7rem;
    padding-left: .55rem;
    border-left: 2px solid rgba(var(--v-theme-warning), .55);
    font-size: .82rem;
    line-height: 1.5;
    color: rgba(var(--v-theme-on-surface), .62);
}

.draft__actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .75rem;
    margin-top: 2.25rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .1);
}

.draft__note {
    font-size: .8rem;
    color: rgba(var(--v-theme-on-surface), .45);
}

.draft__again {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .75rem;
    margin-top: 1.25rem;
}

@media (max-width: 900px) {
    .draft__head {
        grid-template-columns: 1fr;
    }

    .draft__art {
        aspect-ratio: 16 / 9;
    }

    .draft__cols {
        grid-template-columns: 1fr;
        gap: 1.75rem;
    }
}

@media (max-width: 640px) {
    .spec__lists {
        grid-template-columns: 1fr;
    }

    .zutaten__row {
        column-gap: .6rem;
    }

    .draft__numbers {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .zutaten__row {
        grid-template-columns: 6.5rem 1fr;
    }

    .zutaten--editing .zutaten__row {
        grid-template-columns: 9.5rem 1fr;
    }
}
</style>
