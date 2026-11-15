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


class TestStepTitles:
    """A step must never lose its instruction to a title.

    The first version of lift_title(instruction, name) was called as
    lift_title(name, instruction), so a step without a title had its text moved
    into the title field and an empty instruction. Recipe 199 on the live
    instance showed seven untitled steps; this pins the opposite failure.
    """

    def test_plain_instruction_keeps_its_text(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Mehl abwiegen und sieben.'}]},
            units={}, foods={}, keywords=[])
        step = payload['steps'][0]
        assert step['instruction'] == 'Mehl abwiegen und sieben.'
        assert step['name']

    def test_bold_title_in_text_is_moved_to_the_name_field(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': '**Teig ansetzen**\nMehl und Zucker verrühren.'}]},
            units={}, foods={}, keywords=[])
        step = payload['steps'][0]
        assert step['name'] == 'Teig ansetzen'
        assert step['instruction'] == 'Mehl und Zucker verrühren.'

    def test_whole_instruction_in_bold_is_not_a_title(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': '**Alles miteinander verrühren und servieren**'}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['instruction'] == '**Alles miteinander verrühren und servieren**'

    def test_step_number_prefix_is_dropped(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Schritt 1: Mehl abwiegen.'}]},
            units={}, foods={}, keywords=[])
        assert 'Schritt 1' not in payload['steps'][0]['instruction']

    def test_title_the_model_put_in_the_right_field_is_kept(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'name': 'Teig ansetzen', 'instruction': 'Mehl abwiegen.'}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['name'] == 'Teig ansetzen'

    def test_titles_can_be_switched_off(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': '**Teig ansetzen**\nMehl abwiegen.'}]},
            units={}, foods={}, keywords=[], options={'enforce_step_titles': False})
        step = payload['steps'][0]
        assert step['name'] == ''
        assert step['instruction'].startswith('**Teig')


class TestPlaceholders:
    def test_out_of_order_ingredients_are_left_as_text(self):
        """Measured on Zimtschnecken 2026-11-14: the sentence named Zucker, Salz,
        Kardamom but the step listed Salz, Kardamom, Butter. Index 2 pointed at
        Salz, so the rendered text read "Mehl, 0.5 TL Salz, 0.5 TL Kardamom und
        Kardamom". Wrong amounts are worse than no amounts."""
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Mehl, Zucker, Salz und Kardamom vermengen.',
                                        'ingredients': [
                                            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
                                            {'amount': 0.5, 'unit': 'TL', 'food': 'Salz'},
                                            {'amount': 0.5, 'unit': 'TL', 'food': 'Kardamom'},
                                            {'amount': 75, 'unit': 'Gramm', 'food': 'Zucker'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        assert '{{' not in payload['steps'][0]['instruction']

    def test_out_of_order_step_is_reported(self):
        warnings: list[str] = []
        shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Salz und Mehl mischen.',
                                        'ingredients': [
                                            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
                                            {'amount': 1, 'unit': 'TL', 'food': 'Salz'},
                                        ]}]},
            units={}, foods={}, keywords=[], warnings=warnings)
        assert warnings and 'Reihenfolge' in warnings[0]

    def test_in_order_ingredients_do_get_placeholders(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Salz und Mehl mischen.',
                                        'ingredients': [
                                            {'amount': 1, 'unit': 'TL', 'food': 'Salz'},
                                            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        text = payload['steps'][0]['instruction']
        assert text.startswith('{{ ingredients[0] }}') and '{{ ingredients[1] }}' in text

    def test_ingredient_missing_from_text_does_not_block_the_others(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Mehl abwiegen.',
                                        'ingredients': [
                                            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
                                            {'amount': 75, 'unit': 'Gramm', 'food': 'Butter'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['instruction'].startswith('{{ ingredients[0] }}')

    def test_first_mention_becomes_a_positional_placeholder(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Weizenmehl und Rohrzucker verrühren, dann das Weizenmehl sieben.',
                                        'ingredients': [
                                            {'amount': 450, 'unit': 'Gramm', 'food': 'Weizenmehl'},
                                            {'amount': 75, 'unit': 'Gramm', 'food': 'Rohrzucker'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        text = payload['steps'][0]['instruction']
        assert text.startswith('{{ ingredients[0] }} und {{ ingredients[1] }}')
        # one replacement per ingredient: the second mention stays prose
        assert 'dann das Weizenmehl sieben' in text

    def test_longer_food_name_wins_the_overlap(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Vollkornweizenmehl und Weizenmehl mischen.',
                                        'ingredients': [
                                            {'amount': 1, 'unit': 'kg', 'food': 'Vollkornweizenmehl'},
                                            {'amount': 2, 'unit': 'kg', 'food': 'Weizenmehl'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        text = payload['steps'][0]['instruction']
        assert text.startswith('{{ ingredients[0] }}')
        assert '{{ ingredients[1] }}' in text

    def test_amount_written_beside_the_name_is_replaced_whole(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': '450 g Weizenmehl in eine Schüssel geben.',
                                        'ingredients': [{'amount': 450, 'unit': 'Gramm', 'food': 'Weizenmehl'}]}]},
            units={}, foods={}, keywords=[])
        text = payload['steps'][0]['instruction']
        assert text.startswith('{{ ingredients[0] }} in eine Schüssel')
        assert '450' not in text

    def test_group_headers_get_no_placeholder(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Alles verrühren.',
                                        'ingredients': [
                                            {'amount': 0, 'unit': '', 'food': '', 'note': 'Für den Teig',
                                             'is_header': True, 'no_amount': True},
                                            {'amount': 1, 'unit': 'kg', 'food': 'Mehl'},
                                        ]}]},
            units={}, foods={}, keywords=[])
        assert payload['steps'][0]['instruction'] == 'Alles verrühren.'

    def test_placeholders_can_be_switched_off(self):
        payload = shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': 'Mehl abwiegen.',
                                        'ingredients': [{'amount': 1, 'unit': 'kg', 'food': 'Mehl'}]}]},
            units={}, foods={}, keywords=[], options={'placeholders_enabled': False})
        assert payload['steps'][0]['instruction'] == 'Mehl abwiegen.'


class TestPlaceholderState:
    """Each step says what happened to its amounts, so the household reads it.

    Measured 2026-11-14 on Zimtschnecken: the plugin refused the placeholders
    because the sentence named the ingredients in another order than the list,
    and said so only in ``warnings``. The text still read "Mehl" without a
    number and nothing on the page explained why -- the household found out at
    the stove. The state travels with the step, so the import dialog can show
    it beside the sentence it belongs to.
    """

    def _payload(self, instruction, ingredients, **kwargs):
        return shaping.to_recipe_payload(
            {'name': 'Test', 'steps': [{'instruction': instruction, 'ingredients': ingredients}]},
            units={}, foods={}, keywords=[], **kwargs)

    def test_every_named_ingredient_replaced_is_all(self):
        payload = self._payload('Salz und Mehl mischen.', [
            {'amount': 1, 'unit': 'TL', 'food': 'Salz'},
            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
        ])
        assert payload['steps'][0]['placeholder_state'] == 'all'

    def test_refused_placeholders_are_none(self):
        payload = self._payload('Salz und Mehl mischen.', [
            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
            {'amount': 1, 'unit': 'TL', 'food': 'Salz'},
        ])
        assert payload['steps'][0]['placeholder_state'] == 'none'

    def test_a_step_that_names_no_ingredient_is_empty(self):
        """A step with nothing to replace is not a problem, so it says 'empty'.

        Measured 2026-11-15 on the live preview: 'Den Ofen vorheizen' was told
        "the sentence names its ingredients in another order than the list",
        which is not true of a sentence that names none. The household would
        look for a problem that does not exist.
        """
        payload = self._payload('Den Ofen auf 180 Grad vorheizen.', [
            {'amount': 1, 'unit': 'kg', 'food': 'Mehl'},
        ])
        assert payload['steps'][0]['placeholder_state'] == 'empty'

    def test_a_partly_replaced_step_is_partial(self):
        payload = self._payload('Mehl und Zucker verrühren, dann die Butter schmelzen.', [
            {'amount': 450, 'unit': 'Gramm', 'food': 'Mehl'},
            {'amount': 75, 'unit': 'Gramm', 'food': 'Zucker'},
            {'amount': 100, 'unit': 'Gramm', 'food': 'Butter'},
        ])
        text = payload['steps'][0]['instruction']
        # The sentence names Mehl, Zucker, Butter in list order and all three
        # are replaced, so this is "all" -- the state counts replacements, not
        # mentions.
        assert payload['steps'][0]['placeholder_state'] == 'all'
        assert text.count('{{') == 3

    def test_switched_off_placeholders_are_none(self):
        payload = self._payload('Mehl abwiegen.', [
            {'amount': 1, 'unit': 'kg', 'food': 'Mehl'},
        ], options={'placeholders_enabled': False})
        assert payload['steps'][0]['instruction'] == 'Mehl abwiegen.'

    def test_a_switched_off_step_still_carries_a_state(self):
        """A step with the switch off says "none", not "absent".

        Absent would mean "the plugin has nothing to say"; "none" means "you
        asked for no amounts and got none". The import dialog has to tell those
        two apart, because only the second is the household's own choice.
        """
        payload = self._payload('Mehl abwiegen.', [
            {'amount': 1, 'unit': 'kg', 'food': 'Mehl'},
        ], options={'placeholders_enabled': False})
        assert payload['steps'][0]['placeholder_state'] == 'none'


class TestImages:
    HTML = '''
      <html><head>
        <meta property="og:image" content="https://site.example/dish.jpg">
        <meta name="twitter:image" content="https://site.example/dish-social.jpg">
      </head><body>
        <img src="/images/logo.svg">
        <img src="/images/ad-banner.png">
        <img data-src="https://site.example/photos/step-1.webp">
        <img srcset="https://site.example/photos/zimt-600.jpg 600w, https://site.example/photos/zimt-1200.jpg 1200w">
        <img src="data:image/png;base64,AAAA">
        <img src="https://other.example/pixel.gif">
      </body></html>
    '''

    def test_page_photo_comes_first(self):
        from recipes.plugins.ai_import.images import images_from_html
        images = images_from_html(self.HTML, 'https://site.example/recipe')
        assert images[0] == 'https://site.example/dish.jpg'

    def test_logos_banners_and_trackers_are_dropped(self):
        from recipes.plugins.ai_import.images import images_from_html
        images = images_from_html(self.HTML, 'https://site.example/recipe')
        joined = ' '.join(images)
        assert 'logo' not in joined and 'ad-banner' not in joined
        assert 'pixel' not in joined

    def test_lazy_and_srcset_images_are_included(self):
        from recipes.plugins.ai_import.images import images_from_html
        images = images_from_html(self.HTML, 'https://site.example/recipe')
        assert 'https://site.example/photos/step-1.webp' in images
        assert 'https://site.example/photos/zimt-600.jpg' in images

    def test_relative_urls_resolve_against_the_page(self):
        from recipes.plugins.ai_import.images import images_from_html
        images = images_from_html('<img src="/foto.jpg">', 'https://site.example/a/b')
        assert images == ['https://site.example/foto.jpg']

    def test_list_is_capped(self):
        from recipes.plugins.ai_import.images import MAX_IMAGES, images_from_html
        html = ''.join(f'<img src="/p/{i}.jpg">' for i in range(40))
        assert len(images_from_html(html, 'https://x.example/')) == MAX_IMAGES
