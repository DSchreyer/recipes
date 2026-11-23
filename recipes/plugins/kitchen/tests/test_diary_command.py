"""``manage.py diary-push`` -- the plan half of the bridge.

The command shares the transport with the cook log, so these tests are about
what it walks and what it refuses to do: one entry per planned recipe, nothing
on ``--dry-run``, nothing at all without a key.
"""

from __future__ import annotations

from datetime import datetime
from unittest import mock

import pytest
from cookbook.tests.factories import (
    MealPlanFactory, MealTypeFactory, RecipeFactory, SpaceFactory, UserFactory,
)
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django_scopes import scopes_disabled

from recipes.plugins.kitchen import diary

from .test_diary import bridge, posts

pytestmark = pytest.mark.django_db

DAY = datetime(2026, 11, 23, 12, 30)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv('SPARKY_FITNESS_API_KEY', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_URL', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_USERS', raising=False)
    monkeypatch.delenv('SPARKY_FITNESS_TANDOOR_PROVIDER_ID', raising=False)
    diary.reset_cache()
    yield
    diary.reset_cache()


@pytest.fixture
def plan(db):
    with scopes_disabled():
        space = SpaceFactory.create(name='Kitchen')
        user = UserFactory.create(space=space, username='anna')
        meal_type = MealTypeFactory.create(space=space, name='Mittagessen', created_by=user)
        recipe = RecipeFactory.create(space=space, name='Linsensuppe', steps__count=0, keywords=[])
        return MealPlanFactory.create(
            space=space, recipe=recipe, created_by=user, meal_type=meal_type,
            title='',   # get_label() falls back to the recipe name
            from_date=timezone.make_aware(DAY),
            to_date=timezone.make_aware(datetime(2026, 11, 23, 13, 30)),
        )


def test_a_planned_meal_becomes_one_entry(plan, monkeypatch, capsys):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-23')

    sent = posts(http)
    assert len(sent) == 1
    body = sent[0].kwargs['json']
    assert body['source_id'] == f'mealplan:{plan.pk}'
    assert body['meal_type'] == 'lunch'      # "Mittagessen", translated
    assert body['entry_date'] == '2026-11-23'
    assert 'Linsensuppe' in capsys.readouterr().out


def test_dry_run_writes_nothing(plan, monkeypatch, capsys):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-23', dry_run=True)

    assert posts(http) == []
    out = capsys.readouterr().out
    assert f'mealplan:{plan.pk}' in out
    assert 'would push 1 of 1' in out


def test_without_a_key_the_command_sends_nothing(plan, monkeypatch, capsys):
    with mock.patch.object(diary.requests, 'request') as http:
        call_command('diary-push', date='2026-11-23')

    http.assert_not_called()
    assert 'inert' in capsys.readouterr().out


def test_another_day_is_left_alone(plan, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-24')

    http.assert_not_called()


def test_a_title_only_plan_is_skipped(plan, monkeypatch, caplog):
    """A plan with no recipe has no calories to resolve -- and no guessing."""
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with scopes_disabled():
        MealPlanFactory.create(
            space=plan.space, recipe=None, title='Reste', created_by=plan.created_by,
            meal_type=plan.meal_type,
            from_date=timezone.make_aware(datetime(2026, 11, 23, 18, 30)),
            to_date=timezone.make_aware(datetime(2026, 11, 23, 19, 30)),
        )
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-23')

    assert len(posts(http)) == 1
    assert any('has no recipe' in record.getMessage() for record in caplog.records)


def test_two_plans_on_one_day_get_two_entries(plan, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with scopes_disabled():
        MealPlanFactory.create(
            space=plan.space, recipe=plan.recipe, created_by=plan.created_by,
            meal_type=plan.meal_type,
            from_date=timezone.make_aware(datetime(2026, 11, 23, 18, 30)),
            to_date=timezone.make_aware(datetime(2026, 11, 23, 19, 30)),
        )
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-23')

    assert len(posts(http)) == 2
    assert len({call.kwargs['json']['source_id'] for call in posts(http)}) == 2


def test_a_bad_date_is_a_command_error(monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with pytest.raises(CommandError):
        call_command('diary-push', date='23.11.2026')


def test_an_unknown_user_is_a_command_error(plan, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    with pytest.raises(CommandError):
        call_command('diary-push', date='2026-11-23', user='niemand')


def test_the_user_flag_moves_the_entry_to_that_diary(plan, monkeypatch):
    monkeypatch.setenv('SPARKY_FITNESS_API_KEY', 'key')
    monkeypatch.setenv('SPARKY_FITNESS_USERS', 'anna:cccccccc-0000-0000-0000-000000000003')
    with mock.patch.object(
        diary.requests, 'request', side_effect=bridge(plan.recipe_id, 'Linsensuppe')
    ) as http:
        call_command('diary-push', date='2026-11-23', user='anna')

    assert posts(http)[0].kwargs['json']['user_id'] == 'cccccccc-0000-0000-0000-000000000003'
