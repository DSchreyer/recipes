<template>
    <v-img v-if="hasImage" :cover="cover" :style="{'height': height, 'width': width,}" color="recipeImagePlaceholderBg" :src="image"
           :alt="$t('Recipe_Image')" :rounded="props.rounded">
        <slot name="overlay">
        </slot>
    </v-img>
    <!-- Recipes without a photo are mostly the reference sheets (Technik, Vorrat,
         Grundteig). A stock "no image" icon there looks like a broken page; the
         monogram reads as a deliberate title card instead. -->
    <div v-else class="recipe-image-blank" :style="{'height': height, 'width': width, borderRadius: radius}">
        <span class="recipe-image-blank__monogram">{{ monogram }}</span>
        <slot name="overlay">
        </slot>
    </div>
</template>

<script setup lang="ts">

import {computed, PropType} from "vue";
import {Recipe, RecipeOverview} from "@/openapi";

const props = defineProps({
    recipe: {type: {} as PropType<Recipe | RecipeOverview | undefined>, required: false, default: undefined},
    height: {type: String},
    width: {type: String},
    cover: {type: Boolean, default: true},
    rounded: {type: [Boolean, String], default: false},
})

const image = computed(() => props.recipe?.image ?? null)

const hasImage = computed(() => !!image.value)

const monogram = computed(() => (props.recipe?.name ?? '').trim().charAt(0).toUpperCase() || '·')

const radius = computed(() => {
    if (props.rounded === true) return '8px'
    if (typeof props.rounded === 'string') return '16px'
    return undefined
})

</script>

<style scoped>
.recipe-image-blank {
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: rgb(var(--v-theme-recipeImagePlaceholderBg));
    box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), .06);
    container-type: inline-size;
}

.recipe-image-blank__monogram {
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(.95rem, 26cqw, 3.4rem);
    line-height: 1;
    color: rgba(var(--v-theme-on-surface), .28);
    user-select: none;
}
</style>
