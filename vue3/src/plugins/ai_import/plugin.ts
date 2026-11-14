import type {TandoorPlugin} from "@/types/Plugins.ts";
import AiImportSettings from "./AiImportSettings.vue";
import SettingsNavItem from "./SettingsNavItem.vue";
import en from "./locales/en.json";

/**
 * Frontend half of the ai_import plugin.
 *
 * Tandoor's Vue app globs `vue3/src/plugins/* /plugin.ts` and asks each plugin
 * for routes, navigation entries and a `settingsComponent`, which the settings
 * page renders under *Space*. This plugin only needs the last one: the import
 * lives in the existing import dialog, and its switches belong beside the
 * other space settings.
 *
 * `defaultLocale` must be a **promise** -- Tandoor calls `.then()` on it at
 * startup (`vue3/src/i18n.ts`). Handing it an object throws
 * "defaultLocale.then is not a function" and takes the whole app down with a
 * blank page, which is how this was found.
 */
export const plugin: TandoorPlugin = {
    name: 'ai_import',
    // Tandoor resolves plugin locale files as @/plugins/<basePath>/locales/<lang>.json
    basePath: 'ai_import',
    defaultLocale: Promise.resolve(en),
    localeFiles: import.meta.glob('./locales/*.json'),
    routes: [],
    // A page under Settings -> Space, rendered in the content column, plus a
    // sidebar entry that links to it.
    //
    // `settingsComponent` is NOT used: Tandoor renders that inside the sidebar
    // <v-list>, so a real settings page dropped into it swallowed the whole
    // navigation column and pushed the Space form off screen. Measured on the
    // live instance 2026-11-14 -- the screenshot was the evidence.
    settingRoutes: [
        {
            path: 'ai-import',
            component: AiImportSettings,
            name: 'AiImportSettings',
            meta: {title: 'Settings'},
        },
    ],
    navigationDrawer: [],
    bottomNavigation: [],
    userNavigation: [],
    settingsComponent: SettingsNavItem,
}
