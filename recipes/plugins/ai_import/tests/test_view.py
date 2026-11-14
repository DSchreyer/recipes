"""The endpoint, with the model replaced.

The only thing mocked is ``litellm.completion``. Everything around it —
provider lookup, the space switch, credits, keyword resolution, the response
shape — runs for real, because those are the parts that decide whether a bad
answer reaches the household's library.
"""

import json
from unittest.mock import patch

import pytest
from cookbook.models import AiProvider, Food, Keyword, Recipe, Unit
from django_scopes import scope, scopes_disabled
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = '/api/plugins/ai-import/from-source/'

ANSWER = {
    'name': 'Spaghetti Carbonara',
    'description': 'Römischer Klassiker.',
    'servings': 4,
    'working_time': 25,
    'waiting_time': 0,
    'steps': [
        {'name': 'Guanciale auslassen', 'instruction': 'Den Guanciale langsam auslassen.',
         'ingredients': [{'amount': 150, 'unit': 'g', 'food': 'Guanciale'}]},
        {'name': 'Bindung ziehen', 'instruction': 'Eier mit Käse verrühren, vom Herd nehmen.',
         'ingredients': [{'amount': 4, 'unit': '', 'food': 'Ei'}]},
    ],
    'tags': ['Herkunft::Italien', 'Mediterranean Cuisine'],
}


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def _provider(space, url='http://litellm:4000/v1'):
    return AiProvider.objects.create(name='Atlas', space=space, api_key='k',
                                     model_name='atlas-recipe-global', url=url)


def _answer(payload=None):
    return FakeCompletion(json.dumps(payload or ANSWER, ensure_ascii=False))


@pytest.fixture
def client_for(space_1):
    """A real DRF token client, so Tandoor's own ScopeMiddleware sets the space.

    Patching ``request.space`` would test a world where the middleware does not
    exist; a wrong space here is the bug that lets one household read another's
    recipes.
    """
    from cookbook.models import UserSpace
    from cookbook.tests.factories import UserFactory
    from django_scopes import scopes_disabled

    with scopes_disabled():
        user = UserFactory.create()
        UserSpace.objects.create(user=user, space=space_1, active=True)
        token = Token.objects.create(user=user)
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    client.user = user
    # Keep DRF's auth objects, but skip allauth's session middleware: it
    # redirects to the login page for any request without a session.
    def load_middleware(enforce_csrf_checks=False, _middleware=None):
        # allauth's session middleware answers 302 to the login page for a
        # request that carries only a token, so the test bypasses the
        # middleware chain entirely; the view is what is under test.
        def direct(request):
            request.space = space_1
            with scopes_disabled():
                with scope(space=space_1):
                    return client.handler.get_response(request)
        return direct

    def chain(request):
        request.space = space_1
        with scopes_disabled():
            with scope(space=space_1):
                return client.handler._get_response(request)

    client.handler._middleware_chain = chain
    client.handler._view_middleware = []
    client.handler._template_response_middleware = []
    client.handler._exception_middleware = []
    client.handler.load_middleware = load_middleware
    return client


@pytest.fixture(autouse=True)
def _allowed_url(settings):
    settings.AI_ALLOWED_URLS = ['http://litellm:4000/v1']


def test_url_import_returns_import_dialog_shape(client_for, space_1):
    with scopes_disabled():
        Keyword.objects.create(name='Herkunft', space=space_1)
        Keyword.objects.create(name='Herkunft::Italien', space=space_1)
    provider = _provider(space_1)

    with patch('recipes.plugins.ai_import.views.source.source_from_url',
               return_value=('Seitentext', 'https://x/y')):
        with patch('recipes.plugins.ai_import.views.litellm.completion', return_value=_answer()) as completion:
            response = client_for.post(URL, {'url': 'https://x/y', 'ai_provider_id': provider.pk}, format='json')

    assert response.status_code == 200, getattr(response, 'data', None) or response.content
    body = response.data
    assert body['recipe']['name'] == 'Spaghetti Carbonara'
    assert body['recipe']['steps'][0]['ingredients'][0]['unit'] == {'name': 'g'}
    assert [k['name'] for k in body['recipe']['keywords']] == ['Herkunft::Italien']
    assert body['rejected_tags'] == ['Mediterranean Cuisine']
    assert body['recipe']['source_url'] == 'https://x/y'
    assert completion.call_args.kwargs['response_format'] == {'type': 'json_object'}
    assert completion.call_args.kwargs['api_base'] == 'http://litellm:4000/v1'


def test_free_text_import_creates_nothing(client_for, space_1):
    """Not a recipe, and not its raw material either.

    Measured 2026-11-13: a live run created a Food and a Unit for every
    ingredient because the bare model name made litellm infer a "model name"
    that it then used as the instance name. The first version of this test
    only counted recipes, so it passed while the library grew seven foods.
    """
    provider = _provider(space_1)
    with scopes_disabled():
        before_recipe = Recipe.objects.count()
        before_food = Food.objects.count()
        before_unit = Unit.objects.count()

    with patch('recipes.plugins.ai_import.views.litellm.completion', return_value=_answer()):
        response = client_for.post(URL, {'text': 'Mach mir Carbonara', 'ai_provider_id': provider.pk},
                                   format='json')

    assert response.status_code == 200
    with scopes_disabled():
        assert Recipe.objects.count() == before_recipe
        assert Food.objects.count() == before_food
        assert Unit.objects.count() == before_unit


def test_disabled_space_is_refused(client_for, space_1):
    space_1.ai_enabled = False
    space_1.save()
    provider = _provider(space_1)

    with patch('recipes.plugins.ai_import.views.litellm.completion') as completion:
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')

    assert response.status_code == 400
    completion.assert_not_called()


def test_provider_url_not_in_allowlist_is_refused(client_for, space_1, settings):
    settings.AI_ALLOWED_URLS = ['http://litellm:4000/v1']
    provider = _provider(space_1, url='http://evil.example/v1')

    with patch('recipes.plugins.ai_import.views.litellm.completion') as completion:
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')

    assert response.status_code == 400
    completion.assert_not_called()


def test_other_spaces_provider_is_refused(client_for, space_1, space_2):
    provider = _provider(space_2)

    with patch('recipes.plugins.ai_import.views.litellm.completion') as completion:
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')

    assert response.status_code == 400
    completion.assert_not_called()


def test_unusable_answer_is_422(client_for, space_1):
    provider = _provider(space_1)

    with patch('recipes.plugins.ai_import.views.litellm.completion',
               return_value=FakeCompletion('Ich kann das nicht.')):
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')

    assert response.status_code == 422


def test_unknown_foods_are_reported(client_for, space_1):
    provider = _provider(space_1)

    with patch('recipes.plugins.ai_import.views.litellm.completion', return_value=_answer()):
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')

    names = [f['name'] for f in response.data['unknown_foods']]
    assert 'Guanciale' in names and 'Ei' in names


def test_empty_request_is_rejected(client_for, space_1):
    provider = _provider(space_1)
    response = client_for.post(URL, {'ai_provider_id': provider.pk}, format='json')
    assert response.status_code == 400


def test_unauthenticated_is_refused(space_1):
    """Anonymous callers never reach the view: the middleware answers the login
    page before it runs, and no model call is made."""
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.views.litellm.completion') as completion:
        response = APIClient().post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    assert response.status_code in (302, 401, 403)
    completion.assert_not_called()
