"""The page through Tandoor's own middleware.

The client is a real session, not a patched ``request.space``: the middleware is
what decides which space a query sees, and a bug there is the one that lets one
household read another's recipes.
"""

from __future__ import annotations

import pytest
from cookbook.models import UserSpace
from cookbook.tests.factories import (
    FoodFactory, IngredientFactory, KeywordFactory, RecipeFactory, SpaceFactory,
    StepFactory, UserFactory,
)
from django.test import Client
from django.urls import reverse
from django_scopes import scopes_disabled

pytestmark = pytest.mark.django_db
URL = '/api/plugins/kitchen/'


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
    missing_lines = [line for line in body.splitlines() if 'fehlt:' in line]

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
