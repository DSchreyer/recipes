<template>
    <span v-if="value" class="rating-stars" :class="[sizeClass, {'rating-stars--chip': chip}]" role="img"
          :aria-label="ariaLabel">
        <span class="rating-stars__stars" aria-hidden="true">
            <span class="rating-stars__track">
                <i v-for="n in 5" :key="'t' + n" class="fa-regular fa-star"></i>
            </span>
            <span class="rating-stars__fill" :style="{width: fillWidth}">
                <i v-for="n in 5" :key="'f' + n" class="fa-solid fa-star"></i>
            </span>
        </span>
        <span v-if="showValue" class="rating-stars__value">{{ number }}</span>
    </span>
</template>

<script setup lang="ts">
import {computed} from 'vue'

/**
 * A rating in quarter steps, drawn as a clipped star row.
 *
 * Vuetify's v-rating only fills halves, so a 4.25 rating renders as 4 or 4.5 and
 * the quarter the household chose disappears. Here the fill is a solid star row
 * clipped to the exact fraction, so the same number shows everywhere.
 *
 * `chip` gives the stars and the number a tinted pill, for places where the
 * rating should read as a verdict rather than decoration.
 */
const props = withDefaults(defineProps<{
    value?: number | null
    size?: 'sm' | 'md' | 'lg'
    chip?: boolean
    showValue?: boolean
}>(), {
    size: 'sm',
    chip: false,
    showValue: true,
})

const number = computed(() => {
    const value = props.value ?? 0
    return value.toFixed(2).replace(/\.?0+$/, '').replace('.', ',')
})

const fillWidth = computed(() => `${Math.max(0, Math.min(5, props.value ?? 0)) / 5 * 100}%`)

const ariaLabel = computed(() => `${number.value} von 5 Sternen`)

const sizeClass = computed(() => `rating-stars--${props.size}`)
</script>

<style scoped>
.rating-stars {
    display: inline-flex;
    align-items: center;
    gap: 0.35em;
    line-height: 1;
    vertical-align: -0.08em;
    white-space: nowrap;
}

.rating-stars__stars {
    position: relative;
    display: inline-block;
    white-space: nowrap;
}

.rating-stars__track {
    color: #d8ccb6;
}

.rating-stars__fill {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    overflow: hidden;
    color: rgb(var(--v-theme-star));
    white-space: nowrap;
}

/* A fixed one-em box per star keeps the clip aligned with the glyph, so 4.25
   fills exactly a quarter of the fifth star instead of drifting into the gap. */
.rating-stars__track i,
.rating-stars__fill i {
    display: inline-block;
    width: 1em;
    margin: 0;
    text-align: center;
}

.rating-stars--sm {
    font-size: 0.9rem;
}

.rating-stars--md {
    font-size: 1.15rem;
}

.rating-stars--lg {
    font-size: 1.45rem;
}

.rating-stars__value {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
}

.rating-stars--chip {
    padding: 0.12rem 0.55rem 0.12rem 0.42rem;
    border-radius: 999px;
    background: rgba(var(--v-theme-star), 0.10);
    border: 1px solid rgba(var(--v-theme-star), 0.22);
    color: rgb(var(--v-theme-star));
    gap: 0.2em;
}

/* A hairline keeps the number from touching the last star. */
.rating-stars--chip .rating-stars__value {
    padding-left: 0.5em;
    border-left: 1px solid rgba(var(--v-theme-star), 0.3);
    font-size: 0.95em;
}
</style>
