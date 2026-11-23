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

    def ready(self):
        """Wire the cook log to the diary.

        Imported here rather than at module level: the loader mentioned above
        reads ``sorted(dir(module))[1]``, so a new top-level name is a startup
        risk. The signal covers both write paths -- the picker's form and
        upstream's ``POST /api/cook-log/`` -- without either of them knowing.
        """
        from cookbook.models import CookLog
        from django.db.models.signals import post_save

        from . import diary

        post_save.connect(
            diary.cook_logged,
            sender=CookLog,
            dispatch_uid='kitchen.diary.cook_log',
        )
        diary.startup_notice()
