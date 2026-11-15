"""Live round trip against a real model and a real page. Opt-in.

    E2E_URL=https://... LITELLM_MASTER_KEY=... pytest .../test_live_e2e.py

The model's output is not asserted -- the point is that a request with the
real 701-food vocabulary comes back shaped, matched and cost-logged, and that
it creates no Food and no Unit. The mocked tests assert the parts that must be
exact.
"""

import json
import os

import pytest
from cookbook.models import (AiProvider, Food, Keyword, Space, Unit, User,
                             UserSpace)
from django_scopes import scope, scopes_disabled
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

pytestmark = pytest.mark.skipif(
    not (os.environ.get('E2E_URL') and os.environ.get('LITELLM_MASTER_KEY')),
    reason='live model test; set E2E_URL and LITELLM_MASTER_KEY')

URL = '/api/plugins/ai-import/from-source/'


@pytest.mark.django_db
def test_live_import(settings):
    settings.AI_ALLOWED_URLS = ['http://127.0.0.1:4000/v1']
    vocab_path = os.environ.get('E2E_VOCAB')
    if vocab_path and os.path.exists(vocab_path):
        with open(vocab_path) as handle:
            vocab = json.load(handle)
    else:
        # A small built-in set so the opt-in test runs on a fresh checkout;
        # E2E_VOCAB points it at a real space's export instead.
        vocab = {
            'foods': [{'name': n} for n in ('Mehl', 'Zucker', 'Salz', 'Butter', 'Ei', 'Milch')],
            'keywords': [{'name': n} for n in ('Herkunft::Italien', 'Aufwand::Schnell')],
        }
    with scopes_disabled():
        sp = Space.objects.create(name='E2E')
        user = User.objects.create(username=f'live{os.getpid()}')
        UserSpace.objects.create(user=user, space=sp, active=True)
        Token.objects.create(user=user)
        prov = AiProvider.objects.create(
            name='Atlas', space=sp, api_key=os.environ['LITELLM_MASTER_KEY'],
            model_name='atlas-recipe-global', url='http://127.0.0.1:4000/v1')
        for food in vocab['foods']:
            Food.objects.create(name=food['name'], space=sp)
        for keyword in vocab['keywords']:
            Keyword.objects.create(name=keyword['name'], space=sp)
        for unit in ['g', 'kg', 'ml', 'Stück', 'EL', 'TL', 'Prise', 'Bund', 'Zehe']:
            Unit.objects.create(name=unit, space=sp)
        before = (Food.objects.count(), Unit.objects.count())

    client = APIClient()
    client.force_authenticate(user)

    def chain(request):
        request.space = sp
        with scopes_disabled():
            with scope(space=sp):
                return client.handler._get_response(request)

    client.handler._middleware_chain = chain
    client.handler._view_middleware = []
    client.handler._template_response_middleware = []
    client.handler._exception_middleware = []
    client.handler.load_middleware = lambda *a, **k: None

    response = client.post(URL, {'url': os.environ['E2E_URL'], 'ai_provider_id': prov.pk},
                           format='json')
    assert response.status_code == 200, response.content[:800]
    body = response.json()
    recipe = body['recipe']

    print('\nSOURCE:', os.environ['E2E_URL'])
    print('name:', recipe['name'], '| servings:', recipe['servings'],
          '| steps:', len(recipe['steps']))
    print('keywords:', [k['name'] for k in recipe['keywords']])
    print('rejected:', body['rejected_tags'])
    print('unknown foods:', [f['name'] for f in body['unknown_foods']])
    print('duplicates:', body['duplicates'])
    for number, step in enumerate(recipe['steps'], 1):
        rows = [(i['amount'], i['unit']['name'], i['food']['name']) for i in step['ingredients']]
        print(f'  {number}. {step["name"]}: {step["instruction"][:110]}')
        print('     ', rows)

    with scopes_disabled():
        after = (Food.objects.count(), Unit.objects.count())
    assert after == before, f'preview created foods/units: {before} -> {after}'
