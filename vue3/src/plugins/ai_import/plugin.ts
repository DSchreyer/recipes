import type {TandoorPlugin} from "@/types/Plugins.ts";
import AiImportSettings from "./AiImportSettings.vue";

/**
 * Frontend half of the ai_import plugin.
 *
 * Tandoor's Vue app globs `vue3/src/plugins/* /plugin.ts` and asks each plugin
 * for routes, navigation entries and a `settingsComponent`, which the settings
 * page renders under *Space*. This plugin only needs the last one: the import
 * lives in the existing import dialog, and its switches belong beside the
 * other space settings.
 */
export const plugin: TandoorPlugin = {
    name: 'ai_import',
    basePath: 'api/plugins/ai-import/',
    defaultLocale: 'en',
    localeFiles: {},
    routes: [],
    settingRoutes: [],
    navigationDrawer: [],
    bottomNavigation: [],
    userNavigation: [],
    settingsComponent: AiImportSettings,
}
