from django.apps import AppConfig

# Tandoor's loader (recipes/settings.py) resolves the plugin's app class as
# ``dir(module)[1]`` -- the second name in the module, sorted. A bare
# ``AppConfig`` import therefore wins and Django is handed
# ``...apps.AppConfig``, which has no ``name``. The alias below sorts before
# ``AppConfig`` and is the class Tandoor actually loads.
class AiImportConfig(AppConfig):
    name = 'recipes.plugins.ai_import'
    verbose_name = 'AI Import'
    VERSION = '0.1.0'
    website = 'https://github.com/DSchreyer/recipes'
    github = 'DSchreyer/recipes'
    base_url = 'plugins/ai-import/'
    nav_main = ''
    nav_dropdown = ''
    api_router_name = ''


# Name that sorts before ``AppConfig`` so Tandoor's ``dir(module)[1]`` picks
# the config class and not the imported base class.
AAiImportConfig = AiImportConfig
