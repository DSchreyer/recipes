"""Every recipe list carries the caller's rating, not only a rating-sorted one.

The card grid and the picker read `rating` from the default list response. It
was annotated only when the request sorted or filtered by rating, so stars
would have appeared exactly where they were least needed.
"""

import pytest
from django.contrib import auth

from cookbook.tests.factories import CookLogFactory

pytestmark = pytest.mark.django_db


def test_list_returns_rating_without_rating_sort(search_recipes, space_1, u1_s1, u2_s1):
    user1 = auth.get_user(u1_s1)
    user2 = auth.get_user(u2_s1)
    CookLogFactory.create(recipe=search_recipes.r1, created_by=user1, rating=4, space=space_1)
    # The other household member's verdict must not leak into "my rating".
    CookLogFactory.create(recipe=search_recipes.r1, created_by=user2, rating=1, space=space_1)

    response = u1_s1.get('/api/recipe/')

    assert response.status_code == 200
    rows = {row['id']: row for row in response.json()['results']}
    assert rows[search_recipes.r1.id]['rating'] == 4


def test_unrated_recipe_has_no_rating(search_recipes, u1_s1):
    response = u1_s1.get('/api/recipe/')

    rows = {row['id']: row for row in response.json()['results']}
    assert rows[search_recipes.r1.id]['rating'] is None


def test_a_quarter_star_survives_the_round_trip(search_recipes, space_1, u1_s1):
    """The household rates in 0.25 steps; a store that rounds to int loses it."""
    from decimal import Decimal

    user = auth.get_user(u1_s1)
    CookLogFactory.create(recipe=search_recipes.r1, created_by=user, rating=Decimal('4.25'), space=space_1)

    response = u1_s1.get('/api/recipe/')

    rows = {row['id']: row for row in response.json()['results']}
    assert rows[search_recipes.r1.id]['rating'] == 4.25


def test_rating_filter_accepts_a_quarter_step(search_recipes, space_1, u1_s1):
    from decimal import Decimal

    user = auth.get_user(u1_s1)
    CookLogFactory.create(recipe=search_recipes.r1, created_by=user, rating=Decimal('4.25'), space=space_1)
    CookLogFactory.create(recipe=search_recipes.r2, created_by=user, rating=Decimal('4.00'), space=space_1)

    response = u1_s1.get('/api/recipe/', {'rating_gte': '4.25'})

    ids = {row['id'] for row in response.json()['results']}
    assert search_recipes.r1.id in ids
    assert search_recipes.r2.id not in ids
