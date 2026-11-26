/**
 * The four things a cook scans a recipe for, taken from the flat keyword tree.
 *
 * Keywords are stored as paths ("Herkunft::Mittelmeer::Italien::Toskana") and the
 * tree is flat, so a recipe carries the shelf, the country and the region as three
 * siblings. For a chip we want one value per axis: strip the axis, drop the shelf
 * segment when a deeper one exists, keep the most specific label.
 */

export interface AxisChip {
    axis: string
    value: string
}

export interface KeywordGroup {
    axis: string
    values: string[]
}

const AXES: string[] = ['Herkunft', 'Beilage', 'Hauptzutat', 'Aufwand']

const OTHER = 'Weitere'

function labels(keywords?: { label?: string }[] | null): string[] {
    if (!keywords) return []
    return keywords.map(k => k.label).filter((l): l is string => !!l)
}

function pathsUnder(labels: string[], axis: string): string[][] {
    return labels
        .filter(l => l.startsWith(axis + '::'))
        .map(l => l.split('::').filter(s => s.length > 0))
        .filter(p => p.length > 1)
}

/** one chip per axis: the most specific value the recipe carries for it */
export function axisChips(keywords?: { label?: string }[] | null): AxisChip[] {
    const all = labels(keywords)
    const chips: AxisChip[] = []
    for (const axis of AXES) {
        const paths = pathsUnder(all, axis)
        if (paths.length === 0) continue
        // longest path = most specific value (Italien::Toskana beats Italien)
        const deepest = paths.reduce((a, b) => (b.length > a.length ? b : a))
        chips.push({axis, value: capitalise(deepest[deepest.length - 1])})
    }
    return chips
}

/**
 * Every keyword, grouped by axis for the "Alle Merkmale" dialog. Anything outside
 * the four cooking axes (Rezepttyp, machine tags like "atlas:…") lands in "Weitere"
 * so no information is silently dropped.
 */
export function groupedKeywords(keywords?: { label?: string }[] | null): KeywordGroup[] {
    const all = labels(keywords)
    const groups: KeywordGroup[] = []

    for (const axis of AXES) {
        const values = unique(pathsUnder(all, axis).map(p => p[p.length - 1]).map(capitalise))
        if (values.length > 0) groups.push({axis, values})
    }

    const rest = all
        .filter(l => !AXES.some(a => l.startsWith(a + '::')))
        .map(readable)
        .filter(v => v.length > 0)
    const other = unique(rest)
    if (other.length > 0) groups.push({axis: OTHER, values: other})

    return groups
}

/**
 * "Rezepttyp::Grundlagen" reads better as "Grundlagen"; a namespaced machine tag
 * such as "atlas:bistecca-fiorentina" is shown as it is, lower case — it is a key,
 * not a word, and capitalising it invents a name nobody uses.
 */
function readable(label: string): string {
    const parts = label.split('::').filter(s => s.length > 0)
    const leaf = parts.length > 1 ? parts[parts.length - 1] : parts[0] ?? label
    return leaf.includes(':') ? leaf : capitalise(leaf)
}

function unique(values: string[]): string[] {
    return [...new Set(values)].sort((a, b) => a.localeCompare(b, 'de'))
}

function capitalise(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1)
}
