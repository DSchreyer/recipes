import {useDjangoUrls} from "@/composables/useDjangoUrls";
import {ref} from "vue";
import {getCookie} from "@/utils/cookie";
import {AiProvider, RecipeFromSourceResponseFromJSON, RecipeImageFromJSON, ResponseError, UserFile, UserFileFromJSON} from "@/openapi";
import {tr} from "vuetify/locale";


/**
 * function to upload files to the multipart endpoints accepting file uploads
 */
export function useFileApi() {
    const {getDjangoUrl} = useDjangoUrls()

    const fileApiLoading = ref(false)

    /**
     * creates or updates an existing UserFile if an id is given
     * @param name name to set for user file
     * @param file file object to upload
     * @param id optional id to update existing user file
     */
    function createOrUpdateUserFile(name: string, file: File | null, id?: number): Promise<UserFile> {
        let formData = new FormData()
        formData.append('name', name)

        if (file != null) {
            formData.append('file', file)
        }

        fileApiLoading.value = true

        let fetchUrl = getDjangoUrl('api/user-file/')
        let fetchMethod = 'POST'
        if (id) {
            fetchUrl += `${id}/`
            fetchMethod = 'PUT'
        }

        return fetch(fetchUrl, {
            method: fetchMethod,
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            body: formData
        }).then(r => {
            if (r.ok) {
                return r.json().then(r => {
                    return UserFileFromJSON(r)
                })
            } else {
                throw new ResponseError(r)
            }
        }).finally(() => {
            fileApiLoading.value = false
        })
    }

    /**
     * update a recipes image either by a given file or given url
     * @param recipeId ID of recipe to update
     * @param file file object to upload or null to delete image (if no imageUrl is given)
     * @param imageUrl url of an image to download by server
     */
    function updateRecipeImage(recipeId: number, file: File | null, imageUrl?: string) {
        let formData = new FormData()
        if (file != null) {
            formData.append('image', file)
        }
        if (imageUrl) {
            formData.append('image_url', imageUrl)
        }

        return fetch(getDjangoUrl(`api/recipe/${recipeId}/image/`), {
            method: 'PUT',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            body: formData
        }).then(r => {
            return r.json().then(r => {
                return RecipeImageFromJSON(r)
            })
        }).finally(() => {
            fileApiLoading.value = false
        })
    }

    /**
     * uploads the given file to the image recognition endpoint
     * @param file file object to upload
     * @param text text to import
     * @param recipeId id of a recipe to use as import base (for external recipes
     */
    function doAiImport(providerId: number, file: File | null, text: string = '', recipeId: string = '') {
        let formData = new FormData()

        if (file != null) {
            formData.append('file', file)
        } else {
            formData.append('file', '')
        }
        formData.append('text', text)
        formData.append('recipe_id', recipeId)
        formData.append('ai_provider_id', providerId)
        fileApiLoading.value = true

        return fetch(getDjangoUrl(`api/ai-import/`), {
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            body: formData
        }).then(r => {
            return r.json().then(r => {
                return RecipeFromSourceResponseFromJSON(r)
            })
        }).finally(() => {
            fileApiLoading.value = false
        })
    }

    /**
     * URL (or free text) into a recipe through the ai_import plugin.
     *
     * Tandoor's own `/api/recipe-from-source/` returns what the page published,
     * so a Chefkoch page without usable structured data becomes a three-step
     * recipe under a marketing title. The plugin fetches the page, has the
     * household's own AiProvider shape it, then checks every food, unit and
     * tag against this space before answering in the shape the import dialog
     * already consumes.
     *
     * Nothing is saved here on purpose: the dialog shows the draft, the
     * household corrects it and saves. An import nobody reviewed is how a
     * recipe library rots.
     */
    function doAiImportFromSource(providerId: number, url: string = '', text: string = '',
                                  wish: Record<string, unknown> | null = null) {
        fileApiLoading.value = true

        return fetch(getDjangoUrl(`api/plugins/ai-import/from-source/`), {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
            // A wish is a text request plus the household's constraints: servings,
            // a time budget, a diet, what not to use, what is in the fridge. The
            // plugin turns them into binding prompt lines instead of prose, so a
            // wish saying "für vier" cannot outvote a servings field of 6.
            body: JSON.stringify({ai_provider_id: providerId, url, text, ...(wish ? {wish} : {})}),
        }).then(r => {
            return r.json().then(raw => {
                const response = RecipeFromSourceResponseFromJSON(raw)
                // The generated mapper rebuilds every step from a fixed field
                // list and drops anything it does not know, so the plugin's own
                // per-step state has to be copied back by index. Without this
                // the dialog cannot say which step has no amounts.
                const rawSteps = (raw && raw.recipe && raw.recipe.steps) || []
                const steps = (response && response.recipe && response.recipe.steps) || []
                steps.forEach((step: any, index: number) => {
                    const state = rawSteps[index] && rawSteps[index].placeholder_state
                    if (state) {
                        step.placeholder_state = state
                    }
                })
                // Same reason, for the wish page: what the database does not
                // know yet and what the tag list refused.
                const extra = response as any
                extra.unknownFoods = (raw && raw.unknown_foods) || []
                extra.rejectedTags = (raw && raw.rejected_tags) || []
                extra.warnings = (raw && raw.warnings) || []
                return response
            })
        }).finally(() => {
            fileApiLoading.value = false
        })
    }

    /**
     * uploads the given files to the app import endpoint
     * @param files array to import
     * @param app app to import
     * @param includeDuplicates if recipes that were found as duplicates should be imported as well
     * @param mealPlans if meal plans should be imported
     * @param shoppingLists if shopping lists should be imported
     * @param nutritionPerServing if nutrition information should be treated as per serving (if false its treated as per recipe)
     * @returns Promise resolving to the import ID of the app import
     */
    function doAppImport(files: File[], app: string, includeDuplicates: boolean, mealPlans: boolean = true, shoppingLists: boolean = true, nutritionPerServing: boolean = false,) {
        fileApiLoading.value = true

        let formData = new FormData()
        formData.append('type', app);
        formData.append('duplicates', includeDuplicates ? 'true' : 'false')
        formData.append('meal_plans', mealPlans ? 'true' : 'false')
        formData.append('shopping_lists', shoppingLists ? 'true' : 'false')
        formData.append('nutrition_per_serving', nutritionPerServing ? 'true' : 'false')
        files.forEach(file => {
            formData.append('files', file)
        })

        return fetch(getDjangoUrl(`api/import/`), {
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            body: formData
        }).then(r => {
            return r.json().then(r => {
                return r.import_id
            })
        }).finally(() => {
            fileApiLoading.value = false
        })
    }

    return {
        fileApiLoading,
        createOrUpdateUserFile,
        updateRecipeImage,
        doAiImport,
        doAiImportFromSource,
        doAppImport,
    }
}
