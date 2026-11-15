<template>
    <v-form>
        <p class="text-h6">{{ $t('AiImport') }}</p>
        <v-divider class="mb-3"></v-divider>

        <v-alert v-if="loaded && !stored" type="info" variant="tonal" class="mb-4">
            {{ $t('AiImportDefaultsNotice') }}
        </v-alert>

        <v-switch v-model="form.placeholders_enabled" color="primary" inset hide-details="auto"
                  :label="$t('AiImportPlaceholders')" class="mb-4"></v-switch>
        <v-switch v-model="form.images_enabled" color="primary" inset hide-details="auto"
                  :label="$t('AiImportImages')" class="mb-4"></v-switch>
        <v-switch v-model="form.enforce_step_titles" color="primary" inset hide-details="auto"
                  :label="$t('AiImportStepTitles')" class="mb-4"></v-switch>

        <p class="text-subtitle-1 mt-6">{{ $t('AiImportPrompt') }}</p>
        <p class="text-body-2 text-medium-emphasis mb-2">{{ $t('AiImportPromptHelp') }}</p>
        <v-textarea v-model="form.custom_prompt" rows="4" counter="2000" maxlength="2000"
                    :label="$t('AiImportPromptLabel')"
                    :placeholder="$t('AiImportPromptPlaceholder')"></v-textarea>

        <v-row dense class="mt-2">
            <v-col cols="12" sm="7">
                <v-text-field v-model="testUrl" :label="$t('AiImportTestUrl')"
                              :hint="$t('AiImportTestUrlHint')" persistent-hint
                              prepend-inner-icon="$link"></v-text-field>
            </v-col>
            <v-col cols="12" sm="5">
                <v-select v-model="providerId" :items="providers" item-title="name" item-value="id"
                          :label="$t('AiProvider')"></v-select>
            </v-col>
        </v-row>

        <v-btn class="mt-6" variant="tonal" prepend-icon="$search" :loading="testing"
               :disabled="!testUrl || !providerId" @click="preview()">
            {{ $t('AiImportTest') }}
        </v-btn>

        <v-card v-if="previewResult" class="mt-4" variant="outlined">
            <v-card-title class="text-subtitle-1">{{ previewResult.name }}</v-card-title>
            <v-card-subtitle>
                {{ previewResult.steps.length }} {{ $t('Steps') }}
                <span v-if="unknownFoods > 0" class="text-warning ml-3">
                    {{ unknownFoods }} {{ $t('AiImportUnknownFoods') }}
                </span>
            </v-card-subtitle>
            <v-card-text>
                <div v-for="(step, index) in previewResult.steps" :key="index" class="mb-4">
                    <p class="text-subtitle-2">{{ index + 1 }}. {{ step.name }}</p>
                    <p class="text-body-2" style="white-space: pre-wrap">{{ readable(step) }}</p>
                    <p v-if="step.placeholder_state && step.placeholder_state !== 'all'"
                       class="text-caption text-warning mt-1">
                        <v-icon size="small" icon="fa-solid fa-circle-info" class="mr-1"></v-icon>
                        {{ $t(step.placeholder_state === 'partial'
                            ? 'AiImportStatePartial' : 'AiImportStateNone') }}
                    </p>
                </div>
            </v-card-text>
        </v-card>

        <v-expansion-panels class="mt-4" variant="accordion">
            <v-expansion-panel :title="$t('AiImportExplain')">
                <v-expansion-panel-text>
                    <ul class="ml-6">
                        <li>{{ $t('AiImportExplainPlaceholders') }}</li>
                        <li>{{ $t('AiImportExplainImages') }}</li>
                        <li>{{ $t('AiImportExplainStepTitles') }}</li>
                    </ul>
                </v-expansion-panel-text>
            </v-expansion-panel>
        </v-expansion-panels>

        <v-btn class="mt-3" color="success" prepend-icon="$save" :loading="saving" @click="save()">
            {{ $t('Save') }}
        </v-btn>
    </v-form>
</template>

<script setup lang="ts">

import {computed, onMounted, ref} from "vue";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";
import {ErrorMessageType, MessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";

const {getDjangoUrl} = useDjangoUrls()
const saving = ref(false)
const testing = ref(false)
const stored = ref(false)
const loaded = ref(false)

const testUrl = ref('')
const providerId = ref<number | null>(null)
const previewResult = ref<any>(null)
const unknownFoods = ref(0)

const form = ref({
    placeholders_enabled: true,
    images_enabled: true,
    enforce_step_titles: true,
    custom_prompt: '',
})

const providers = computed(() => {
    const list = (useUserPreferenceStore() as any).aiProviders
    return Array.isArray(list) ? list : []
})

function endpoint(path: string) {
    return getDjangoUrl(`api/plugins/ai-import/${path}/`)
}

function getCookie(name: string) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
    return match ? decodeURIComponent(match[2]) : ''
}

function apply(data: any) {
    form.value.placeholders_enabled = data.placeholders_enabled
    form.value.images_enabled = data.images_enabled
    form.value.enforce_step_titles = data.enforce_step_titles
    form.value.custom_prompt = data.custom_prompt
    stored.value = data.stored
}

/**
 * The preview returns template placeholders; render them the way Tandoor will
 * -- amount, unit and food -- instead of showing the syntax. A preview that
 * writes "[Zutat]" answers "does this prompt work" with "no idea".
 */
function readable(step: any) {
    const ingredients = step.ingredients || []
    return (step.instruction || '').replace(
        /\{\{\s*ingredients\[(\d+)\]\s*\}\}/g,
        (_match: string, index: string) => {
            const ingredient = ingredients[Number(index)]
            if (!ingredient) return ''
            return [ingredient.amount, ingredient.unit?.name, ingredient.food?.name]
                .filter((part: any) => part !== null && part !== undefined && part !== '')
                .join(' ')
        },
    )
}

/**
 * Why a step shows no amount. The plugin refuses a placeholder when the
 * ingredients are named out of order, because a positional reference would then
 * point at the wrong jar. That refusal is a fact about the sentence, so it is
 * said in the reading order of the sentence.
 */

function load() {
    fetch(endpoint('settings'), {headers: {'Accept': 'application/json'}})
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.json()
        })
        .then(apply)
        .catch(err => useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err))
        .finally(() => loaded.value = true)
}

function loadProviders() {
    fetch(getDjangoUrl('api/ai-provider/'), {headers: {'Accept': 'application/json'}})
        .then(r => r.ok ? r.json() : {results: []})
        .then(data => {
            const list = data.results || data
            ;(useUserPreferenceStore() as any).aiProviders = list
            if (list.length && !providerId.value) providerId.value = list[0].id
        })
        .catch(() => undefined)
}

function save() {
    saving.value = true
    fetch(endpoint('settings'), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
        body: JSON.stringify(form.value),
    })
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.json()
        })
        .then(data => {
            apply(data)
            useMessageStore().addMessage(MessageType.SUCCESS, 'OK')
        })
        .catch(err => useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err))
        .finally(() => saving.value = false)
}

function preview() {
    testing.value = true
    previewResult.value = null
    fetch(endpoint('preview'), {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
        body: JSON.stringify({
            url: testUrl.value,
            ai_provider_id: providerId.value,
            custom_prompt: form.value.custom_prompt,
        }),
    })
        .then(r => r.json().then(body => {
            if (!r.ok) throw new Error(body.msg || `HTTP ${r.status}`)
            return body
        }))
        .then(body => {
            previewResult.value = body.recipe
            unknownFoods.value = body.counts?.unknown_foods || 0
        })
        .catch(err => useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err))
        .finally(() => testing.value = false)
}

onMounted(() => {
    load()
    loadProviders()
})

</script>
