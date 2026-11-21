from django.apps import AppConfig


# Tandoor's loader (recipes/settings.py) resolves the plugin's app class as
# ``dir(module)[1]`` -- the second name in the module, sorted. Importing only
# ``AppConfig`` puts it at index 0 and this class at index 1, which is what the
# loader wants. ``ai_import`` needed an extra alias because a second import
# landed between them; do not add another top-level import here without
# re-checking ``sorted(dir(module))[1]``.
class KitchenConfig(AppConfig):
    name = 'recipes.plugins.kitchen'
    verbose_name = 'Kitchen Picker'
    VERSION = '0.1.0'
    website = ''
    github = ''
    # Under /api/: that is the path measured to work past Tandoor's
    # ScopeMiddleware, which authenticates an X-Session-Token only below /api/.
    # It reads oddly for a page, but a browser with a session is served the same
    # way, and a bookmark keeps the URL out of sight.
    base_url = 'api/plugins/kitchen/'
    nav_main = ''
    nav_dropdown = ''
    api_router_name = ''
