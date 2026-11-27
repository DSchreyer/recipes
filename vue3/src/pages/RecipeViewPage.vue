<template>
    <v-container :class="{'ps-0 pe-0 pt-0': mobile}">
        <v-defaults-provider :defaults="(useUserPreferenceStore().isPrintMode ? {VCard: {variant: 'flat'}} : {})">


           <recipe-view v-model="recipe" :servings="servings"></recipe-view>

            <!-- the page is the only place with the full width this grid needs; inside the
                 intro card it came out in the tag column at 85px per tile -->
            <similar-recipes v-if="recipe?.id" :recipe="recipe" class="mt-4"></similar-recipes>

            <div class="mt-2" v-if="isShared && Object.keys(recipe).length > 0">
                <import-tandoor-dialog></import-tandoor-dialog>
            </div>
        </v-defaults-provider>

    </v-container>

</template>

<script setup lang="ts">
import {computed, onMounted, ref, watch} from 'vue'
import {ApiApi, ApiRecipeRetrieveRequest, Recipe, ViewLog} from "@/openapi";
import RecipeView from "@/components/display/RecipeView.vue";
import {useDisplay} from "vuetify";
import {useTitle, useUrlSearchParams} from "@vueuse/core";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import ImportTandoorDialog from "@/components/dialogs/ImportTandoorDialog.vue";
import SimilarRecipes from "@/components/display/SimilarRecipes.vue";

const props = defineProps({
    id: {type: String, required: true}
})

const params = useUrlSearchParams('history')
const {mobile} = useDisplay()
const title = useTitle()

const isShared = computed(() => {
    return params.share && typeof params.share == "string"
})

const servings = computed(() => {
    const value = params.servings
    if (!value) return undefined
    const parsed = parseInt(value as string, 10)
    return parsed > 0 ? parsed : undefined
})

const recipe = ref({} as Recipe)

watch(() => props.id, () => {
    refreshData(props.id)
})

onMounted(() => {
    refreshData(props.id)
})

function refreshData(recipeId: string) {
    const api = new ApiApi()
    recipe.value = {} as Recipe

    let requestParameters: ApiRecipeRetrieveRequest = {id: props.id}
    if (isShared.value) {
        requestParameters.share = params.share
    }

    api.apiRecipeRetrieve(requestParameters).then(r => {
        recipe.value = r
        title.value = recipe.value.name

        setTimeout(() => {
            if (useUserPreferenceStore().isPrintMode) {
                window.print()
            }
        }, 500)

        if (useUserPreferenceStore().isAuthenticated) {
            api.apiViewLogCreate({viewLog: {recipe: Number(recipeId)} as ViewLog})
        }
    }).catch(err => {
        if (err.response.status == 403) {
            // TODO maybe redirect to login if fails with 403? or conflict with group/sapce system?
        } else {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }
    })
}

</script>

<style scoped>

</style>