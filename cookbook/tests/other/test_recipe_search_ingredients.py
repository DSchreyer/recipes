"""A recipe search must reach the ingredients, not only the title.

Measured 2026-11-11 on the household library (172 recipes): 'Hähnchenbrust'
sits in 291 ingredient rows and GET /api/recipe/?query=Hähnchenbrust returned
one recipe — the one with it in the name. The stored vectors cover name,
description and instruction only, and Postgres stems 'Hähnchen' and
'Hähnchenbrust' to different lexemes, so the fulltext path cannot bridge a
compound either. The list query now ORs a substring match on the ingredient
food name, which needs no reindex of the live database.

The fixture below is the household's shape: fulltext on name, description and
instructions, ingredient names not part of any configured search field.
"""

import pytest
from django.contrib import auth
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_scopes import scopes_disabled

from cookbook.models import SearchFields
from cookbook.tests.factories import FoodFactory, IngredientFactory, RecipeFactory, StepFactory

pytestmark = pytest.mark.django_db


def _recipe_with_food(space, food_name, name=None):
    """A recipe with one step and one ingredient carrying a canonical food."""
    fields = {'name': name} if name else {}
    with scopes_disabled():
        recipe = RecipeFactory.create(space=space, steps__count=0, keywords__count=0, **fields)
        step = StepFactory.create(space=space, ingredients__count=0)
        recipe.steps.add(step)
        step.ingredients.add(IngredientFactory.create(
            food=FoodFactory.create(name=food_name, space=space), space=space))
    return recipe


@pytest.fixture
def household_prefs(u1_s1):
    """Fulltext on title/description/instructions, substring on the title.

    This is the configuration the defect was measured under: nothing in it ever
    looks at an ingredient, so the search box could not see one.
    """
    user = auth.get_user(u1_s1)
    pref = user.searchpreference
    pref.icontains.set(SearchFields.objects.filter(field='name'))
    pref.istartswith.set([])
    pref.fulltext.set(SearchFields.objects.filter(
        field__in=['name', 'description', 'steps__instruction']))
    pref.trigram.set([])
    pref.unaccent.set(SearchFields.objects.all())
    pref.save()
    return user


@pytest.fixture
def chicken_recipes(space_1):
    """'food': the term only in the ingredients; 'title': only in the name;
    'other': a recipe that shares nothing with the term."""
    return {
        'food': _recipe_with_food(space_1, 'Hähnchenbrust', name='Ofengemüse mit Kräutern'),
        'title': _recipe_with_food(space_1, 'Rinderfilet', name='Hähnchenbrust mit Reis'),
        # Same word family, still a different food: proves the match is on the
        # stored name and not on a stem both sides collapse to.
        'other': _recipe_with_food(space_1, 'Rinderfilet', name='Rinderrouladen'),
    }


def _search_ids(client, term):
    response = client.get('/api/recipe/', {'query': term})
    assert response.status_code == 200
    body = response.json()
    return {row['id'] for row in body['results']}, body['count']


def test_ingredient_food_name_finds_the_recipe(chicken_recipes, household_prefs, u1_s1):
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hähnchenbrust')

    assert recipes['food'].id in ids


def test_a_recipe_without_the_ingredient_stays_out(chicken_recipes, household_prefs, u1_s1):
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hähnchenbrust')

    assert recipes['other'].id not in ids


def test_the_title_path_still_works(chicken_recipes, household_prefs, u1_s1):
    """A recipe whose title carries the term and whose ingredients do not."""
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hähnchenbrust')

    assert recipes['title'].id in ids


def test_a_compound_is_found_from_its_head_word(chicken_recipes, household_prefs, u1_s1):
    """'Hähnchen' and 'Hähnchenbrust' stem apart in Postgres; the substring does not."""
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hähnchen')

    assert recipes['food'].id in ids
    assert recipes['title'].id in ids


def test_umlaut_typo_still_matches_the_ingredient(chicken_recipes, household_prefs, u1_s1):
    """Unaccent is on for every field in this household, and the food name may
    be written either way: 'Hahnchen' must find 'Hähnchenbrust'."""
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hahnchen')

    assert recipes['food'].id in ids


def test_a_term_matching_nothing_returns_an_empty_page(chicken_recipes, household_prefs, u1_s1):
    """Not in a title, an instruction, a food name or a keyword of any recipe."""
    ids, count = _search_ids(u1_s1, 'Maracuja')

    assert ids == set()
    assert count == 0


def test_the_default_preferences_find_ingredients_too(chicken_recipes, u1_s1):
    """A user who never opened the search settings gets the fresh-install
    defaults: substring and trigram on the title only. Ingredients must still
    be reachable, or the library is invisible until somebody configures it."""
    recipes = chicken_recipes

    ids, _ = _search_ids(u1_s1, 'Hähnchenbrust')

    assert recipes['food'].id in ids
    assert recipes['other'].id not in ids


def test_the_ingredient_match_rides_in_the_page_query(chicken_recipes, household_prefs, u1_s1):
    """No second round trip: the food name is joined inside the page statement,
    not resolved by a query of its own before or after it."""
    recipes = chicken_recipes

    with CaptureQueriesContext(connection) as captured:
        response = u1_s1.get('/api/recipe/', {'query': 'Hähnchenbrust'})

    # Two statements carry the ingredient join: the page itself and the
    # pagination count around that same query. Nothing looks up ingredients on
    # its own and then filters recipes by the result.
    page_queries = [q['sql'] for q in captured.captured_queries if 'cookbook_ingredient' in q['sql']]
    assert len(page_queries) == 2
    assert any('LIMIT' in sql for sql in page_queries)
    assert all('cookbook_recipe' in sql for sql in page_queries)
    assert recipes['food'].id in {row['id'] for row in response.json()['results']}
