<template>
    <div class="cook-log-quick">
        <div class="d-flex flex-wrap align-center ga-2">
            <v-btn size="small" color="create" prepend-icon="$create" @click="open">Gekocht</v-btn>
            <span v-if="latest" class="text-body-2 text-medium-emphasis">
                Zuletzt: {{ lastWhen }} · {{ latest.createdBy?.displayName }}
                <v-rating
                    v-if="latest.rating"
                    :model-value="latest.rating"
                    readonly
                    half-increments
                    size="x-small"
                    density="compact"
                    color="tandoor"
                    class="d-inline-flex align-center"
                ></v-rating>
                <span v-if="latest.comment">— „{{ latest.comment }}“</span>
            </span>
        </div>

        <v-dialog v-model="dialog" max-width="480">
            <v-card>
                <v-card-title>Gekocht</v-card-title>
                <v-card-text>
                    <v-label>Bewertung</v-label>
                    <div>
                        <v-rating v-model="form.rating" clearable hover density="compact"></v-rating>
                    </div>
                    <v-row dense class="mt-2">
                        <v-col cols="12" sm="6">
                            <v-date-input v-model="form.createdAt" label="Datum"></v-date-input>
                        </v-col>
                        <v-col cols="12" sm="6">
                            <v-number-input v-model="form.servings" label="Portionen" :precision="2"></v-number-input>
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
                    <v-btn @click="dialog = false">Abbrechen</v-btn>
                    <v-btn color="create" :loading="saving" @click="save">Speichern</v-btn>
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

/**
 * One tap to record that the dish was cooked, optionally with stars and a note.
 *
 * The cook log is the household's only rating store (see
 * docs/superpowers/specs/2026-11-22-recipe-ratings-design.md in the Atlas
 * repo): a rating without a date would not survive the first "when did we last
 * make this" question.
 */
const props = defineProps<{
    recipe: Recipe
    servings?: number
}>()

const api = new ApiApi()
const latest = ref<CookLog | null>(null)
const dialog = ref(false)
const saving = ref(false)
const form = ref<{
    rating?: number | null
    comment?: string | null
    createdAt?: Date
    servings?: number | null
}>({})

const lastWhen = computed(() => latest.value?.createdAt
    ? DateTime.fromJSDate(latest.value.createdAt).toLocaleString(DateTime.DATE_MED)
    : '')

function open() {
    form.value = {
        rating: null,
        comment: null,
        createdAt: new Date(),
        servings: props.servings ?? props.recipe.servings ?? 1,
    }
    dialog.value = true
}

function load() {
    api.apiCookLogList({recipe: props.recipe.id!, page: 1}).then(r => {
        const rows = r.results ?? []
        latest.value = rows.length
            ? rows.reduce((a, b) => ((a.createdAt ?? new Date(0)) > (b.createdAt ?? new Date(0)) ? a : b))
            : null
    }).catch(() => {
        // The line is decoration; a failure must not block the recipe page.
    })
}

function save() {
    saving.value = true
    api.apiCookLogCreate({
        cookLog: {
            recipe: props.recipe.id!,
            rating: form.value.rating ?? null,
            comment: form.value.comment || null,
            servings: form.value.servings ?? null,
            createdAt: form.value.createdAt ?? new Date(),
        },
    }).then(r => {
        latest.value = r
        dialog.value = false
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    }).finally(() => {
        saving.value = false
    })
}

onMounted(load)
</script>
