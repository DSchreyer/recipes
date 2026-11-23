<template>
    <div class="cook-log-quick">
        <div class="d-flex flex-wrap align-center ga-2">
            <v-btn size="small" variant="tonal" color="create" prepend-icon="$create" @click="open">
                Gekocht
            </v-btn>
            <rating-stars
                v-if="recipe.rating"
                :value="recipe.rating"
                size="md"
                chip
                title="Dein Schnitt über alle Male"
            ></rating-stars>
            <span v-if="cookCount" class="cook-count">{{ cookCount }}×</span>
        </div>
        <div v-if="latest" class="cook-log-quick__meta">
            Zuletzt {{ lastWhen }} · {{ latest.createdBy?.displayName }}
        </div>
        <div v-if="latest?.comment" class="cook-note">„{{ latest.comment }}“</div>

        <v-dialog v-model="dialog" max-width="520">
            <v-card>
                <v-card-title class="cook-dialog__title">
                    <span>Gekocht</span>
                    <span class="cook-dialog__recipe">{{ recipe.name }}</span>
                </v-card-title>
                <v-card-text>
                    <div class="cook-dialog__rating" :class="{'cook-dialog__rating--empty': !form.rating}">
                        <rating-stars
                            v-if="form.rating"
                            :value="form.rating"
                            size="lg"
                            :show-value="false"
                        ></rating-stars>
                        <span v-else class="cook-dialog__rating-empty">noch keine Bewertung</span>
                        <span v-if="form.rating" class="cook-dialog__rating-label">
                            {{ formRatingLabel }}<span class="cook-dialog__rating-of"> von 5</span>
                        </span>
                    </div>
                    <v-slider
                        v-model="form.rating"
                        :min="0"
                        :max="5"
                        :step="0.25"
                        color="star"
                        show-ticks="always"
                        tick-size="2"
                        hide-details="auto"
                        class="mb-3"
                        hint="Viertel-Schritte: 0,25 · 0,5 · 0,75"
                        persistent-hint
                    ></v-slider>
                    <v-row dense>
                        <v-col cols="12" sm="6">
                            <v-date-input v-model="form.createdAt" label="Datum" prepend-icon=""
                                          :display-format="germanDate"></v-date-input>
                        </v-col>
                        <v-col cols="12" sm="6">
                            <v-number-input v-model="form.servings" label="Portionen" :precision="0"></v-number-input>
                        </v-col>
                    </v-row>
                    <v-textarea
                        v-model="form.comment"
                        label="Notiz"
                        rows="2"
                        auto-grow
                        class="mt-2"
                        hint="Was beim nächsten Mal anders soll"
                        persistent-hint
                    ></v-textarea>
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="dialog = false">Abbrechen</v-btn>
                    <v-btn color="create" variant="flat" :loading="saving" @click="save">Speichern</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from 'vue'
import {ApiApi, CookLog, Recipe} from '@/openapi'
import {DateTime} from 'luxon'
import {ErrorMessageType, useMessageStore} from '@/stores/MessageStore.ts'
import {VDateInput} from 'vuetify/labs/VDateInput'
import RatingStars from '@/components/display/RatingStars.vue'

/**
 * One tap to record that the dish was cooked, optionally with stars and a note.
 *
 * The cook log is the household's only rating store (see
 * docs/superpowers/specs/2026-11-22-recipe-ratings-design.md in the Atlas
 * repo): a rating without a date would not survive the first "when did we last
 * make this" question.
 */
const emit = defineEmits<{saved: []}>()

const props = defineProps<{
    recipe: Recipe
    servings?: number
}>()

const api = new ApiApi()
const latest = ref<CookLog | null>(null)
const cookCount = ref(0)
const dialog = ref(false)
const saving = ref(false)
const form = ref<{
    rating?: number | null
    comment?: string | null
    createdAt?: Date
    servings?: number | null
}>({})

const lastWhen = computed(() => latest.value?.createdAt
    ? DateTime.fromJSDate(latest.value.createdAt).toFormat('dd.MM.yyyy')
    : '')

// Tandoor's Vuetify locale is English, so a native date field would read
// 11/23/2026. The household reads 23.11.2026, the same as the plugin pages.
function germanDate(date: Date): string {
    return date.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric'})
}

const formRatingLabel = computed(() => {
    const value = form.value.rating ?? 0
    if (!value) return ''
    return value.toFixed(2).replace(/\.?0+$/, '').replace('.', ',')
})

function open() {
    form.value = {
        // Start from the last verdict so a repeated cook is one tap away; the
        // note stays empty because a fresh note is what the next cook needs.
        rating: latest.value?.rating ? Number(latest.value.rating) : 0,
        comment: null,
        createdAt: new Date(),
        servings: props.servings ?? props.recipe.servings ?? 1,
    }
    dialog.value = true
}

function load() {
    api.apiCookLogList({recipe: props.recipe.id!, page: 1}).then(r => {
        const rows = r.results ?? []
        cookCount.value = rows.length
        latest.value = rows.length
            ? rows.reduce((a, b) => (a.createdAt ?? new Date(0)) > (b.createdAt ?? new Date(0)) ? a : b)
            : null
    }).catch(() => {
        // The line is decoration; a failure must not break the recipe page.
    })
}

function save() {
    saving.value = true
    api.apiCookLogCreate({
        cookLog: {
            recipe: props.recipe.id!,
            // Vuetify's clearable rating yields 0 when the thumb is at the
            // start; 0 is not a verdict and would drag the average down.
            rating: form.value.rating || null,
            comment: form.value.comment?.trim() || null,
            servings: form.value.servings ?? null,
            createdAt: form.value.createdAt,
        },
    }).then(r => {
        latest.value = r
        dialog.value = false
        emit('saved')
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    }).finally(() => {
        saving.value = false
    })
}

onMounted(load)
</script>

<style scoped>
.cook-log-quick__meta {
    margin-top: 0.5rem;
    font-size: 0.8rem;
    color: rgba(var(--v-theme-on-surface), 0.6);
}

.cook-count {
    font-size: 0.78rem;
    font-variant-numeric: tabular-nums;
    color: rgba(var(--v-theme-on-surface), 0.55);
}

.cook-note {
    margin-top: 0.4rem;
    padding: 0.05rem 0 0.05rem 0.55rem;
    border-left: 3px solid rgba(184, 121, 26, 0.45);
    color: #6f665b;
    font-size: 0.85rem;
    font-style: italic;
    line-height: 1.4;
}

.cook-dialog__title {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    padding-bottom: 0.25rem;
}

.cook-dialog__recipe {
    font-size: 0.82rem;
    font-weight: 400;
    color: rgba(var(--v-theme-on-surface), 0.6);
}

.cook-dialog__rating {
    display: flex;
    align-items: baseline;
    gap: 0.55rem;
    margin-bottom: 0.75rem;
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(var(--v-theme-star), 0.08);
    border: 1px solid rgba(var(--v-theme-star), 0.2);
}

.cook-dialog__rating--empty {
    background: rgba(var(--v-theme-on-surface), 0.04);
    border-color: rgba(var(--v-theme-on-surface), 0.12);
}

.cook-dialog__rating-label {
    font-size: 1.15rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: rgb(var(--v-theme-star));
    white-space: nowrap;
}

.cook-dialog__rating-of {
    font-size: 0.72em;
    font-weight: 500;
    color: rgba(var(--v-theme-on-surface), 0.55);
}

.cook-dialog__rating-empty {
    font-size: 0.9rem;
    color: rgba(var(--v-theme-on-surface), 0.55);
}
</style>
