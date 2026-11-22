"""The latest cook is on the first page.

The recipe page shows a "last time" line from the first page of this endpoint.
Pagination is the trap: ascending order puts the newest note on a page nobody
loads.
"""

from datetime import timedelta

import pytest
from django.contrib import auth
from django.utils import timezone

from cookbook.tests.factories import CookLogFactory

pytestmark = pytest.mark.django_db


def test_cook_log_list_newest_first(search_recipes, space_1, u1_s1):
    user = auth.get_user(u1_s1)
    now = timezone.now()
    CookLogFactory.create(
        recipe=search_recipes.r1, created_by=user, rating=3, space=space_1,
        created_at=now - timedelta(days=10),
    )
    newest = CookLogFactory.create(
        recipe=search_recipes.r1, created_by=user, rating=5, space=space_1,
        created_at=now,
    )

    response = u1_s1.get('/api/cook-log/', {'recipe': search_recipes.r1.id})

    assert response.status_code == 200
    assert response.json()['results'][0]['id'] == newest.id
