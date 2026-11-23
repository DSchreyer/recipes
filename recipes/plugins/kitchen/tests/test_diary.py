"""The diary bridge, HTTP mocked.

What is asserted here is the contract, not the code shape: no key means no
request; a good answer means one entry with the keys Sparky upserts on; a dead
diary means a warning and a saved cook log; the same cook twice means one row.
The Sparky side (route names, payload fields, the ``(user_id, source,
source_id)`` unique index) was read from the running container on 2026-11-23.
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest import mock

import pytest
import requests
from cookbook.models import CookLog
from cookbook.tests.factories import (
    CookLogFactory, RecipeFactory, SpaceFactory, UserFactory,
)
from django.utils import timezone
from django_scopes import scopes_disabled

from recipes.plugins.kitchen import diary

pytestmark = pytest.mark.django_db

PROVIDER_ID = '11111111-1111-1111-1111-111111111111'
PROVIDERS = [{'id': PROVIDER_ID, 'provider_type': 'tandoor', 'provider_name': 'Tandoor'}]

COOKED_AT = datetime(2026, 11, 23, 19, 15)
# 19:15 local: no meal type on a cook log, so the clock decides.
DINNER = 'dinner'


def response(status=200, body=None):
    """Enough of a ``requests.Response`` for ``diary._send``."""
    reply = mock.Mock()
    reply.status_code = status
    reply.content = b'{}' if body is not None else b''
    reply.text = '' if status < 400 else 'kaputt'
    reply.json.return_value = body
    return reply


def food(recipe_id, name, calories=320):
    """One item of ``GET /api/foods/tandoor/search`` -- the provider mapping."""
    return {
        'name': name,
        'provider_type': 'tandoor',
        'provider_external_id': str(recipe_id),
        'default_variant': {
            'serving_size': 1,
            'serving_unit': 'serving',
            'calories': calories,
            'protein': 12,
            'carbs': 40,
            'fat': 9,
        },
        'variants': [],
    }


def bridge(recipe_id, name, *, results=None, entry_status=201):
    """The three calls a successful push makes, in the order it makes them."""
    def fake(method, url, **kwargs):
        if url.endswith('/api/external-providers'):
            return response(200, PROVIDERS)
        if url.endswith('/api/foods/tandoor/search'):
            if results is not None:
                return response(200, results)
            return response(200, [food(recipe_id, name)])
        if url.endswith('/api/food-entries'):
            return response(entry_status, {'id': 'entry-1'})
        raise AssertionError(f'unexpected request {method} {url}')
    return fake


def posts(http):
    """The create-entry calls, out of everything else on the wire."""
    return [call for call in http.call_args_list
            if str(call.args[1] if call.args else call.kwargs.get('url')).endswith('/api/food-entries')]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv('SPARKY_FITNESS_API_KEY', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_URL', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_USERS', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_TANDOOR_PROVIDER_ID', raising=False)
    diary.reset_cache()
    yield
    diary.wait_for_pending(5)
    diary.reset_cache()


@pytest.fixture
def cook(db):
    with scopes_disabled():
        space = SpaceFactory.create(name='Kitchen')
        user = UserFactory.create(space=space, username='daniel')
        recipe = RecipeFactory.create(space=space, name='Kartoffelsuppe', steps__count=0, keywords=[])
        log = CookLogFactory.create(
            space=space, recipe=recipe, created_by=user,
            created_at=timezone.make_aware(COOKED_AT),
        )
    return log


# --------------------------------------------------------------------------
# inert
# --------------------------------------------------------------------------


def test_inert_without_key_builds_no_request(cook):
    with mock.patch.object(diary.requests, 'request') as http:
        assert diary.push_cook(cook) is None
    http.assert_not_called()


def test_inert_is_said_once_at_startup_not_per_cook(cook, caplog):
    caplog.set_level(logging.INFO, logger=diary.__name__)
    diary.startup_notice()
    diary.push_cook(cook)

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert 'inert' in messages[0]


def test_startup_notice_names_the_url_when_enabled(monkeypatch, caplog):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    monkeypatch.setenv('SPARKY_FITNESS_URL', 'http://diary.internal:3010/')
    caplog.set_level(logging.INFO, logger=diary.__name__)

    diary.startup_notice()

    assert 'http://diary.internal:3010' in caplog.records[0].getMessage()
    assert diary.config().url == 'http://diary.internal:3010'


# --------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------


def test_a_successful_push_sends_the_expected_requests(cook, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key-123')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        payload = diary.push_cook(cook)

    assert payload['source'] == 'tandoor'
    assert payload['source_id'] == f'cooklog:{cook.pk}'
    assert payload['food_name'] == 'Kartoffelsuppe'
    assert payload['meal_type'] == DINNER
    assert payload['entry_date'] == '2026-11-23'
    assert payload['calories'] == 320.0

    search = [call for call in http.call_args_list if 'tandoor/search' in call.args[1]]
    assert len(search) == 1
    assert search[0].kwargs['headers']['x-provider-id'] == PROVIDER_ID
    assert search[0].kwargs['params'] == {'query': 'Kartoffelsuppe'}

    sent = posts(http)
    assert len(sent) == 1
    assert sent[0].args[0] == 'POST'
    body = sent[0].kwargs['json']
    assert body['quantity'] == 1 and body['unit'] == 'serving'
    # A snapshot, not a library row: Sparky's provider food is not persisted.
    assert 'food_id' not in body and 'variant_id' not in body
    assert sent[0].kwargs['headers']['x-api-key'] == 'key-123'


def test_the_provider_id_is_looked_up_once_per_process(cook, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook)
        diary.push_cook(cook, force=True)

    providers = [call for call in http.call_args_list if 'external-providers' in call.args[1]]
    assert len(providers) == 1


def test_a_named_recipe_is_matched_by_id_not_by_name(cook, monkeypatch):
    """A lookalike in the search results must not become the entry."""
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    results = [food(999999, 'Kartoffelsuppe', calories=1), food(cook.recipe_id, 'Kartoffelsuppe')]
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, '', results=results)
    ) as http:
        diary.push_cook(cook)

    assert posts(http)[0].kwargs['json']['calories'] == 320.0


# --------------------------------------------------------------------------
# failures
# --------------------------------------------------------------------------


def test_a_dead_diary_does_not_propagate(cook, monkeypatch, caplog):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(diary.requests, 'request', side_effect=requests.ConnectionError('down')):
        assert diary.push_cook(cook) is None

    assert any('not pushed' in record.getMessage() for record in caplog.records)


def test_an_http_error_does_not_propagate(cook, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request',
        side_effect=lambda method, url, **kw: response(500),
    ):
        assert diary.push_cook(cook) is None


def test_a_recipe_sparky_cannot_resolve_is_skipped(cook, monkeypatch, caplog):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, '', results=[])
    ) as http:
        assert diary.push_cook(cook) is None

    assert posts(http) == []
    assert any('cannot resolve' in record.getMessage() for record in caplog.records)


def test_a_broken_json_answer_does_not_propagate(cook, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    broken = response(200, None)
    broken.content = b'<html>'
    broken.json.side_effect = ValueError('not json')
    with mock.patch.object(diary.requests, 'request', side_effect=lambda *a, **kw: broken):
        assert diary.push_cook(cook) is None


# --------------------------------------------------------------------------
# the signal
# --------------------------------------------------------------------------


def test_the_signal_is_registered_and_saves_survive(
    cook, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    """A save through the ORM reaches the diary, and a broken diary is silent."""
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=requests.Timeout('slow')
    ), django_capture_on_commit_callbacks(execute=True):
        cook.comment = 'nochmal'
        cook.save()
        diary.wait_for_pending()

    with scopes_disabled():
        assert CookLog.objects.filter(pk=cook.pk).exists()
    assert any('not pushed' in record.getMessage() for record in caplog.records)


def test_the_signal_pushes_what_the_view_saved(cook, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http, django_capture_on_commit_callbacks(execute=True):
        cook.comment = 'war gut'
        cook.save()
        diary.wait_for_pending()

    sent = posts(http)
    assert len(sent) == 1
    assert sent[0].kwargs['json']['source_id'] == f'cooklog:{cook.pk}'


# --------------------------------------------------------------------------
# idempotency
# --------------------------------------------------------------------------


def test_two_saves_push_once(cook, monkeypatch):
    """The second save of the same row costs no request at all."""
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook)
        cook.rating = 4
        diary.push_cook(cook)

    assert len(posts(http)) == 1


def test_every_save_carries_the_same_key_so_sparky_upserts(cook, monkeypatch):
    """Even with the in-process guard bypassed, the row key is what protects us.

    ``createFoodEntry`` in Sparky's ``models/foodEntry.ts`` runs
    ``ON CONFLICT (user_id, source, source_id) DO UPDATE``: two identical POSTs
    are one diary entry, not two.
    """
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook, force=True)
        diary.push_cook(cook, force=True)

    sent = posts(http)
    assert len(sent) == 2
    assert {call.kwargs['json']['source_id'] for call in sent} == {f'cooklog:{cook.pk}'}


def test_two_cooks_of_the_same_recipe_are_two_entries(cook, monkeypatch):
    """Same recipe, same day, different cook logs: two meals, two keys."""
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with scopes_disabled():
        second = CookLogFactory.create(
            space=cook.space, recipe=cook.recipe, created_by=cook.created_by,
            created_at=timezone.make_aware(datetime(2026, 11, 23, 12, 30)),
        )
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook)
        diary.push_cook(second)

    assert {call.kwargs['json']['source_id'] for call in posts(http)} == {
        f'cooklog:{cook.pk}', f'cooklog:{second.pk}',
    }


# --------------------------------------------------------------------------
# who ate it
# --------------------------------------------------------------------------


def test_a_mapped_user_gets_their_own_entry(cook, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    monkeypatch.setenv('SPARKY_FITNESS_USERS', 'daniel:aaaaaaaa-0000-0000-0000-000000000001')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook)

    assert posts(http)[0].kwargs['json']['user_id'] == 'aaaaaaaa-0000-0000-0000-000000000001'


def test_an_unmapped_user_falls_back_to_the_key_owner(cook, monkeypatch, caplog):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    monkeypatch.setenv('SPARKY_FITNESS_USERS', 'anna:bbbbbbbb-0000-0000-0000-000000000002')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(cook.recipe_id, 'Kartoffelsuppe')
    ) as http:
        diary.push_cook(cook)

    assert 'user_id' not in posts(http)[0].kwargs['json']
    assert any('no SparkyFitness user' in record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------
# meal buckets
# --------------------------------------------------------------------------


@pytest.mark.parametrize('name,expected', [
    ('Frühstück', 'breakfast'),
    ('Mittagessen', 'lunch'),
    ('Abendessen', 'dinner'),
    ('Snack am Nachmittag', 'snacks'),
    ('Kaffee und Kuchen', 'snacks'),
])
def test_a_planned_meal_type_is_translated_not_guessed(name, expected):
    when = timezone.make_aware(datetime(2026, 11, 23, 3, 0))
    assert diary.meal_for(name, when) == expected


@pytest.mark.parametrize('hour,expected', [
    (8, 'breakfast'), (12, 'lunch'), (19, 'dinner'), (22, 'snacks'),
])
def test_a_cook_log_uses_the_clock(hour, expected):
    when = timezone.make_aware(datetime(2026, 11, 23, hour, 0))
    assert diary.meal_for(None, when) == expected
