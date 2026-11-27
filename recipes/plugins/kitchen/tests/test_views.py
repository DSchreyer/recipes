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


def test_the_search_box_finds_a_recipe_by_name(kitchen):
    client, space = kitchen
    _kitchen(space, 'Köhler-Curry mit Kokosmilch', ['Hauptzutat::Fisch'])
    _kitchen(space, 'Kartoffelsuppe', ['Beilage::Kartoffel'])

    body = client.get(URL, {'q': 'köhler'}).content.decode()
    assert 'Köhler-Curry mit Kokosmilch' in body
    assert 'Kartoffelsuppe' not in body

    # a word that names nothing says so instead of showing the whole library
    nothing = client.get(URL, {'q': 'zzz'}).content.decode()
    assert 'Nichts heißt' in nothing


def test_a_name_word_and_a_chip_narrow_together(kitchen):
    client, space = kitchen
    _kitchen(space, 'Köhler-Curry', ['Hauptzutat::Fisch'])
    _kitchen(space, 'Köhler mit Beurre Blanc', ['Hauptzutat::Fisch'])

    both = client.get(URL, {'q': 'köhler', 'protein': 'Hauptzutat::Fisch'}).content.decode()
    assert 'Köhler-Curry' in both and 'Beurre Blanc' in both

    # a chip that fits nothing gives way and says so; the typed word is still the
    # question, so both Köhler dishes stay on the page
    dead = client.get(URL, {'q': 'köhler', 'carb': 'Beilage::Kartoffel'}).content.decode()
    assert 'Köhler-Curry' in dead and 'Beurre Blanc' in dead
    assert 'Ohne Beilage' in dead


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
    assert 'carb=Beilage' in response['Location']
    assert 'geloggt' not in response['Location']
    with scopes_disabled():
        log = CookLog.objects.get()
    assert f'„{dish.name}“ geloggt.' in client.get(response['Location']).content.decode()
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

    # The confirmation is a message now, not a query flag: the page must not
    # turn into a different one just because a card was rated.
    body = client.get(URL).content.decode()

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
    assert 'geloggt' not in response['Location']
    assert f'„{dish.name}“ geloggt.' in client.get(response['Location']).content.decode()


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
    with scopes_disabled():
        newest = CookLog.objects.filter(recipe=dish).order_by('-pk').first()
    # The form addresses the cook that happened, not the recipe.
    assert f'action="/api/plugins/kitchen/gekocht/{newest.pk}/"' in nudge
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


def test_the_nudge_rates_the_cook_that_happened(kitchen):
    """Rating from the nudge used to post to the picker and invent a second cook."""
    client, space = kitchen
    dish = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)
    with scopes_disabled():
        newest = CookLog.objects.filter(recipe=dish).order_by('-pk').first()

    response = client.post(reverse('kitchen:cooked_entry', args=[newest.pk]),
                           {'action': 'save', 'rating': '4.25', 'next': HISTORY})

    assert response.status_code == 302
    assert response['Location'].endswith(f'/api/plugins/kitchen/gekocht/#cook-{newest.pk}')
    with scopes_disabled():
        assert CookLog.objects.filter(recipe=dish).count() == 2
        assert float(CookLog.objects.get(pk=newest.pk).rating) == 4.25


def test_card_badge_marks_a_twice_cooked_never_rated_recipe(kitchen):
    client, space = kitchen
    dish = _cooked(space, _kitchen(space, 'Linseneintopf'), rating=None, times=2)
    _cooked(space, _kitchen(space, 'Einmal'), rating=None, times=1)

    body = client.get(URL, {'minrating': '0'}).content.decode()

    assert 'gekocht, nie bewertet' in body
    assert f'href="#stars-{dish.id}"' in body
    assert f'id="stars-{dish.id}"' in body
    assert body.count('class="badge badge-warning badge-nudge"') == 1


def test_a_saved_cook_says_which_dish_was_saved(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Linseneintopf'), rating=None)

    response = client.post(
        reverse('kitchen:cooked_entry', args=[log.pk]),
        {'action': 'save', 'rating': '4', 'next': HISTORY}, follow=True,
    )

    assert '„Linseneintopf“ gespeichert.' in response.content.decode()


def test_a_confirmation_is_shown_once(kitchen):
    """A reload is not a second save, so it must not repeat the message."""
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                {'action': 'save', 'rating': '5', 'next': HISTORY}, follow=True)
    again = client.get(HISTORY).content.decode()

    assert '„Kartoffelsuppe“ gespeichert.' not in again


# --- the funnel: shelf -> country -> class -> carb ----------------------------


def test_region_row_lists_cookbook_shelves_with_counts(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien'])
    _kitchen(space, 'Curry', ['Herkunft::Thailand'])

    body = client.get(URL).content.decode()

    assert 'Mittelmeer <span class="filter-chip__n">1</span>' in body
    assert 'Südostasien <span class="filter-chip__n">1</span>' in body
    # Countries are the next row, not a wall of 34 chips on the first one.
    assert 'Italien <span class="filter-chip__n">' not in body


def test_country_row_appears_only_inside_a_shelf(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien'])

    assert 'step-label">Land' not in client.get(URL).content.decode()

    shelved = client.get(URL, {'region': 'Mittelmeer'}).content.decode()
    assert 'step-label">Land' in shelved
    assert 'Italien <span class="filter-chip__n">1</span>' in shelved


def test_region_filters_to_its_countries(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien'])
    _kitchen(space, 'Curry', ['Herkunft::Thailand'])

    body = client.get(URL, {'region': 'Mittelmeer'}).content.decode()

    assert 'Pasta' in body
    assert 'Curry' not in body


def test_subregion_row_appears_under_a_country(kitchen):
    client, space = kitchen
    _kitchen(space, 'Toskanische Pasta', ['Herkunft::Italien::Toskana'])
    _kitchen(space, 'Sizilianische Pasta', ['Herkunft::Italien::Sizilien'])

    body = client.get(URL, {'region': 'Mittelmeer', 'land': 'Italien'}).content.decode()
    assert 'Toskanische Pasta' in body and 'Sizilianische Pasta' in body

    body = client.get(
        URL, {'region': 'Mittelmeer', 'land': 'Italien', 'sub': 'Toskana'}
    ).content.decode()
    assert 'Toskanische Pasta' in body
    assert 'Sizilianische Pasta' not in body


def test_class_gate_is_a_partition(kitchen):
    client, space = kitchen
    _kitchen(space, 'Huhn', ['Hauptzutat::Hähnchen'])
    _kitchen(space, 'Lachs', ['Hauptzutat::Fisch'])
    _kitchen(space, 'Gemüse', ['Ernaehrung::Vegetarisch'])
    _kitchen(space, 'Unbekannt', ['Beilage::Reis'])

    body = client.get(URL).content.decode()
    for label in ('Fleisch', 'Fisch', 'Vegetarisch', 'ohne Angabe'):
        assert f'{label} <span class="filter-chip__n">1</span>' in body

    for klasse, shown, hidden in (
        ('fleisch', 'Huhn', 'Lachs'),
        ('fisch', 'Lachs', 'Huhn'),
        ('vegetarisch', 'Gemüse', 'Huhn'),
        ('ohne', 'Unbekannt', 'Gemüse'),
    ):
        body = client.get(URL, {'klasse': klasse}).content.decode()
        assert shown in body, klasse
        assert hidden not in body, klasse


def test_carb_chips_fold_synonyms(kitchen):
    client, space = kitchen
    _kitchen(space, 'Handgemachte Nudeln', ['Beilage::Nudeln'])
    _kitchen(space, 'Pasta al Pomodoro', ['Beilage::Pasta'])

    body = client.get(URL, {'carb': 'Pasta'}).content.decode()

    assert 'Pasta <span class="filter-chip__n">2</span>' in body
    assert 'Handgemachte Nudeln' in body
    assert 'Pasta al Pomodoro' in body


def test_counts_answer_the_other_filters(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta vegetarisch', ['Herkunft::Italien', 'Ernaehrung::Vegetarisch'])
    _kitchen(space, 'Pasta mit Huhn', ['Herkunft::Italien', 'Hauptzutat::Hähnchen'])

    body = client.get(URL, {'region': 'Mittelmeer', 'klasse': 'vegetarisch'}).content.decode()

    # Italien has two recipes, but one of them is meat: the chip says one.
    assert 'Italien <span class="filter-chip__n">1</span>' in body


def test_a_zero_chip_is_shown_disabled(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien', 'Ernaehrung::Vegetarisch'])

    body = client.get(URL, {'region': 'Mittelmeer', 'klasse': 'vegetarisch'}).content.decode()

    assert 'Portugal <span class="filter-chip__n">0</span>' in body
    assert 'filter-chip--off' in body


def test_protein_row_only_inside_meat_and_fish(kitchen):
    client, space = kitchen
    _kitchen(space, 'Kartoffelsalat', ['Herkunft::Deutschland', 'Ernaehrung::Vegetarisch'])
    _kitchen(space, 'Schnitzel', ['Herkunft::Deutschland', 'Hauptzutat::Schwein'])

    veg = client.get(URL, {'region': 'DACH', 'klasse': 'vegetarisch'}).content.decode()
    assert 'step-label">Hauptzutat' not in veg

    meat = client.get(URL, {'region': 'DACH', 'klasse': 'fleisch'}).content.decode()
    assert 'step-label">Hauptzutat' in meat
    assert 'Schwein <span class="filter-chip__n">1</span>' in meat


def test_an_applied_filter_can_be_removed_in_one_click(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien', 'Ernaehrung::Vegetarisch'])

    body = client.get(URL, {'region': 'Mittelmeer', 'klasse': 'vegetarisch'}).content.decode()

    assert 'class="applied-chip" href="?klasse=vegetarisch"' in body
    assert 'alles zurücksetzen' in body


def test_an_old_cuisine_bookmark_still_answers(kitchen):
    client, space = kitchen
    _kitchen(space, 'Pasta', ['Herkunft::Italien'])
    _kitchen(space, 'Curry', ['Herkunft::Thailand'])

    body = client.get(URL, {'cuisine': 'Herkunft::Italien'}).content.decode()

    assert 'Pasta' in body
    assert 'Curry' not in body


def test_the_header_counts_the_pool_not_the_six_cards(kitchen):
    client, space = kitchen
    for index in range(8):
        _kitchen(space, f'Gericht {index}')

    body = client.get(URL).content.decode()

    assert '8 Rezepte' in body
    assert 'mehr zeigen' in body


# --- correcting an entry ------------------------------------------------------


def _one_cook(space, recipe, rating=None, comment=None, when=None):
    with scopes_disabled():
        user = UserFactory.create(first_name='Daniel', last_name='')
        UserSpace.objects.create(user=user, space=space, active=True)
        fields = {'created_at': when} if when else {}
        return CookLogFactory.create(
            recipe=recipe, created_by=user, rating=rating, comment=comment,
            space=space, **fields,
        )


def test_a_cook_can_be_rated_renoted_and_redated(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))

    response = client.post(
        reverse('kitchen:cooked_entry', args=[log.pk]),
        {'action': 'save', 'rating': '4.25', 'note': 'mehr Muskat',
         'date': '2026-10-03', 'next': HISTORY},
    )

    assert response.status_code == 302
    assert response['Location'].endswith(f'/gekocht/#cook-{log.pk}')
    with scopes_disabled():
        log.refresh_from_db()
    assert float(log.rating) == 4.25
    assert log.comment == 'mehr Muskat'
    assert log.created_at.date().isoformat() == '2026-10-03'


def test_a_correction_leaves_what_the_form_did_not_carry(kitchen):
    """The nudge sends a rating only; the note and the day must survive it."""
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Linseneintopf'), comment='zu salzig')
    with scopes_disabled():
        before = CookLog.objects.get(pk=log.pk).created_at

    client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                {'action': 'save', 'rating': '3'})

    with scopes_disabled():
        log.refresh_from_db()
    assert float(log.rating) == 3
    assert log.comment == 'zu salzig'
    assert log.created_at == before


def test_a_rating_off_the_quarter_step_clears_instead_of_rounding(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                {'action': 'save', 'rating': '4.1'})

    with scopes_disabled():
        log.refresh_from_db()
    assert log.rating is None


def test_a_cook_can_be_deleted(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    response = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                           {'action': 'delete', 'next': HISTORY})

    assert response['Location'].endswith('/gekocht/')
    assert '„Kartoffelsuppe“ gelöscht.' in client.get(response['Location']).content.decode()
    with scopes_disabled():
        assert CookLog.objects.count() == 0


def test_another_spaces_cook_cannot_be_touched(kitchen):
    client, space = kitchen
    with scopes_disabled():
        other = SpaceFactory.create(name='Other')
        foreign = CookLogFactory.create(
            recipe=RecipeFactory.create(space=other, name='Fremd', steps__count=0),
            created_by=UserFactory.create(), rating=5, space=other,
        )

    response = client.post(reverse('kitchen:cooked_entry', args=[foreign.pk]),
                           {'action': 'delete'})

    assert response.status_code == 404
    with scopes_disabled():
        assert CookLog.objects.filter(pk=foreign.pk).count() == 1


def test_cooking_it_again_adds_a_fresh_entry(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    log = _one_cook(space, dish, rating=5)

    client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                {'action': 'cook', 'next': HISTORY})

    with scopes_disabled():
        logs = CookLog.objects.filter(recipe=dish)
    assert logs.count() == 2
    assert logs.filter(rating__isnull=True).count() == 1


# --- what a row shows ---------------------------------------------------------


def test_a_row_shows_the_dish_its_photo_and_its_axes(kitchen):
    client, space = kitchen
    dish = _kitchen(
        space, 'Toskanische Pasta',
        ['Herkunft::Mittelmeer', 'Herkunft::Mittelmeer::Italien',
         'Herkunft::Mittelmeer::Italien::Toskana', 'Beilage::Pasta', 'Aufwand::Schnell'],
    )
    with scopes_disabled():
        dish.image = 'recipes/toskanische-pasta.jpg'
        dish.save(update_fields=['image'])
    _one_cook(space, dish, rating='4.25', comment='mehr Salz')

    body = client.get(HISTORY).content.decode()

    assert 'recipes/toskanische-pasta.jpg' in body
    assert 'class="axis-chip">Italien<' in body
    assert 'class="axis-chip">Pasta<' in body
    assert 'class="axis-chip">Schnell<' in body
    assert '>Toskana<' not in body
    assert '>Mittelmeer<' not in body
    assert '4,25' in body


def test_a_cook_without_a_photo_drops_the_column(kitchen):
    """An empty 72 px square reads as a broken image; the row goes full width."""
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))

    body = client.get(HISTORY).content.decode()

    assert 'cook-row--text' in body
    assert 'class="cook-row__photo' not in body


def test_a_month_header_counts_and_averages(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    november = timezone.now().replace(year=2026, month=11, day=3)
    _one_cook(space, dish, rating=5, when=november)
    _one_cook(space, dish, rating=4, when=november.replace(day=9))

    body = client.get(HISTORY).content.decode()

    assert 'November 2026' in body
    assert '2× · ⌀ 4,5' in body


def test_every_row_carries_its_own_edit_form(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    body = client.get(HISTORY).content.decode()

    assert f'action="/api/plugins/kitchen/gekocht/{log.pk}/"' in body
    assert 'name="action" value="cook"' in body
    assert 'name="action" value="delete"' in body


def test_every_confirmation_names_the_dish(kitchen):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    log = _one_cook(space, dish, rating=4)

    saved = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                        {'action': 'save', 'rating': '4.25', 'next': HISTORY}, follow=True)
    cooked = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                         {'action': 'cook', 'next': HISTORY}, follow=True)
    removed = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                          {'action': 'delete', 'next': HISTORY}, follow=True)

    assert '„Kartoffelsuppe“ gespeichert.' in saved.content.decode()
    assert '„Kartoffelsuppe“ noch einmal gekocht.' in cooked.content.decode()
    assert '„Kartoffelsuppe“ gelöscht.' in removed.content.decode()


def test_a_new_confirmation_replaces_the_old_one(kitchen):
    """The page must not say "saved" while it is reporting a delete."""
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    response = client.post(
        reverse('kitchen:cooked_entry', args=[log.pk]),
        {'action': 'delete', 'next': HISTORY + '?by=daniel'}, follow=True,
    )

    body = response.content.decode()
    assert response.redirect_chain[-1][0].endswith('/gekocht/?by=daniel')
    assert '„Kartoffelsuppe“ gelöscht.' in body
    assert 'gespeichert.' not in body

# --- what the page says back -------------------------------------------------


def test_saving_returns_to_the_row_that_changed(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))

    response = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                           {'action': 'save', 'rating': '4', 'next': HISTORY})

    assert response['Location'].endswith(f'#cook-{log.pk}')


def test_cooking_it_again_returns_to_the_new_row(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=5)

    response = client.post(reverse('kitchen:cooked_entry', args=[log.pk]),
                           {'action': 'cook', 'next': HISTORY})

    with scopes_disabled():
        again = CookLog.objects.filter(recipe=log.recipe).exclude(pk=log.pk).get()
    assert response['Location'].endswith(f'#cook-{again.pk}')


def test_no_nudge_when_everything_is_rated(kitchen):
    """A block that reports "0× ohne Bewertung" is scaffolding for absent data."""
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    assert 'ohne Bewertung' not in client.get(HISTORY).content.decode()


def test_the_nudge_counts_only_the_filtered_person(kitchen):
    """Two numbers side by side have to count the same rows."""
    client, space = kitchen
    mine = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))
    _one_cook(space, _kitchen(space, 'Linseneintopf'))

    body = client.get(HISTORY, {'by': mine.created_by.username}).content.decode()

    assert '1×</strong> gekocht' in body
    assert '2×</strong> gekocht' not in body


def test_the_header_counts_the_whole_history_not_the_page(kitchen, monkeypatch):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    for _ in range(3):
        _one_cook(space, dish, rating=4)
    monkeypatch.setattr(views.CookedView, 'page_size', 1)

    body = client.get(HISTORY).content.decode()

    assert '<strong>3</strong> Einträge' in body
    assert '1 von 3 gezeigt' in body
    assert 'before=' in body


def test_one_person_hides_the_person_filter(kitchen):
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))

    assert 'class="people-tabs' not in client.get(HISTORY).content.decode()


def test_two_people_show_the_person_filter(kitchen):
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'))
    _one_cook(space, _kitchen(space, 'Linseneintopf'))

    assert 'class="people-tabs' in client.get(HISTORY).content.decode()


def test_no_template_comment_reaches_the_page(kitchen):
    """`{# ... #}` spans one line only; a wrapped one prints as literal text."""
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    for url in (HISTORY, URL):
        body = client.get(url).content.decode()
        assert '{#' not in body
        assert '{%' not in body

# --- searching and paging ----------------------------------------------------


def test_the_search_filters_by_dish_name(kitchen):
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)
    _one_cook(space, _kitchen(space, 'Linseneintopf'), rating=3)

    body = client.get(HISTORY, {'q': 'Kartoffel'}).content.decode()

    assert 'Kartoffelsuppe' in body
    assert 'Linseneintopf' not in body
    assert '<strong>1</strong> Einträge' in body


def test_a_search_without_a_hit_says_so_and_offers_a_way_back(kitchen):
    client, space = kitchen
    _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating=4)

    body = client.get(HISTORY, {'q': 'Auflauf'}).content.decode()

    assert 'ist nichts eingetragen' in body
    assert 'Suche zurücksetzen' in body


def test_the_cursor_walks_back_without_skipping_a_row(kitchen, monkeypatch):
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    for day in (1, 2, 3):
        _one_cook(space, dish, when=timezone.now().replace(year=2026, month=11, day=day))
    monkeypatch.setattr(views.CookedView, 'page_size', 2)

    first = client.get(HISTORY).content.decode()
    assert 'Ältere Einträge' in first
    assert '2 von 3 gezeigt' in first
    before, before_pk = _cursor(first)
    older = client.get(HISTORY, {'before': before, 'before_pk': before_pk}).content.decode()

    assert '1 von 3 gezeigt' not in older
    assert 'Ältere Einträge' not in older
    assert 'November 2026' in older


def test_every_row_rates_with_a_star_strip_not_a_select(kitchen):
    client, space = kitchen
    log = _one_cook(space, _kitchen(space, 'Kartoffelsuppe'), rating='4.25')

    body = client.get(HISTORY).content.decode()

    assert 'name="rating"' in body
    assert '<select name="rating"' not in body
    assert f'id="rate-{log.pk}-0"' in body
    assert 'value="4.25"' in body
    assert body.count('class="star-input__hit"') == 20


def _cursor(body):
    from urllib.parse import unquote

    raw = body.split('before=', 1)[1].split('"', 1)[0].replace('&amp;', '&')
    before, rest = raw.split('&before_pk=', 1)
    return unquote(before), rest.split('&', 1)[0]


def test_two_cooks_in_the_same_minute_are_both_reached(kitchen, monkeypatch):
    """Same timestamp used to order arbitrarily, so a cursor could skip a row."""
    client, space = kitchen
    dish = _kitchen(space, 'Kartoffelsuppe')
    stamp = timezone.now().replace(year=2026, month=11, day=23, microsecond=0)
    pks = [_one_cook(space, dish, when=stamp).pk for _ in range(3)]
    monkeypatch.setattr(views.CookedView, 'page_size', 2)

    seen, body, params = [], client.get(HISTORY).content.decode(), {}
    while True:
        page = client.get(HISTORY, params).content.decode()
        seen += [int(pk) for pk in _row_ids(page)]
        if 'Ältere Einträge' not in page:
            break
        before, before_pk = _cursor(page)
        params = {'before': before, 'before_pk': before_pk}

    assert sorted(seen) == sorted(pks)
    assert len(seen) == len(set(seen))


def _row_ids(body):
    import re

    return re.findall(r'id="cook-(\d+)"', body)
