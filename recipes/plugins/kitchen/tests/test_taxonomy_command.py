"""The taxonomy command: rename into shelves, fold synonyms, stay idempotent."""

from __future__ import annotations

from io import StringIO

import pytest
from cookbook.models import Keyword
from cookbook.tests.factories import KeywordFactory, RecipeFactory, SpaceFactory
from django.core.management import call_command
from django_scopes import scopes_disabled

pytestmark = pytest.mark.django_db


def _run(*args):
    out = StringIO()
    call_command("kitchen_taxonomy", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def test_countries_and_regions_get_their_shelf():
    with scopes_disabled():
        space = SpaceFactory.create()
        country = KeywordFactory.create(space=space, name="Herkunft::Italien")
        region = KeywordFactory.create(space=space, name="Herkunft::Italien::Toskana")
        recipe = RecipeFactory.create(space=space, keywords__count=0, keywords=[country, region],
                             steps__count=0)

    _run()

    with scopes_disabled():
        assert recipe.keywords.filter(name="Herkunft::Mittelmeer::Italien").exists()
        assert recipe.keywords.filter(name="Herkunft::Mittelmeer::Italien::Toskana").exists()
        assert not Keyword.objects.filter(name="Herkunft::Italien").exists()


def test_synonyms_fold_and_keep_their_recipes():
    with scopes_disabled():
        space = SpaceFactory.create()
        pasta = KeywordFactory.create(space=space, name="Beilage::Pasta")
        noodles = KeywordFactory.create(space=space, name="Beilage::Nudeln")
        recipe = RecipeFactory.create(space=space, keywords__count=0, keywords=[noodles],
                             steps__count=0)

    _run()

    with scopes_disabled():
        assert not Keyword.objects.filter(name="Beilage::Nudeln").exists()
        assert recipe.keywords.filter(name="Beilage::Pasta").exists()
        assert Keyword.objects.filter(name="Beilage::Pasta").count() == 1


def test_second_run_changes_nothing():
    with scopes_disabled():
        space = SpaceFactory.create()
        KeywordFactory.create(space=space, name="Herkunft::Deutschland")
        KeywordFactory.create(space=space, name="Beilage::Nudeln")

    _run()
    output = _run()

    assert "0 renamed, 0 merged" in output


def test_dry_run_writes_nothing():
    with scopes_disabled():
        space = SpaceFactory.create()
        KeywordFactory.create(space=space, name="Herkunft::Deutschland")

    output = _run("--dry-run")

    assert "Herkunft::DACH::Deutschland" in output
    with scopes_disabled():
        assert Keyword.objects.filter(name="Herkunft::Deutschland").exists()
