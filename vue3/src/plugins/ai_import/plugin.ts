import type {TandoorPlugin} from "@/types/Plugins.ts";
import AiImportSettings from "./AiImportSettings.vue";
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
    settingRoutes: [],
    navigationDrawer: [],
    bottomNavigation: [],
    userNavigation: [],
    settingsComponent: AiImportSettings,
}
