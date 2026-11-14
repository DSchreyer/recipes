"""What the plugin promises, pinned.

Each test names a failure that already happened once in Atlas's library or is
implied by Tandoor's importer contract: a model answer in HTML, a step with no
``unit`` (silently dropped), a keyword invented next to an existing one, a
page that is not http(s), an answer with no steps.
"""

import pytest

from recipes.plugins.ai_import import prompt, shaping, source
from recipes.plugins.ai_import.vocabulary import (food_key, sanitize_instruction,
                                                  sanitize_title)

pytestmark = pytest.mark.django_db


class TestShaping:
    def test_fenced_json_is_read(self):
        answer = 'Hier das Rezept:\n```json\n{"name": "Test"}\n```\nViel Erfolg!'
        assert shaping.parse_model_answer(answer) == {'name': 'Test'}

    def test_prose_around_json_is_read(self):
        answer = 'Sicher! {"name": "Test", "steps": []} Das war es.'
        assert shaping.parse_model_answer(answer)['name'] == 'Test'

    def test_no_json_raises(self):
        with pytest.raises(shaping.ShapeError):
            shaping.parse_model_answer('Ich kann das leider nicht.')

    def test_recipe_without_steps_raises(self):
        with pytest.raises(shaping.ShapeError):
            shaping.to_recipe_payload({'name': 'Test', 'steps': []}, units={}, foods={}, keywords=[])

    def test_recipe_without_name_raises(self):
        with pytest.raises(shaping.ShapeError):
            shaping.to_recipe_payload({'name': '  ', 'steps': [{'instruction': 'x'}]},
                                      units={}, foods={}, keywords=[])

    def test_ingredient_always_carries_a_unit(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Kochen', 'ingredients': [
                {'amount': 2, 'unit': '', 'food': 'Ei'}]}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['ingredients'][0]['unit'] == {'name': ''}

    def test_ingredient_uses_existing_food_spelling(self):
        class Food:
            name = 'Ei'

        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Kochen', 'ingredients': [
                {'amount': 2, 'unit': '', 'food': 'Eier'}]}]},
            units={}, foods={food_key('Ei'): Food()}, keywords=[])
        assert payload['steps'][0]['ingredients'][0]['food'] == {'name': 'Ei'}

    def test_html_in_instruction_is_stripped(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': '<p>Kochen</p><b>und</b> essen'}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['instruction'] == 'Kochenund essen'

    def test_group_header_keeps_its_note_and_no_amount(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Kochen', 'ingredients': [
                {'amount': 0, 'unit': '', 'food': '', 'note': 'Für die Sauce',
                 'is_header': True, 'no_amount': True}]}]},
            units={}, foods={}, keywords=[])
        row = payload['steps'][0]['ingredients'][0]
        assert row['is_header'] is True and row['no_amount'] is True
        assert row['note'] == 'Für die Sauce'

    def test_amount_written_as_text_becomes_a_number(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Kochen', 'ingredients': [
                {'amount': '1,5', 'unit': 'l', 'food': 'Wasser'}]}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['ingredients'][0]['amount'] == 1.5


class TestSanitize:
    def test_instruction_length_is_capped(self):
        assert len(sanitize_instruction('x' * 9000)) == 4000

    def test_title_length_is_capped(self):
        assert len(sanitize_title('y' * 400)) == 120


class TestVocabulary:
    def test_keyword_from_another_space_is_not_accepted(self, space_1, space_2):
        from cookbook.models import Keyword
        from django_scopes import scopes_disabled
        from recipes.plugins.ai_import.vocabulary import resolve_keywords

        with scopes_disabled():
            Keyword.objects.create(name='Herkunft::Italien', space=space_2)
        accepted, rejected = resolve_keywords(space_1, ['Herkunft::Italien'])
        assert accepted == []
        assert rejected == ['Herkunft::Italien']

    def test_leaf_name_resolves_to_axis_keyword(self, space_1):
        from cookbook.models import Keyword
        from django_scopes import scopes_disabled
        from recipes.plugins.ai_import.vocabulary import resolve_keywords

        with scopes_disabled():
            Keyword.objects.create(name='Herkunft', space=space_1)
            Keyword.objects.create(name='Herkunft::Italien', space=space_1)
        accepted, rejected = resolve_keywords(space_1, ['Italien'])
        assert [k.name for k in accepted] == ['Herkunft::Italien']
        assert rejected == []

    def test_invented_tag_is_rejected(self, space_1):
        from recipes.plugins.ai_import.vocabulary import resolve_keywords

        accepted, rejected = resolve_keywords(space_1, ['Mediterranean Cuisine'])
        assert accepted == []
        assert rejected == ['Mediterranean Cuisine']

    def test_unknown_food_is_reported_not_created(self, space_1):
        from recipes.plugins.ai_import.vocabulary import food_suggestions

        assert food_suggestions(space_1, ['Zutat die es nicht gibt']) == [
            {'name': 'Zutat die es nicht gibt', 'folded': 'zutat die es nicht gibt'}]

    def test_plural_of_an_existing_food_is_not_a_new_food(self, space_1):
        from cookbook.models import Food
        from django_scopes import scopes_disabled
        from recipes.plugins.ai_import.vocabulary import food_suggestions

        with scopes_disabled():
            Food.objects.create(name='Ei', space=space_1)
        assert food_suggestions(space_1, ['Eier']) == []


class TestSource:
    def test_file_url_is_refused(self):
        with pytest.raises(source.FetchError):
            source.fetch_html('file:///etc/passwd')

    def test_ftp_url_is_refused(self):
        with pytest.raises(source.FetchError):
            source.fetch_html('ftp://example.org/x')

    def test_navigation_and_scripts_are_dropped(self):
        html = ('<html><head><title>Gericht</title><style>b{}</style></head>'
                '<body><nav>Menü</nav><h1>Gericht</h1><p>200 g Mehl</p>'
                '<script>alert(1)</script><footer>Impressum</footer></body></html>')
        text = source.html_to_text(html)
        assert 'Gericht' in text and '200 g Mehl' in text
        assert 'Menü' not in text and 'Impressum' not in text and 'alert' not in text

    def test_text_is_capped(self):
        assert len(source.source_from_text('x' * 99999)) == source.MAX_SOURCE_CHARS


class TestPrompt:
    def test_prompt_carries_the_vocabulary(self):
        messages = prompt.build_messages('Quelle', source_kind='text', known_foods=['Ei'],
                                         known_units=['g'], known_tags=['Herkunft::Italien'])
        user = messages[1]['content']
        assert 'Ei' in user and 'Herkunft::Italien' in user and 'Quelle' in user

    def test_prompt_forbids_amounts_in_instruction_text(self):
        assert 'Mengen im Fließtext sind verboten' in prompt.build_messages(
            'x', source_kind='text', known_foods=[], known_units=[], known_tags=[])[1]['content']


class TestCompletionModel:
    def test_bare_alias_gets_the_openai_protocol(self):
        from recipes.plugins.ai_import.views import completion_model

        assert completion_model('atlas-recipe-global') == 'openai/atlas-recipe-global'
        assert completion_model('llama3:8b') == 'openai/llama3:8b'

    def test_qualified_model_name_is_left_alone(self):
        from recipes.plugins.ai_import.views import completion_model

        assert completion_model('openrouter/deepseek/deepseek-v4.1') == 'openrouter/deepseek/deepseek-v4.1'


class TestMountPoint:
    def test_plugin_is_mounted_under_api(self):
        """A plugin path outside /api/ is redirected to login before it runs.

        Tandoor's ScopeMiddleware only authenticates X-Session-Token and OAuth
        bearers for ``/api/``. Measured live 2026-11-14: at /plugins/ the
        endpoint answered 302 for a valid token while /api/ai-step-sort/
        next to it answered 400.
        """
        from recipes.plugins.ai_import.apps import AiImportConfig
        from recipes.plugins.ai_import.tests.test_view import URL

        assert AiImportConfig.base_url.startswith('api/')
        assert URL.startswith('/api/plugins/ai-import/')
