<template>
    <v-container class="find" fluid>
        <header class="find__head">
            <div>
                <h1 class="find__title">Suchen</h1>
                <p class="find__sub">{{ resultLabel }}</p>
            </div>
            <div class="find__head-actions">
                <v-btn variant="text" prepend-icon="fa-solid fa-sliders"
                       @click="panel = panel === 'search' ? '' : 'search'">
                    Filter
                    <v-badge v-if="activeFilterCount" :content="activeFilterCount" color="primary" inline class="ms-1"></v-badge>
                </v-btn>
            </div>
        </header>

        <v-text-field v-model="query"
                      :label="$t('Search')"
                      :loading="loading"
                      prepend-inner-icon="$search"
                      variant="outlined"
                      density="comfortable"
                      rounded="lg"
                      bg-color="surface"
                      hide-details
                      clearable
                      class="find__search"
                      @keydown.enter="flushQuery()"
                      @click:clear="resetQuery()"></v-text-field>

        <recipe-filter-bar v-model="chipFilters" :recipes="library" @update:model-value="onChipFilters"/>

        <section v-if="panel === 'search'" class="find__panel">
            <v-form :disabled="loading">
                <div v-for="filter in Object.values(filters)" :key="filter.id">
                    <template v-if="filter.enabled">
                        <component :is="filter.is" v-bind="getPropsFromFilter(filter)"
                                   density="compact" v-model:modelValue="filter.modelValue" class="find__filter">
                            <template #append>
                                <v-btn icon="fa-solid fa-times" size="small" variant="plain" :aria-label="$t('Remove')"
                                       @click="filter.enabled = false; filter.modelValue = filter.default"></v-btn>
                            </template>
                        </component>
                    </template>
                </div>

                <div class="find__panel-row">
                    <v-autocomplete :items="availableFilters"
                                    :label="$t('AddFilter')"
                                    density="compact"
                                    v-model="addFilterSelect"
                                    @update:model-value="(item:string) =>{ filters[item].enabled = true; nextTick(() => {addFilterSelect = null})}"></v-autocomplete>
                </div>

                <div class="find__panel-row">
                    <v-model-select model="CustomFilter" v-model="selectedCustomFilter" density="compact" :label="$t('SavedSearch')">
                        <template #append>
                            <v-btn icon="fa-solid fa-upload" color="warning" variant="text" size="small"
                                   :disabled="selectedCustomFilter == null" :aria-label="$t('Load')"
                                   @click="loadSelectedCustomFilter()"></v-btn>
                            <v-btn icon="$save" color="save" variant="text" size="small" :aria-label="$t('Save')"
                                   @click="saveCustomFilter()"></v-btn>
                        </template>
                    </v-model-select>
                </div>
            </v-form>

            <div class="find__panel-foot">
                <v-select :label="$t('PerPage')" v-model="pageSize" :items="[10,25,50,100]"
                          density="compact" variant="underlined" hide-details class="find__perpage"></v-select>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="reset()" prepend-icon="$reset">{{ $t('Reset') }}</v-btn>
                <v-btn variant="flat" color="primary" @click="searchRecipes({page: 1})" prepend-icon="$search">{{ $t('Search') }}</v-btn>
            </div>
        </section>

        <div class="find__toolbar">
            <v-btn-toggle v-model="viewMode" density="compact" variant="outlined" divided mandatory class="find__view">
                <v-btn value="grid" icon="fa-solid fa-grip" :aria-label="$t('Cards')"></v-btn>
                <v-btn value="table" icon="fa-solid fa-list" :aria-label="$t('Table')"></v-btn>
            </v-btn-toggle>
        </div>

        <v-card v-if="recipes.length > 0 && viewMode === 'table'" class="find__table">
            <v-data-table-server
                v-model="selectedItems"
                return-object
                @update:options="searchRecipes"
                :loading="loading"
                :items="recipes"
                :headers="tableHeaders"
                :page="page"
                :items-per-page="pageSize"
                :items-length="tableItemCount"
                @click:row="handleRowClick"
                disable-sort
                show-select
                hide-default-footer
            >
                <template v-slot:header.action v-if="selectedItems.length > 0">
                    <v-btn icon="fa-solid fa-ellipsis-v" variant="plain" color="info" :aria-label="$t('Actions')">
                        <v-menu activator="parent" close-on-content-click>
                            <v-list density="compact" class="pt-1 pb-1" activatable>
                                <v-list-item prepend-icon="$edit" @click="batchEditDialog = true">
                                    {{ $t('BatchEdit') }}
                                </v-list-item>
                                <v-list-item prepend-icon="$delete" @click="batchDeleteDialog = true">
                                    {{ $t('Delete_All') }}
                                </v-list-item>
                            </v-list>
                        </v-menu>
                    </v-btn>
                </template>

                <template #item.image="{item}">
                    <v-avatar :image="item.image" size="40" class="my-1" v-if="item.image"></v-avatar>
                    <v-avatar color="primary" variant="tonal" size="40" class="my-1" v-else>
                        <random-icon></random-icon>
                    </v-avatar>
                </template>

                <template #item.name="{item}">
                    <span class="find__name" :title="item.name">{{ item.name }}</span>
                </template>

                <template #item.rating="{item}">
                    <rating-stars v-if="item.rating" :value="item.rating" size="xs"></rating-stars>
                    <span v-else class="find__muted">–</span>
                </template>

                <template #item.description="{item}">
                    <span v-if="item.description" class="find__desc">{{ item.description }}</span>
                    <span v-else class="find__muted">–</span>
                </template>

                <template #item.action="{item}">
                    <recipe-context-menu :recipe="item"></recipe-context-menu>
                </template>
            </v-data-table-server>
        </v-card>

        <div v-if="recipes.length > 0 && viewMode === 'grid'" class="find__grid">
            <book-recipe-tile v-for="r in recipes" :key="r.id" :recipe="r" :meta="tileMeta(r)"></book-recipe-tile>
        </div>

        <div v-if="!loading && recipes.length === 0" class="find__empty">
            <!-- A failed request is not an empty result. During a deploy the API
                 answers 502 for a minute, and "Kein Rezept zu „Köhler“" is then a
                 false claim about the library rather than about the connection. -->
            <template v-if="searchFailed">
                <p class="find__empty-text">Die Suche kam nicht durch — vermutlich kurz keine Verbindung.</p>
                <div class="find__empty-actions">
                    <v-btn variant="text" size="small" @click="searchRecipes({page: page})">Nochmal</v-btn>
                </div>
            </template>
            <template v-else>
                <p class="find__empty-text">
                    {{ debouncedQuery ? `Kein Rezept zu „${debouncedQuery}“.` : 'Keine Rezepte mit diesen Filtern.' }}
                </p>
                <div class="find__empty-actions">
                    <v-btn variant="text" size="small" @click="reset()">{{ $t('Reset') }}</v-btn>
                    <v-btn variant="text" size="small" :to="{name: 'RecipeWishPage'}">Rezept wünschen</v-btn>
                </div>
            </template>
        </div>

        <div class="find__pager">
            <v-pagination v-model="page" :length="Math.ceil(tableItemCount/pageSize)"
                          @update:modelValue="searchRecipes({page: page})" size="small"
                          v-if="recipes.length > 0 && filters['sortOrder'].modelValue != 'random'"></v-pagination>
            <v-btn rounded="xl" prepend-icon="fa-solid fa-dice" variant="tonal" size="large"
                   v-if="recipes.length > 0 && filters['sortOrder'].modelValue == 'random'"
                   @click="searchRecipes({page: 1})">
                {{ $t('Random Recipes') }}
            </v-btn>
        </div>

        <v-dialog v-model="dialog">
            <v-card>
                <v-closable-card-title :title="$t('SavedSearch')" v-model="dialog"></v-closable-card-title>
                <v-card-text>
                    <v-text-field :label="$t('Name')" v-model="newFilterName"></v-text-field>
                </v-card-text>
                <v-card-actions>
                    <v-btn prepend-icon="$create" color="create" @click="createCustomFilter()">{{ $t('Create') }}</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <batch-delete-dialog :items="selectedItems" model="Recipe" v-model="batchDeleteDialog" activator="model"
                             @change="searchRecipes({page: 1})"></batch-delete-dialog>
        <batch-edit-recipe-dialog :items="selectedItems" v-model="batchEditDialog" activator="model"
                                  @change="searchRecipes({page: page})"></batch-edit-recipe-dialog>

    </v-container>
</template>

<script setup lang="ts">

import {computed, markRaw, nextTick, onMounted, ref, toRaw, watch} from "vue";
import {ApiApi, ApiRecipeListRequest, CustomFilter, RecipeOverview} from "@/openapi";
import {useI18n} from "vue-i18n";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {VDateInput} from 'vuetify/labs/VDateInput'
import RecipeContextMenu from "@/components/inputs/RecipeContextMenu.vue";
import {useRouter} from "vue-router";
import {VDataTableUpdateOptions} from "@/vuetify";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import BookRecipeTile from "@/components/display/BookRecipeTile.vue";
import RatingStars from "@/components/display/RatingStars.vue";
import {DateTime} from "luxon";
import {useDisplay} from "vuetify";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import {useRouteQuery} from "@vueuse/router";
import {boolOrUndefinedTransformer, numberOrUndefinedTransformer, routeQueryDateTransformer, stringToBool, toNumberArray} from "@/utils/utils";
import {useDebouncedSearch} from "@/composables/useDebouncedSearch";
import RandomIcon from "@/components/display/RandomIcon.vue";
import {VSelect, VTextField, VNumberInput} from "vuetify/components";
import RatingField from "@/components/inputs/RatingField.vue";
import BatchDeleteDialog from "@/components/dialogs/BatchDeleteDialog.vue";
import {EditorSupportedTypes} from "@/types/Models.ts";
import BatchEditRecipeDialog from "@/components/dialogs/BatchEditRecipeDialog.vue";
import VModelSelect from "@/components/inputs/VModelSelect.vue";
import RecipeFilterBar, {RecipeFilterState} from "@/components/display/RecipeFilterBar.vue";

const {t} = useI18n()
const router = useRouter()
const {mdAndUp} = useDisplay()

const {inputValue: query, debouncedValue: debouncedQuery, signal, flush: flushQuery, reset: resetQuery} = useDebouncedSearch({routeQueryKey: 'query'})
const page = useRouteQuery('page', 1, {transform: Number})
const pageSize = useRouteQuery('pageSize', useUserPreferenceStore().deviceSettings.search_itemsPerPage, {transform: Number})

/**
 * filters that are not yet enabled
 */
const availableFilters = computed(() => {
    let f: Array<{ value: string, title: string }> = []
    useUserPreferenceStore().deviceSettings.search_visibleFilters = []
    Object.entries(filters.value).forEach((entry) => {
        let [key, filter] = entry
        if (!filter.enabled) {
            f.push({value: filter.id, title: filter.label})
        } else {
            useUserPreferenceStore().deviceSettings.search_visibleFilters.push(filter.id)
        }
    })
    return f
})

const loading = ref(false)
const dialog = ref(false)
const panel = ref('')
const addFilterSelect = ref<string | null>(null)
const hasFiltersApplied = ref(false)

const tableHeaders = computed(() => {
    let headers = [
        {title: t('Image'), width: '1%', noBreak: true, key: 'image',},
        {title: t('Name'), key: 'name',},
    ]
    if (mdAndUp.value) {
        // the list view reads stories, not taxonomies: a two-line description says
        // more about a recipe than four chips, and the tags are one click away
        headers.push({title: t('Description'), key: 'description',},)
        headers.push({title: t('Rating'), key: 'rating', width: '1%', noBreak: true, align: 'end'},)
    }
    headers.push({title: t('Actions'), key: 'action', width: '1%', noBreak: true, align: 'end'},)

    return headers
})

const tableItemCount = ref(0)

/** the line under the title: how many recipes the current search found, and which ones are on screen */
const resultLabel = computed(() => {
    if (loading.value) return 'Suche läuft …'
    if (searchFailed.value) return 'Suche fehlgeschlagen'
    const total = tableItemCount.value
    if (!total) return debouncedQuery.value ? `Nichts für „${debouncedQuery.value}“` : 'Keine Rezepte'
    const from = (page.value - 1) * pageSize.value + 1
    const to = Math.min(total, page.value * pageSize.value)
    const base = total === 1 ? '1 Rezept' : `${total} Rezepte`
    return `${base} · ${from}–${to}`
})

/** how many filters are on, for the badge on the panel button */
const activeFilterCount = computed(() => Object.values(filters.value).filter((filter) => filter.enabled).length)

const viewMode = computed({
    get: () => useUserPreferenceStore().deviceSettings.search_viewMode,
    set: (value: string) => {
        useUserPreferenceStore().deviceSettings.search_viewMode = value
    },
})

/** a tile says when the recipe was last cooked; one that never was stays plain */
function tileMeta(recipe: RecipeOverview): string {
    if (!recipe.lastCooked) return ''
    const day = DateTime.fromJSDate(recipe.lastCooked).startOf('day')
    const diff = DateTime.now().startOf('day').diff(day, 'days').days
    if (diff <= 0) return 'heute gekocht'
    if (diff === 1) return 'gestern gekocht'
    if (diff < 31) return `vor ${Math.round(diff)} Tagen gekocht`
    return `zuletzt ${day.setLocale('de').toFormat('d. MMM')}`
}

const recipes = ref([] as RecipeOverview[])
/** the last request failed, so an empty list says nothing about the library */
const searchFailed = ref(false)
const selectedCustomFilter = ref<null | CustomFilter>(null)
const newFilterName = ref('')

const selectedItems = ref([] as EditorSupportedTypes[])
const batchDeleteDialog = ref(false)
const batchEditDialog = ref(false)

/**
 * handle query updates when using the GlobalSearchDialog on the search page directly
 */
watch(debouncedQuery, () => {
    searchRecipes({page: 1})
})

/**
 * perform initial search on mounted
 */
onMounted(() => {
    // load filters that were previously enabled
    useUserPreferenceStore().deviceSettings.search_visibleFilters.forEach(f => {
        if (f in filters.value) {
            filters.value[f].enabled = true
        } else {
            useUserPreferenceStore().deviceSettings.search_visibleFilters.splice(useUserPreferenceStore().deviceSettings.search_visibleFilters.indexOf(f), 1)
        }
    })

    enableFiltersWithValues()
    loadLibrary()
    searchRecipes({page: page.value})
})

/**
 * perform the recipe search with the given options
 * @param options
 */
function searchRecipes(options: VDataTableUpdateOptions) {
    let api = new ApiApi()
    loading.value = true
    searchFailed.value = false
    hasFiltersApplied.value = false
    selectedItems.value = []

    page.value = options.page
    let searchParameters = {
        query: debouncedQuery.value,
        page: options.page,
        pageSize: pageSize.value,
    } as ApiRecipeListRequest

    useUserPreferenceStore().deviceSettings.search_itemsPerPage = pageSize.value

    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            searchParameters[filter.id] = filter.modelValue
            hasFiltersApplied.value = true
        }
    })

    // the chips narrow the same request: one value per axis, AND across axes, which is
    // what `keywords_and` means and what a cook expects from picking two shelves
    if (chipFilters.value.rating !== null) {
        searchParameters.ratingGte = chipFilters.value.rating
        hasFiltersApplied.value = true
    }
    if (chipFilters.value.time !== null) {
        searchParameters.workingTimeLte = chipFilters.value.time
        hasFiltersApplied.value = true
    }
    const axisIds = Object.values(chipFilters.value.axes).filter((id): id is number => id !== null)
    if (axisIds.length) {
        searchParameters.keywordsAnd = axisIds
        hasFiltersApplied.value = true
    }

    api.apiRecipeList(searchParameters, {signal: signal.value}).then((r) => {
        recipes.value = r.results
        tableItemCount.value = r.count
    }).catch(err => {
        if (err.name !== 'AbortError' && err.cause?.name !== 'AbortError') {
            searchFailed.value = true
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }
    }).finally(() => {
        loading.value = false
        window.scrollTo({top: 0, behavior: 'smooth'})
    })
}

/**
 * reset all search parameters and perform emtpy search
 */
function reset() {
    page.value = 1
    resetQuery()
    Object.values(filters.value).forEach((filter) => {
        //filter.enabled = false
        filter.modelValue = filter.default
    })
    selectedCustomFilter.value = null
    chipFilters.value = {sort: '', rating: null, time: null, axes: {}}
    recipes.value = []
    searchRecipes({page: 1})
}

/**
 * handle clicking a table row by opening the selected recipe
 * @param event
 * @param data
 */
function handleRowClick(event: PointerEvent, data: any) {
    router.push({name: 'RecipeViewPage', params: {id: recipes.value[data.index].id}})
}

/**
 * enable UI of filters that have a value that is not the default for the given filter
 */
function enableFiltersWithValues() {
    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            filter.enabled = true
        }
    })
}

/**
 * determines if the current value of a filter is its default value
 * @param filter
 */
function isFilterDefaultValue(filter: any) {
    if (Array.isArray(filter.default) && Array.isArray(filter.modelValue)) {
        return filter.default.length == filter.modelValue.length
    } else if (Number.isNaN(filter.default) && Number.isNaN(filter.modelValue)) {
        return true
    } else {
        return toRaw(filter.default) === filter.modelValue
    }
}

/**
 * to prevent browser warnings from unused/wrong props on the target component
 * @param filter
 */
function getPropsFromFilter(filter: any){
    const {
        id,
        enabled,
        is,
        default: defaultValue,
        ...props
    } = filter

    return props
}

// -------------------------------------------
// --------- Logic for saved filters ---------
// -------------------------------------------

/**
 * triggered by save button, if filter exists update it, if not open dialog to create a new filter
 */
function saveCustomFilter() {
    let api = new ApiApi()

    if (selectedCustomFilter.value != null) {
        loading.value = true
        selectedCustomFilter.value.search = JSON.stringify(filtersToCustomFilterFormat())
        api.apiCustomFilterUpdate({id: selectedCustomFilter.value.id!, customFilter: selectedCustomFilter.value}).then((r) => {
            selectedCustomFilter.value = r
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        }).finally(() => {
            loading.value = false
        })
    } else {
        newFilterName.value = ''
        dialog.value = true
    }
}

/**
 * create a new saved search filter in the database via api
 */
function createCustomFilter() {
    let api = new ApiApi()

    dialog.value = false
    loading.value = true
    api.apiCustomFilterCreate({customFilter: {name: newFilterName.value, search: JSON.stringify(filtersToCustomFilterFormat())} as CustomFilter}).then((r) => {
        selectedCustomFilter.value = r
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
    }).finally(() => {
        loading.value = false
    })
}

/**
 * load selected custom filter into the filters system
 */
function loadSelectedCustomFilter() {
    let customFilterParams = JSON.parse(selectedCustomFilter.value.search)
    if (customFilterParams['version'] == null) {
        customFilterParams = transformTandoor1Filter(customFilterParams)
    }

    if (customFilterParams['query'] != null) {
        query.value = customFilterParams['query']
    }

    Object.values(filters.value).forEach((filter) => {
        let filterName = filter.id.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
        if (customFilterParams[filterName] != null) {
            filter.modelValue = customFilterParams[filterName]
            filter.enabled = true
        }
    })

}

/**
 * convert filters to custom filter format
 */
function filtersToCustomFilterFormat() {
    let customFilterParams: any = {};

    if (query.value != '') {
        customFilterParams['query'] = query.value;
    }

    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            let filterName = filter.id.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
            customFilterParams[filterName] = filter.modelValue
        }
    })

    customFilterParams['version'] = '2'

    return customFilterParams
}

/**
 * transform a filter that is in the tandoor 1 format into the tandoor 2 format
 * @param customFilterParams
 */
function transformTandoor1Filter(customFilterParams: any) {

    // _or was basically an alias to the standard filter which behaves like an or filter
    [['books_or', 'books'], ['foods_or', 'foods'], ['keywords_or', 'keywords'],].forEach(pair => {
        if (customFilterParams[pair[1]] != null) {
            if (customFilterParams[pair[2]] != null) {
                customFilterParams[pair[2]].concat(customFilterParams[pair[1]])
            } else {
                customFilterParams[pair[2]] = customFilterParams[pair[1]]
            }
        }
    })

    if (customFilterParams['cookedon'] != null) {
        if (customFilterParams['cookedon'].startsWith('-')) {
            customFilterParams['cookedon_lte'] = customFilterParams['cookedon'].substring(1)
        } else {
            customFilterParams['cookedon_gte'] = customFilterParams['cookedon']
        }
    }

    if (customFilterParams['viewedon'] != null) {
        if (customFilterParams['viewedon'].startsWith('-')) {
            customFilterParams['viewedon_lte'] = customFilterParams['viewedon'].substring(1)
        } else {
            customFilterParams['viewedon_gte'] = customFilterParams['viewedon']
        }
    }

    if (customFilterParams['updatedon'] != null) {
        if (customFilterParams['updatedon'].startsWith('-')) {
            customFilterParams['updatedon_lte'] = customFilterParams['updatedon'].substring(1)
        } else {
            customFilterParams['updatedon_gte'] = customFilterParams['updatedon']
        }
    }

    if (customFilterParams['createdon'] != null) {
        if (customFilterParams['createdon'].startsWith('-')) {
            customFilterParams['createdon_lte'] = customFilterParams['createdon'].substring(1)
        } else {
            customFilterParams['createdon_gte'] = customFilterParams['createdon']
        }
    }

    if (customFilterParams['rating'] != null) {
        if (customFilterParams['rating'].startsWith('-')) {
            customFilterParams['rating_lte'] = customFilterParams['rating'].substring(1)
        } else {
            customFilterParams['rating_gte'] = customFilterParams['rating']
        }
    }

    if (customFilterParams['timescooked'] != null) {
        if (customFilterParams['timescooked'].startsWith('-')) {
            customFilterParams['timescooked_lte'] = customFilterParams['timescooked'].substring(1)
        } else {
            customFilterParams['timescooked_gte'] = customFilterParams['timescooked']
        }
    }

    customFilterParams['version'] = '2'

    return customFilterParams
}

/*
[this.$t("search_rank"), "score", "1-9", "9-1"],
[this.$t("Name"), "name", "A-z", "Z-a"],
[this.$t("last_cooked"), "lastcooked", "↑", "↓"],
[this.$t("Rating"), "rating", "1-5", "5-1"],
[this.$t("times_cooked"), "favorite", "x-X", "X-x"],
[this.$t("date_created"), "created_at", "↑", "↓"],
[this.$t("date_viewed"), "lastviewed", "↑", "↓"],
*/
/**
 * all filters available to enable
 */
const filters = ref({
    sortOrder: {
        id: 'sortOrder',
        label: `${t('sort_by')}`,
        hint: '',
        enabled: false,
        default: "",
        is: VSelect,
        items: [
            {value: "random", title: `${t('RandomOrder')}`},
            {value: "score", title: `${t('search_rank')} (1-9)`},
            {value: "-score", title: `${t('search_rank')} (9-1)`},
            {value: "name", title: `${t('Name')} (A-z)`},
            {value: "-name", title: `${t('Name')} (Z-a)`},
            {value: "lastcooked", title: `${t('last_cooked')} (↑)`},
            {value: "-lastcooked", title: `${t('last_cooked')} (↓)`},
            {value: "rating", title: `${t('Rating')} (1-5)`},
            {value: "-rating", title: `${t('Rating')} (5-1)`},
            {value: "times_cooked", title: `${t('favorite')} (↑)`},
            {value: "-times_cooked", title: `${t('favorite')} (↓)`},
            {value: "created_at", title: `${t('date_created')} (↑)`},
            {value: "-created_at", title: `${t('date_created')} (↓)`},
            {value: "lastviewed", title: `${t('date_viewed')} (↑)`},
            {value: "-lastviewed", title: `${t('date_viewed')} (↓)`},
        ],
        modelValue: useRouteQuery('sortOrder', "")
    },
    keywords: {
        id: 'keywords',
        label: `${t('Keywords')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywords', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsAnd: {
        id: 'keywordsAnd',
        label: `${t('Keywords')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsOrNot: {
        id: 'keywordsOrNot',
        label: `${t('Keywords')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsAndNot: {
        id: 'keywordsAndNot',
        label: `${t('Keywords')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foods: {
        id: 'foods',
        label: `${t('Foods')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foods', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsAnd: {
        id: 'foodsAnd',
        label: `${t('Foods')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foodsAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsOrNot: {
        id: 'foodsOrNot',
        label: `${t('Foods')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue:  useRouteQuery('foodsOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsAndNot: {
        id: 'foodsAndNot',
        label: `${t('Foods')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foodsAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    books: {
        id: 'books',
        label: `${t('Books')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('books', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksAnd: {
        id: 'booksAnd',
        label: `${t('Books')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksOrNot: {
        id: 'booksOrNot',
        label: `${t('Books')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksAndNot: {
        id: 'booksAndNot',
        label: `${t('Books')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    createdby: {
        id: 'createdby',
        label: t('CreatedBy'),
        hint: t('searchFilterCreatedByHelp'),
        enabled: false,
        default: undefined,
        is: markRaw(VModelSelect),
        model: 'User',
        modelValue: useRouteQuery('createdby', undefined, {transform: numberOrUndefinedTransformer}),
        returnObject: false,
    },
    units: {
        id: 'units',
        label: `${t('Units')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Units')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Unit',
        modelValue: [],
        modelValueId: useRouteQuery('units', [], {transform: toNumberArray}),
        multiple: true,
        chips: true,
    },
    internal: {
        id: 'internal',
        label: t('Hide_External'),
        hint: t('searchFilterHideExternalHelp'),
        enabled: false,
        default: undefined,
        is: markRaw(VSelect),
        items: [{value: true, title: 'Yes'}, {value: false, title: 'No'}],
        modelValue: useRouteQuery('internal', undefined, {transform: boolOrUndefinedTransformer})
    },
    // random: {
    //     id: 'random',
    //     label: t('RandomOrder'),
    //     hint: t('searchFilterRandomHelp'),
    //     enabled: false,
    //     default: "false",
    //     is: VSelect,
    //     items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
    //     modelValue: useRouteQuery('random', "false")
    // },
    rating: {
        id: 'rating',
        label: `${t('Rating')} (${t('exact')})`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery('rating', undefined, {transform: numberOrUndefinedTransformer}),
    },
    ratingGte: {
        id: 'ratingGte',
        label: `${t('Rating')} (>=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery('ratingGte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    ratingLte: {
        id: 'ratingLte',
        label: `${t('Rating')} (<=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery('ratingLte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescooked: {
        id: 'timescooked',
        label: `${t('times_cooked')} (${t('exact')})`,
        hint: 'Recipes that were cooked at least X times',
        enabled: false,
        default: undefined,
        clearable: true,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery('timescooked', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescookedGte: {
        id: 'timescookedGte',
        label: `${t('times_cooked')} (>=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery('timescookedGte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescookedLte: {
        id: 'timescookedLte',
        label: `${t('times_cooked')} (<=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery('timescookedLte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    makenow: {
        id: 'makenow',
        label: t('OnHand'),
        hint: t('searchFilterOnHandHelp'),
        enabled: false,
        default: "false",
        is: markRaw(VSelect),
        items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
        modelValue: useRouteQuery('makenow', "false"),
    },
    cookedonGte: {
        id: 'cookedonGte',
        label: `${t('Cooked')} ${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('cookedonGte', null, {transform: routeQueryDateTransformer}),
    },
    cookedonLte: {
        id: 'cookedonLte',
        label: `${t('Cooked')} ${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('cookedonLte', null, {transform: routeQueryDateTransformer}),
    },
    viewedonGte: {
        id: 'viewedonGte',
        label: `${t('Viewed')} ${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('viewedonGte', null, {transform: routeQueryDateTransformer}),
    },
    viewedonLte: {
        id: 'viewedonLte',
        label: `${t('Viewed')} ${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('viewedonLte', null, {transform: routeQueryDateTransformer}),
    },
    createdon: {
        id: 'createdon',
        label: `${t('Created')} ${t('on')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdon', null, {transform: routeQueryDateTransformer}),
    },
    createdonGte: {
        id: 'createdonGte',
        label: `${t('Created')} ${t('on')}/${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdonGte', null, {transform: routeQueryDateTransformer}),
    },
    createdonLte: {
        id: 'createdonLte',
        label: `${t('Created')} ${t('on')}/${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdonLte', null, {transform: routeQueryDateTransformer}),
    },
    updatedon: {
        id: 'updatedon',
        label: `${t('Updated')} ${t('on')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedon', null, {transform: routeQueryDateTransformer}),
    },
    updatedonGte: {
        id: 'updatedonGte',
        label: `${t('Updated')} ${t('on')}/${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedonGte', null, {transform: routeQueryDateTransformer}),
    },
    updatedonLte: {
        id: 'updatedonLte',
        label: `${t('Updated')} ${t('on')}/${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedonLte', null, {transform: routeQueryDateTransformer}),
    },
    includeChildren: {
        id: 'includeChildren',
        label: t('Include Children'),
        hint: t('Include child keywords and foods in search results'),
        enabled: false,
        default: "true",  // Default enabled like v1
        is: markRaw(VSelect),
        items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
        modelValue: useRouteQuery('includeChildren', 'true')
    },
})

/**
 * The chip bar's state. Sort is not kept here alone: it lives in `filters.sortOrder`,
 * which is a route query, a toolbar control and the paginator's "random" branch — so a
 * chip writes there and the existing watcher does the searching.
 */
const chipFilters = ref<RecipeFilterState>({
    sort: (filters.value.sortOrder.modelValue as string) ?? '',
    rating: null,
    time: null,
    axes: {},
})

/** the whole shelf, only to count what the chips may offer; filtering stays on the server */
const library = ref<RecipeOverview[]>([])

async function loadLibrary() {
    try {
        const api = new ApiApi()
        // the server caps a page at 100, so a count over one page would undercount
        // every chip ("Italien 10" for a node 38 recipes carry)
        const gathered: RecipeOverview[] = []
        for (let pageNo = 1; pageNo <= 20; pageNo++) {
            const chunk = await api.apiRecipeList({pageSize: 100, page: pageNo})
            gathered.push(...chunk.results)
            if (!chunk.next || chunk.results.length === 0) break
        }
        library.value = gathered
    } catch (e) {
        // counts are a convenience — a failed load must not take the search down with it
    }
}

function onChipFilters(value: RecipeFilterState) {
    const sortChanged = chipFilters.value.sort !== value.sort
    chipFilters.value = value
    if (sortChanged) {
        filters.value.sortOrder.modelValue = value.sort
        return // the watcher below searches
    }
    searchRecipes({page: 1})
}

/** sorting sits next to the results now, so changing it has to search instead of waiting for the button */
watch(() => filters.value.sortOrder.modelValue, () => {
    if (recipes.value.length > 0) searchRecipes({page: 1})
})
</script>

<style scoped>
.find {
    max-width: 1100px;
    padding-bottom: 4rem;
}

.find__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.5rem 0 1.1rem;
}

.find__title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2rem, 5vw, 2.8rem);
    font-weight: 600;
    line-height: 1.05;
    letter-spacing: -.01em;
}

.find__sub {
    margin-top: .35rem;
    font-size: .92rem;
    color: rgba(var(--v-theme-on-surface), .6);
}

.find__head-actions {
    display: flex;
    align-items: center;
    gap: .25rem;
    flex: none;
}

.find__search {
    max-width: 46rem;
}

.find__panel {
    margin-top: 1rem;
    padding: 1rem 1.1rem 1.1rem;
    border-radius: 14px;
    background: rgb(var(--v-theme-surface));
    box-shadow: 0 1px 2px rgba(60, 40, 25, .08), 0 10px 26px -22px rgba(60, 40, 25, .5);
}

.find__filter + .find__filter {
    margin-top: .4rem;
}

.find__panel-row {
    margin-top: .75rem;
}

.find__perpage {
    max-width: 9rem;
}

.find__panel-foot {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: .5rem;
    margin-top: 1rem;
    padding-top: .9rem;
    border-top: 1px solid rgba(var(--v-theme-on-surface), .08);
}

.find__toolbar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 1.6rem 0 .9rem;
    padding-bottom: .5rem;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), .08);
}

.find__sort {
    max-width: 17rem;
}

.find__view {
    margin-left: auto;
    flex: none;
}

.find__table {
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(60, 40, 25, .08), 0 10px 26px -22px rgba(60, 40, 25, .5);
}

.find__grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .9rem;
}

@media (min-width: 700px) {
    .find__grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (min-width: 1100px) {
    .find__grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
}

/* one line, ellipsis, full name in the tooltip: a table row that wraps its name to
   two lines and its description to two more is a card, not a row */
.find__name {
    display: block;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-weight: 600;
}

/* two lines of prose, then an ellipsis: enough to recognise a dish, short enough
   that four rows still fit a screen */
.find__desc {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: .85rem;
    line-height: 1.4;
    color: rgba(var(--v-theme-on-surface), .78);
}

.find__muted {
    color: rgba(var(--v-theme-on-surface), .45);
}

.find__empty {
    padding: 1.4rem 1.25rem;
    border-radius: 14px;
    border: 1px dashed rgba(var(--v-theme-on-surface), .18);
    background: rgba(var(--v-theme-surface), .55);
}

.find__empty-text {
    margin-bottom: .9rem;
    color: rgba(var(--v-theme-on-surface), .7);
}

.find__empty-actions {
    display: flex;
    flex-wrap: wrap;
    gap: .5rem;
}

.find__pager {
    display: flex;
    justify-content: center;
    margin-top: 1.75rem;
}
</style>
