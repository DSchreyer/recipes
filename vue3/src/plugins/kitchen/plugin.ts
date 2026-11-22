import type {TandoorPlugin} from "@/types/Plugins.ts";
import {VListItem} from "vuetify/components";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";
import en from "./locales/en.json";

/**
 * Frontend half of the `kitchen` plugin: one sidebar entry.
 *
 * The page itself is Django-rendered at `/api/plugins/kitchen/`, because the
 * ranking runs over the whole recipe library in one queryset and the page needs
 * no client state -- see `docs/superpowers/specs/2026-11-21-kitchen-picker-design.md`
 * in the Atlas repo. So there is no Vue route, no component and no API call
 * here: the entry is an `<a href>`, the same shape Tandoor's own Admin entry
 * uses, and the browser does a normal page load.
 *
 * `useDjangoUrls()` respects a sub-path install, which a bare
 * `/api/plugins/kitchen/` would not.
 *
 * `defaultLocale` must be a **promise** -- Tandoor calls `.then()` on it at
 * startup (`vue3/src/i18n.ts`); an object throws "defaultLocale.then is not a
 * function" and blanks the whole app.
 */
export const plugin: TandoorPlugin = {
    name: 'kitchen',
    basePath: 'kitchen',
    defaultLocale: Promise.resolve(en),
    localeFiles: import.meta.glob('./locales/*.json'),
    routes: [],
    navigationDrawer: [
        {
            component: VListItem,
            prependIcon: 'fa-solid fa-utensils',
            title: 'Recipe_Finder',
            href: useDjangoUrls().getDjangoUrl('api/plugins/kitchen/'),
        },
        {
            component: VListItem,
            prependIcon: 'fa-solid fa-clock-rotate-left',
            title: 'Gekocht',
            href: useDjangoUrls().getDjangoUrl('api/plugins/kitchen/gekocht/'),
        },
    ],
    bottomNavigation: [],
    userNavigation: [],
}
