"""The preview endpoint proves a prompt without touching the library.

Its job is the one the settings field cannot do: show what a prompt actually
produces. So the assertions are about output shape and about nothing being
written -- not about the model's wording.
"""

import json
from unittest.mock import patch

import pytest
from cookbook.models import AiProvider, Food, Recipe, Unit
from django_scopes import scope, scopes_disabled
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = '/api/plugins/ai-import/preview/'

ANSWER = {
    'name': 'Zimtschnecken',
    'steps': [
        {'name': '', 'instruction': '**Teig ansetzen**\nWeizenmehl abwiegen.',
         'ingredients': [{'amount': 450, 'unit': 'Gramm', 'food': 'Weizenmehl'}]},
        {'name': '', 'instruction': 'Butter schmelzen.',
         'ingredients': [{'amount': 75, 'unit': 'Gramm', 'food': 'Butter'}]},
    ],
    'tags': [],
}


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Completion:
    def __init__(self, content=None):
        self.choices = [_Choice(json.dumps(content or ANSWER, ensure_ascii=False))]


@pytest.fixture
def client_for(space_1):
    from cookbook.models import UserSpace
    from cookbook.tests.factories import UserFactory

    with scopes_disabled():
        user = UserFactory.create()
        UserSpace.objects.create(user=user, space=space_1, active=True)
        token = Token.objects.create(user=user)

    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def chain(request):
        request.space = space_1
        with scopes_disabled():
            with scope(space=space_1):
                return client.handler._get_response(request)

    client.handler._middleware_chain = chain
    client.handler._view_middleware = []
    client.handler._template_response_middleware = []
    client.handler._exception_middleware = []
    client.handler.load_middleware = lambda *a, **k: None
    client.user = user
    return client


@pytest.fixture(autouse=True)
def _allowed_url(settings):
    settings.AI_ALLOWED_URLS = ['http://litellm:4000/v1']


def _provider(space):
    return AiProvider.objects.create(name='Atlas', space=space, api_key='k',
                                     model_name='atlas-recipe-global',
                                     url='http://litellm:4000/v1')


def test_preview_returns_steps(client_for, space_1):
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion', return_value=_Completion()):
        response = client_for.post(URL, {'text': 'Zimtschnecken', 'ai_provider_id': provider.pk},
                                   format='json')
    assert response.status_code == 200, response.data
    steps = response.data['recipe']['steps']
    assert len(steps) == 2
    assert steps[0]['name'] == 'Teig ansetzen'


def test_preview_writes_nothing(client_for, space_1):
    provider = _provider(space_1)
    with scopes_disabled():
        before = (Recipe.objects.count(), Food.objects.count(), Unit.objects.count())
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion', return_value=_Completion()):
        client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    with scopes_disabled():
        after = (Recipe.objects.count(), Food.objects.count(), Unit.objects.count())
    assert after == before


def test_preview_uses_the_draft_prompt_not_the_saved_one(client_for, space_1):
    from recipes.plugins.ai_import.models import AiImportSettings
    AiImportSettings.objects.create(space=space_1, custom_prompt='GESPEICHERT')
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion', return_value=_Completion()) as completion:
        client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk,
                              'custom_prompt': 'ENTWURF'}, format='json')
    prompt = completion.call_args.kwargs['messages'][1]['content']
    assert 'ENTWURF' in prompt
    assert 'GESPEICHERT' not in prompt


def test_preview_falls_back_to_the_saved_prompt(client_for, space_1):
    from recipes.plugins.ai_import.models import AiImportSettings
    AiImportSettings.objects.create(space=space_1, custom_prompt='GESPEICHERT')
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion', return_value=_Completion()) as completion:
        client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    assert 'GESPEICHERT' in completion.call_args.kwargs['messages'][1]['content']


def test_preview_reports_unknown_foods(client_for, space_1):
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion', return_value=_Completion()):
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    # the test space has no foods at all, so both ingredients are unknown
    assert response.data['counts']['unknown_foods'] == 2


def test_preview_refuses_a_disabled_space(client_for, space_1):
    space_1.ai_enabled = False
    space_1.save()
    provider = _provider(space_1)
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion') as completion:
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    assert response.status_code == 400
    completion.assert_not_called()


def test_preview_refuses_a_foreign_provider_url(client_for, space_1, settings):
    settings.AI_ALLOWED_URLS = ['http://litellm:4000/v1']
    provider = _provider(space_1)
    provider.url = 'http://evil.example/v1'
    provider.save()
    with patch('recipes.plugins.ai_import.preview_views.litellm.completion') as completion:
        response = client_for.post(URL, {'text': 'x', 'ai_provider_id': provider.pk}, format='json')
    assert response.status_code == 400
    completion.assert_not_called()


def test_preview_needs_a_source(client_for, space_1):
    provider = _provider(space_1)
    response = client_for.post(URL, {'ai_provider_id': provider.pk}, format='json')
    assert response.status_code == 400
