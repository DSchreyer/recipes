"""The page through Tandoor's own middleware.

The client is a real session, not a patched ``request.space``: the middleware is
what decides which space a query sees, and a bug there is the one that lets one
household read another's recipes.
"""

from __future__ import annotations

from datetime import date

import pytest
from cookbook.models import CookLog, UserSpace
from cookbook.tests.factories import (
    CookLogFactory, FoodFactory, IngredientFactory, KeywordFactory, RecipeFactory,
    SpaceFactory, StepFactory, UserFactory,
)
from django.test import Client
from django.utils import timezone
from django.urls import reverse
from django_scopes import scopes_disabled
from recipes.plugins.kitchen import views

pytestmark = pytest.mark.django_db
URL = '/api/plugins/kitchen/'
HISTORY = '/api/plugins/kitchen/gekocht/'

# 2026-11-24 is a Tuesday, 2026-11-28 a Saturday.
TUESDAY = date(2026, 11, 24)
SATURDAY = date(2026, 11, 28)


@pytest.fixture(autouse=True)
def _a_saturday(monkeypatch):
    """These tests are about ranking, not about the calendar.

    The weekday default would otherwise decide what a bare picker shows
    depending on the day the suite runs. Tests that care set their own day and
    win, because they patch the same function afterwards.
    """
    monkeypatch.setattr(views, '_today', lambda: SATURDAY)


def _cooked(space, recipe, rating=None, times=1):
    with scopes_disabled():
        user = UserFactory.create()
        UserSpace.objects.create(user=user, space=space, active=True)
        for _ in range(times):
            CookLogFactory.create(recipe=recipe, created_by=user, rating=rating, space=space)
    return recipe


def _proven(space, name, rating=5, times=1):
    return _cooked(space, _kitchen(space, name), rating=rating, times=times)


def _kitchen(space, name, keywords=(), foods=()):
    with scopes_disabled():
        recipe = RecipeFactory.create(space=space, name=name, keywords=[], steps__count=0)
        for keyword_name in keywords:
            recipe.keywords.add(KeywordFactory.create(space=space, name=keyword_name))
        step = StepFactory.create(space=space, ingredients__count=0)
        recipe.steps.add(step)
        for food_name in foods:
            food = FoodFactory.create(space=space, name=food_name)
            step.ingredients.add(IngredientFactory.create(space=space, food=food))
        return recipe


@pytest.fixture
def kitchen(db):
    with scopes_disabled():
        space = SpaceFactory.create(name='Kitchen')
        user = UserFactory.create()
        UserSpace.objects.create(user=user, space=space, active=True)
        client = Client()
        client.force_login(user)
    return client, space


def test_picker_page_renders(kitchen):
    client, space = kitchen
    _kitchen(space, 'Kartoffelsuppe', ['Beilage::Kartoffel'])

    response = client.get(URL)

    assert response.status_code == 200
    body = response.content.decode()
    assert 'Was koche ich?' in body
    assert 'Beilage' in body
    assert 'Kartoffelsuppe' in body


def test_two_axes_filter_and_a_dead_pair_explains_itself(kitchen):
    client, space = kitchen
    _kitchen(space, 'Reis mit Hähnchen', ['Beilage::Reis', 'Hauptzutat::Hähnchen'])
    _kitchen(space, 'Reis mit Fisch', ['Beilage::Reis', 'Hauptzutat::Fisch'])

    response = client.get(URL, {'carb': 'Beilage::Reis', 'protein': 'Hauptzutat::Hähnchen'})
    assert 'Reis mit Hähnchen' in response.content.decode()
    assert 'Reis mit Fisch' not in response.content.decode()

    dead = client.get(URL, {'carb': 'Beilage::Kartoffel', 'protein': 'Hauptzutat::Fisch'})
    assert 'Ohne' in dead.content.decode()


def test_card_names_what_is_missing_and_ignores_staples(kitchen):
    client, space = kitchen
    _kitchen(space, 'Kokoscurry', foods=['Reis', 'Kokosmilch', 'Salz', 'Öl'])

    body = client.get(URL, {'foods': 'Reis'}).content.decode()
    missing_lines = [line for line in body.splitlines() if 'ingredient-tag--miss' in line]

    assert any('Kokosmilch' in line for line in missing_lines)
    assert not any('Salz' in line or 'Öl' in line for line in missing_lines)


def test_recipe_without_photo_gets_a_placeholder(kitchen):
    client, space = kitchen
    _kitchen(space, 'Ohne Foto', foods=['Reis'])

    assert 'card-placeholder' in client.get(URL).content.decode()


def test_ingredient_less_page_is_not_a_food_match(kitchen):
    client, space = kitchen
    _kitchen(space, 'Nachschlagewerk')
    _kitchen(space, 'Kokoscurry', foods=['Kokosmilch'])

    body = client.get(URL, {'foods': 'Kokosmilch'}).content.decode()

    assert 'Kokoscurry' in body
    assert 'Nachschlagewerk' not in body


def test_recipe_using_none_of_my_food_is_not_shown(kitchen):
    client, space = kitchen
    _kitchen(space, 'Cacio e Pepe', foods=['Pecorino Romano', 'Spaghetti'])
    _kitchen(space, 'Kokoscurry', foods=['Kokosmilch', 'Reis'])

    body = client.get(URL, {'foods': 'Kokosmilch'}).content.decode()

    assert 'Kokoscurry' in body
    assert 'Cacio e Pepe' not in body


def test_another_spaces_recipe_never_appears(kitchen):
    client, space = kitchen
    with scopes_disabled():
        other = SpaceFactory.create(name='Other')
        RecipeFactory.create(space=other, name='Fremdes Rezept', keywords=[], steps__count=1)

    assert 'Fremdes Rezept' not in client.get(URL).content.decode()


def test_chip_link_toggles_and_keeps_the_rest(kitchen):
    client, space = kitchen
    _kitchen(space, 'Reisgericht', ['Beilage::Reis'])

    body = client.get(URL, {'carb': 'Beilage::Reis', 'foods': 'Reis'}).content.decode()

    assert 'protein=Hauptzutat%3A%3A' not in body  # no invented parameter
    assert 'foods=Reis' in body


def test_unknown_keyword_value_renders_instead_of_crashing(kitchen):
    client, space = kitchen
    _kitchen(space, 'Irgendwas', ['Beilage::Reis'])

    response = client.get(URL, {'carb': 'Beilage::GibtEsNicht'})

    assert response.status_code == 200
    assert 'Ohne' in response.content.decode()


# --- logging a cook ----------------------------------------------------------

def test_a_star_creates_a_dated_cook_log(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    response = client.post(URL, {
        'recipe': dish.id,
        'rating': '4',
        'note': 'mehr Muskat',
        'date': '2026-11-20',
        'next': '/api/plugins/kitchen/?carb=Beilage::Kartoffel',
    })

    assert response.status_code == 302
    assert response['Location'].endswith('geloggt=1')
    with scopes_disabled():
        log = CookLog.objects.get()
    assert log.recipe_id == dish.id
    assert log.rating == 4
    assert log.comment == 'mehr Muskat'
    assert log.created_at.date().isoformat() == '2026-11-20'


def test_cooked_without_stars_still_records_the_day(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    client.post(URL, {'recipe': dish.id, 'rating': '', 'date': '2026-11-20'})

    with scopes_disabled():
        log = CookLog.objects.get()
    assert log.rating is None
    assert log.comment is None


def test_a_recipe_from_another_space_writes_nothing(kitchen):
    client, space = kitchen
    with scopes_disabled():
        other = SpaceFactory.create(name='Other')
        foreign = RecipeFactory.create(space=other, name='Fremd', steps__count=0)

    response = client.post(URL, {'recipe': foreign.id, 'rating': '5'})

    assert response.status_code == 302
    with scopes_disabled():
        assert CookLog.objects.count() == 0


def test_next_cannot_leave_the_site(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    response = client.post(URL, {'recipe': dish.id, 'rating': '5', 'next': 'https://evil.example/x'})

    assert response['Location'].startswith('/api/plugins/kitchen/')


# --- the weekday default ------------------------------------------------------

def test_bare_picker_on_a_weekday_opens_on_proven(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    for name in ('Eintopf', 'Auflauf', 'Suppe', 'Salat'):
        _proven(space, name)
    _kitchen(space, 'Neuland')

    body = client.get(URL).content.decode()

    assert 'Eintopf' in body
    assert 'Neuland' not in body
    # Visible and reversible: the toggle is on, and its link turns it off.
    assert 'href="?minrating=0"' in body
    assert 'Montag bis Donnerstag' in body
    # Re-roll, more cards and the chips keep the default instead of dropping it.
    assert 'minrating=4' in body


def test_the_weekday_default_is_off_from_friday_to_sunday(kitchen, monkeypatch):
    client, space = kitchen
    for name in ('Eintopf', 'Auflauf', 'Suppe', 'Salat'):
        _proven(space, name)
    _kitchen(space, 'Neuland')

    body = client.get(URL).content.decode()  # the fixture's Saturday

    assert 'Neuland' in body
    assert 'minrating=0' not in body


def test_minrating_zero_switches_the_default_off_in_one_click(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    for name in ('Eintopf', 'Auflauf', 'Suppe', 'Salat'):
        _proven(space, name)
    _kitchen(space, 'Neuland')

    body = client.get(URL, {'minrating': '0'}).content.decode()

    assert 'Neuland' in body
    assert 'href="?minrating=4"' in body  # and one click puts it back


def test_a_url_with_its_own_parameter_is_never_reinterpreted(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    for name in ('Eintopf', 'Auflauf', 'Suppe', 'Salat'):
        _proven(space, name)
    _kitchen(space, 'Neuland')

    body = client.get(URL, {'n': '12'}).content.decode()

    assert 'Neuland' in body
    assert 'minrating=0' not in body
    assert 'Montag bis Donnerstag' not in body


def test_an_explicit_minrating_is_honoured_on_a_weekday(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    _proven(space, 'Solide', rating=2)
    _proven(space, 'Gut', rating=5)

    body = client.get(URL, {'minrating': '2'}).content.decode()

    assert 'Solide' in body
    assert 'Gut' in body


def test_saving_on_the_default_page_does_not_change_the_page(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    for name in ('Eintopf', 'Auflauf', 'Suppe', 'Salat'):
        _proven(space, name)
    _kitchen(space, 'Neuland')

    # The redirect after a save carries `geloggt=1`, which is a flash, not a
    # question: the page must not turn into a different one just because a
    # card was rated.
    body = client.get(URL, {'geloggt': '1'}).content.decode()

    assert 'Neuland' not in body
    assert 'href="?minrating=0"' in body


def test_the_default_steps_aside_when_too_few_dishes_are_proven(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    _proven(space, 'Eintopf')
    _kitchen(space, 'Neuland')

    body = client.get(URL).content.decode()

    assert 'Neuland' in body
    assert 'deshalb heute ohne „nur Bewährtes“' in body
    assert 'minrating=0' not in body  # nothing was switched on, so nothing to switch off


def test_the_default_steps_aside_when_nothing_is_rated_at_all(kitchen, monkeypatch):
    client, space = kitchen
    monkeypatch.setattr(views, '_today', lambda: TUESDAY)
    _kitchen(space, 'Neuland')

    body = client.get(URL).content.decode()

    assert 'Neuland' in body
    assert 'Noch nichts bewährt' in body


# --- the history page ---------------------------------------------------------


def test_history_groups_by_month(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    with scopes_disabled():
        user = UserFactory.create(first_name='Daniel', last_name='')
        UserSpace.objects.create(user=user, space=space, active=True)
        CookLogFactory.create(recipe=dish, created_by=user, rating=5, space=space,
                              created_at=timezone.now().replace(year=2026, month=10, day=3))
        CookLogFactory.create(recipe=dish, created_by=user, rating=4, space=space,
                              created_at=timezone.now().replace(year=2026, month=11, day=3))

    body = client.get(HISTORY).content.decode()

    assert 'Oktober 2026' in body
    assert 'November 2026' in body


def test_history_filters_by_person(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    with scopes_disabled():
        daniel = UserFactory.create(first_name='Daniel', last_name='')
        franziska = UserFactory.create(first_name='Franziska', last_name='')
        CookLogFactory.create(recipe=dish, created_by=daniel, rating=5, space=space,
                              comment='von Daniel')
        CookLogFactory.create(recipe=dish, created_by=franziska, rating=4, space=space,
                              comment='von Franziska')

    body = client.get(HISTORY, {'by': franziska.username}).content.decode()

    assert 'von Franziska' in body
    assert 'von Daniel' not in body


def test_the_query_string_survives_the_redirect(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    response = client.post(URL, {
        'recipe': dish.id, 'rating': '4',
        'next': '/api/plugins/kitchen/?carb=Beilage::Kartoffel&seed=abc',
    })

    assert 'carb=Beilage' in response['Location']
    assert 'seed=abc' in response['Location']
    assert response['Location'].endswith('geloggt=1')


def test_a_quarter_star_is_stored_as_given(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    client.post(URL, {'recipe': dish.id, 'rating': '4.25', 'date': '2026-11-20'})

    with scopes_disabled():
        log = CookLog.objects.get()
    assert float(log.rating) == 4.25


def test_a_rating_off_the_quarter_step_is_ignored(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')

    client.post(URL, {'recipe': dish.id, 'rating': '4.1', 'date': '2026-11-20'})

    with scopes_disabled():
        assert CookLog.objects.get().rating is None


def test_history_shows_the_quarter_and_the_display_name(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    with scopes_disabled():
        person = UserFactory.create(first_name='Daniel', last_name='')
        UserSpace.objects.create(user=person, space=space, active=True)
        CookLogFactory.create(recipe=dish, created_by=person, rating='4.25', space=space,
                              comment='Viertelstern')

    body = client.get(HISTORY).content.decode()

    assert '4,25' in body
    assert '>Daniel<' in body
    assert '>daniel<' not in body
# --- gekocht, aber nie bewertet ----------------------------------------------

def test_cooked_page_names_the_unrated_cooks(kitchen):
    client, space = kitchen
    dish = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)
    _proven(space, 'Kartoffelsuppe')

    body = client.get(HISTORY).content.decode()

    assert '<strong>3×</strong>' in body
    assert '<strong>2×</strong>' in body
    assert 'ohne Bewertung' in body
    nudge = body.split('nudge-list', 1)[1].split('</ul>', 1)[0]
    assert 'Linseneintopf' in nudge
    assert f'name="recipe" value="{dish.id}"' in nudge
    assert 'action="/api/plugins/kitchen/"' in nudge
    assert 'name="rating"' in nudge


def test_the_nudge_leaves_out_a_recipe_that_was_ever_rated(kitchen):
    client, space = kitchen
    twice = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)
    one_rated = _kitchen(space, 'Risotto')
    _cooked(space, one_rated, rating=None, times=1)
    _cooked(space, one_rated, rating=4, times=1)

    body = client.get(HISTORY).content.decode()
    nudge = body.split('nudge-list', 1)[1].split('</ul>', 1)[0]

    assert 'Linseneintopf' in nudge
    assert 'Risotto' not in nudge


def test_the_nudge_form_returns_to_the_cooked_page(kitchen):
    client, space = kitchen
    dish = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)

    response = client.post(URL, {'recipe': dish.id, 'rating': '4.25',
                                 'next': '/api/plugins/kitchen/gekocht/'})

    assert response.status_code == 302
    assert response['Location'].endswith('/api/plugins/kitchen/gekocht/?geloggt=1')
    with scopes_disabled():
        assert float(CookLog.objects.filter(rating__gt=0).get().rating) == 4.25


def test_card_badge_marks_a_twice_cooked_never_rated_recipe(kitchen):
    client, space = kitchen
    dish = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)
    _cooked(space, _kitchen(space, 'Einmal'), rating=None, times=1)

    body = client.get(URL, {'minrating': '0'}).content.decode()

    assert 'gekocht, nie bewertet' in body
    assert f'href="#stars-{dish.id}"' in body
    assert f'id="stars-{dish.id}"' in body
    assert body.count('class="badge badge-warning badge-nudge"') == 1


def test_a_saved_cook_is_visible_on_the_cooked_page(kitchen):
    client, space = kitchen
    _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)

    body = client.get(HISTORY, {'geloggt': '1'}).content.decode()

    assert 'Gekocht gespeichert.' in body
