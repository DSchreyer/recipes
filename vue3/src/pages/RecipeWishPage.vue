<template>
    <v-container class="wish" fluid>

        <!-- 1 — der Wunsch: one sentence and four constraints -->
        <section v-if="phase === 'spec'" class="spec">
            <header class="spec__head">
                <h1 class="spec__title">Was soll es sein?</h1>
                <p class="spec__lead">
                    Ein Satz genügt. Atlas entwirft daraus ein Rezept mit Zutaten und Schritten —
                    du liest es, änderst, was nicht passt, und speicherst erst dann.
                </p>
            </header>

            <v-textarea v-model="idea" class="spec__idea" variant="outlined" rows="3" auto-grow hide-details
                        autofocus placeholder="Etwas mit Kürbis, vier Portionen, in 45 Minuten"
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
                <v-combobox v-model="pantry" label="Vorhanden" placeholder="Kürbis, Zwiebel, Reis" multiple chips
                            closable-chips variant="outlined" density="comfortable" hide-details></v-combobox>
                <v-combobox v-model="avoid" label="Nicht verwenden" placeholder="Sahne, Pilze" multiple chips
                            closable-chips variant="outlined" density="comfortable" hide-details></v-combobox>
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

            <v-alert v-if="error" type="error" variant="tonal" class="mt-6" :text="error"></v-alert>
        </section>

        <!-- 2 — der Entwurf: read it like a recipe, then decide -->
        <section v-else-if="phase === 'preview' && draft" class="draft">
            <header class="draft__head">
                <div class="draft__art">
                    <recipe-image :recipe="draft" height="100%" width="100%"></recipe-image>
                </div>
                <div class="draft__text">
                    <div class="draft__eyebrow">Entwurf — nicht gespeichert</div>
                    <h1 class="draft__title">{{ draft.name }}</h1>
                    <p class="draft__desc" v-if="draft.description">{{ draft.description }}</p>
                    <ul class="draft__meta">
                        <li v-if="draft.servings">{{ draft.servings }} Portionen</li>
                        <li v-if="draft.workingTime">{{ draft.workingTime }} min Arbeit</li>
                        <li v-if="draft.waitingTime">{{ draft.waitingTime }} min warten</li>
                        <li v-if="totalMinutes">{{ totalMinutes }} min gesamt</li>
                    </ul>
                </div>
            </header>

            <div class="draft__cols">
                <section class="draft__col">
                    <h2 class="draft__h2">Zutaten</h2>
                    <ul class="zutaten">
                        <template v-for="(row, index) in ingredients" :key="index">
                            <li v-if="row.header" class="zutaten__group">{{ row.header }}</li>
                            <li v-else class="zutaten__row">
                                <span class="zutaten__amount">{{ row.amount }}</span>
                                <span class="zutaten__food">{{ row.food }}</span>
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
                    <h2 class="draft__h2">Zubereitung</h2>
                    <ol class="steps">
                        <li v-for="(step, index) in draft.steps" :key="index" class="steps__row">
                            <span class="steps__n">{{ index + 1 }}</span>
                            <div class="steps__body">
                                <p class="steps__text">{{ step.instruction }}</p>
                                <p class="steps__note" v-if="step.note">{{ step.note }}</p>
                            </div>
                        </li>
                    </ol>
                </section>
            </div>

            <section class="draft__tags" v-if="draft.keywords && draft.keywords.length">
                <h2 class="draft__h2">Merkmale</h2>
                <div class="tags">
                    <span v-for="keyword in draft.keywords" :key="keyword.id ?? keyword.name" class="tags__chip">
                        {{ keyword.name }}
                    </span>
                </div>
                <p class="draft__warn" v-if="rejectedTags.length">
                    Nicht übernommen, weil nicht in der Merkmalsliste: {{ rejectedTags.join(', ') }}
                </p>
                <p class="draft__warn" v-if="warnings.length">
                    {{ warnings.join(' · ') }}
                </p>
            </section>

            <footer class="draft__actions">
                <v-btn color="primary" size="large" :loading="saving" @click="save">Speichern</v-btn>
                <v-btn variant="tonal" size="large" prepend-icon="fa-solid fa-pen" @click="phase = 'edit'">Bearbeiten</v-btn>
                <v-btn variant="text" size="large" prepend-icon="fa-solid fa-rotate" @click="again = !again">
                    Anders entwerfen
                </v-btn>
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

        <!-- 3 — bearbeiten: Tandoor's own editor, so nothing is a second-class field -->
        <section v-else-if="phase === 'edit' && draft" class="edit">
            <div class="edit__bar">
                <v-btn variant="text" prepend-icon="fa-solid fa-arrow-left" @click="phase = 'preview'">
                    Zurück zur Vorschau
                </v-btn>
                <span class="edit__hint">Speichern legt das Rezept an. Bis dahin ist nichts in der Sammlung.</span>
            </div>
            <recipe-editor :item="draft" @create="onCreated" @save="onCreated"></recipe-editor>
        </section>

    </v-container>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import {useRouter} from 'vue-router'
import {ApiApi, Ingredient, Recipe, RecipeFromSourceResponse} from '@/openapi'
import RecipeEditor from '@/components/model_editors/RecipeEditor.vue'
import {useFileApi} from '@/composables/useFileApi'
import {useUserPreferenceStore} from '@/stores/UserPreferenceStore'
import {ErrorMessageType, PreparedMessage, useMessageStore} from '@/stores/MessageStore'

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
const api = new ApiApi()
const {doAiImportFromSource} = useFileApi()
const userPreferenceStore = useUserPreferenceStore()

const phase = ref<'spec' | 'preview' | 'edit'>('spec')
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

const examples = [
    'Etwas mit Kürbis, vier Portionen, in 45 Minuten',
    'Ein Sonntagsbraten für sechs, aber ohne Ofen',
    'Carbonara, vegetarisch',
]

const canDesign = computed(() => !!provider.value && idea.value.trim().length > 0 && !loading.value)

const totalMinutes = computed(() => {
    const working = draft.value?.workingTime ?? 0
    const waiting = draft.value?.waitingTime ?? 0
    return working + waiting || null
})

interface IngredientRow {
    header?: string
    amount: string
    food: string
    note: string
}

const ingredients = computed<IngredientRow[]>(() => {
    const rows: IngredientRow[] = []
    for (const step of draft.value?.steps ?? []) {
        for (const ingredient of step.ingredients ?? []) {
            if (ingredient.isHeader) {
                rows.push({header: ingredient.food?.name ?? ingredient.originalText ?? '', amount: '', food: '', note: ''})
                continue
            }
            rows.push({
                amount: amountLabel(ingredient),
                food: ingredient.food?.name ?? '',
                note: ingredient.note ?? '',
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
            phase.value = 'preview'
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
 * One click from the preview into the collection: the draft is already the
 * payload the recipe endpoint takes, so nothing has to be re-shaped here.
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

function onCreated(recipe: Recipe) {
    useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
    router.push({name: 'RecipeViewPage', params: {id: recipe.id}})
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
    grid-template-columns: 5.5rem 1fr;
    gap: .75rem;
    padding: .3rem 0;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07);
    font-size: .92rem;
}

.zutaten__amount {
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: rgba(var(--v-theme-on-surface), .55);
}

.zutaten__food {
    font-weight: 500;
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
    padding: .55rem 0;
}

.steps__row + .steps__row {
    border-top: 1px solid rgba(var(--v-theme-on-surface), .07);
}

.steps__n {
    display: grid;
    place-items: center;
    width: 1.9rem;
    height: 1.9rem;
    border-radius: 50%;
    background: rgba(var(--v-theme-primary), .12);
    color: rgb(var(--v-theme-primary));
    font-size: .82rem;
    font-weight: 700;
}

.steps__text {
    font-size: .96rem;
    line-height: 1.6;
}

.steps__note {
    margin-top: .3rem;
    font-size: .85rem;
    font-style: italic;
    color: rgba(var(--v-theme-on-surface), .55);
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
    padding: .2rem .6rem;
    border: 1px solid rgba(var(--v-theme-on-surface), .14);
    border-radius: 999px;
    font-size: .78rem;
    color: rgba(var(--v-theme-on-surface), .68);
}

.draft__warn {
    margin-top: .7rem;
    font-size: .82rem;
    line-height: 1.5;
    color: rgba(var(--v-theme-warning), 1);
}

.draft__actions {
    display: flex;
    flex-wrap: wrap;
    gap: .75rem;
    margin-top: 2.25rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .1);
}

.draft__again {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .75rem;
    margin-top: 1.25rem;
}

/* — the editor — */
.edit__bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
}

.edit__hint {
    font-size: .8rem;
    color: rgba(var(--v-theme-on-surface), .5);
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
        grid-template-columns: 4.5rem 1fr;
    }
}
</style>
