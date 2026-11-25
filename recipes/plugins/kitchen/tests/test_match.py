"""The matching rules, without a browser.

Every test here would pass on a page that renders nothing useful if the rule
were wrong, so the numbers are asserted directly: which recipes survive a
filter, what counts as missing, and what order the cards come back in.
"""

from __future__ import annotations

import pytest
from cookbook.models import Food, Keyword, Recipe
from cookbook.tests.factories import (
    CookLogFactory, FoodFactory, IngredientFactory, KeywordFactory,
    RecipeFactory, SpaceFactory, StepFactory, UserFactory,
)
from django_scopes import scope, scopes_disabled

from recipes.plugins.kitchen import match

pytestmark = pytest.mark.django_db


@pytest.fixture
def space(db):
    with scopes_disabled():
        return SpaceFactory.create(name='Kitchen')


def keyword(space, name):
    with scopes_disabled():
        return KeywordFactory.create(space=space, name=name)


def recipe(space, name, keywords=(), foods=()):
    """A cookable recipe: one step, one ingredient per food."""
    with scopes_disabled():
        recipe = RecipeFactory.create(space=space, name=name, keywords=[], steps__count=0)
        for kw in keywords:
            recipe.keywords.add(kw)
        step = StepFactory.create(space=space, ingredients__count=0)
        recipe.steps.add(step)
        for food_name in foods:
            food = FoodFactory.create(space=space, name=food_name)
            step.ingredients.add(IngredientFactory.create(space=space, food=food))
        return recipe


def test_axis_values_only_that_axis(space):
    keyword(space, 'Beilage::Reis')
    keyword(space, 'Beilage::Kartoffel')
    keyword(space, 'Hauptzutat::Hähnchen')

    with scope(space=space):
        assert match.axis_values('Beilage::') == ['Beilage::Kartoffel', 'Beilage::Reis']


def test_toggle_adds_then_removes():
    assert match.toggle(['a'], 'b') == ['a', 'b']
    assert match.toggle(['a', 'b'], 'a') == ['b']


def test_two_axes_require_both(space):
    reis = keyword(space, 'Beilage::Reis')
    haehnchen = keyword(space, 'Hauptzutat::Hähnchen')
    fisch = keyword(space, 'Hauptzutat::Fisch')
    both = recipe(space, 'Reis mit Hähnchen', [reis, haehnchen])
    recipe(space, 'Reis mit Fisch', [reis, fisch])

    with scope(space=space):
        got = match.recipes_for({'carb': ['Beilage::Reis'], 'protein': ['Hauptzutat::Hähnchen']})
        assert list(got.values_list('name', flat=True)) == [both.name]


def test_values_inside_one_axis_are_or(space):
    reis = keyword(space, 'Beilage::Reis')
    kartoffel = keyword(space, 'Beilage::Kartoffel')
    recipe(space, 'Reisgericht', [reis])
    recipe(space, 'Kartoffelgericht', [kartoffel])
    recipe(space, 'Nudelgericht', [keyword(space, 'Beilage::Nudeln')])

    with scope(space=space):
        got = match.recipes_for({'carb': ['Beilage::Reis', 'Beilage::Kartoffel']})
        assert sorted(got.values_list('name', flat=True)) == ['Kartoffelgericht', 'Reisgericht']


def test_recipe_without_steps_is_not_cookable(space):
    with scopes_disabled():
        RecipeFactory.create(space=space, name='Leere Seite', keywords=[], steps__count=0)

    with scope(space=space):
        assert list(match.recipes_for({}).values_list('name', flat=True)) == []


def test_staples_never_reported_missing():
    assert match.missing({'Salz', 'Öl', 'Kokosmilch'}, set()) == ['Kokosmilch']


def test_staple_variants_are_covered_by_suffix():
    # Measured in the live library: Meersalz 450 uses, Olivenöl 1392,
    # Schwarzer Pfeffer 1015. They must not show up as shopping items.
    assert match.missing({'salz', 'Meersalz', 'Olivenöl', 'Schwarzer Pfeffer'}, set()) == []


def test_ingredient_with_no_staple_family_stays_missing():
    assert match.missing({'Kokosmilch', 'Fischsauce'}, set()) == ['Fischsauce', 'Kokosmilch']


def test_reference_pages_are_never_candidates(space):
    grundlagen = keyword(space, 'Rezepttyp::Grundlagen')
    recipe(space, 'Messer & Schnitt', [grundlagen])
    recipe(space, 'Echtes Gericht', [keyword(space, 'Beilage::Reis')])

    with scope(space=space):
        names = list(match.recipes_for({}).values_list('name', flat=True))
    assert names == ['Echtes Gericht']


def test_duplicate_food_counts_once(space):
    r = recipe(space, 'Zweimal Butter', foods=['Butter', 'Butter'])

    with scope(space=space):
        r = Recipe.objects.prefetch_related('steps__ingredients__food').get(pk=r.pk)
        assert match.food_names(r) == {'Butter'}


def test_ingredient_without_food_is_skipped(space):
    with scopes_disabled():
        r = RecipeFactory.create(space=space, name='Gruppe', keywords=[], steps__count=0)
        step = StepFactory.create(space=space, ingredients__count=0)
        r.steps.add(step)
        step.ingredients.add(IngredientFactory.create(space=space, food=None, is_header=True))

    with scope(space=space):
        r = Recipe.objects.prefetch_related('steps__ingredients__food').get(pk=r.pk)
        assert match.food_names(r) == set()


def _candidate(recipe_id, have, missing_names):
    return match.Candidate(recipe_id, f'Rezept {recipe_id}', 20, '', tuple(have), tuple(missing_names))


def test_zero_missing_beats_one_missing():
    complete = _candidate(1, ['Reis', 'Hähnchen', 'Kokosmilch'], [])
    near = _candidate(2, ['Reis'], ['Kokosmilch'])

    ranked = match.rank([near, complete], allow_missing=1, seed='s', limit=6)

    assert [c.recipe_id for c in ranked] == [1, 2]


def test_more_have_first_inside_tier():
    many = _candidate(1, ['Reis', 'Hähnchen'], [])
    few = _candidate(2, ['Reis'], [])

    ranked = match.rank([few, many], allow_missing=1, seed='s', limit=6)

    assert [c.recipe_id for c in ranked] == [1, 2]


def test_seed_changes_order_inside_tier():
    candidates = [_candidate(i, ['Reis'], []) for i in range(1, 8)]

    first = [c.recipe_id for c in match.rank(candidates, seed='a', limit=6)]
    again = [c.recipe_id for c in match.rank(candidates, seed='a', limit=6)]
    second = [c.recipe_id for c in match.rank(candidates, seed='b', limit=6)]

    assert first == again
    assert first != second


def test_limit_cuts():
    candidates = [_candidate(i, [], []) for i in range(10)]
    assert len(match.rank(candidates, allow_missing=1, seed='s', limit=6)) == 6


def test_strictness_excludes_two_missing():
    near = _candidate(1, ['Reis'], ['Kokosmilch'])
    far = _candidate(2, [], ['Kokosmilch', 'Limette'])

    assert [c.recipe_id for c in match.rank([near, far], allow_missing=1, seed='s', limit=6)] == [1]
    assert len(match.rank([near, far], allow_missing=2, seed='s', limit=6)) == 2


def test_search_foods_is_space_scoped(space):
    with scopes_disabled():
        other = SpaceFactory.create(name='Other')
        FoodFactory.create(space=space, name='Kokosmilch')
        FoodFactory.create(space=other, name='Kokosmilch fremd')

    with scope(space=space):
        assert match.search_foods('kokos') == ['Kokosmilch']


# --- ratings -----------------------------------------------------------------

def _rated(recipe_id, have, missing_names, rating=None):
    return match.Candidate(
        recipe_id, f'Rezept {recipe_id}', 20, '', tuple(have), tuple(missing_names),
        rating=rating,
    )


def test_rating_breaks_a_tie():
    good = _rated(1, ['Reis'], [], 4.8)
    okay = _rated(2, ['Reis'], [], 4.2)

    ranked = match.rank([okay, good], seed='s', limit=6)

    assert [c.recipe_id for c in ranked] == [1, 2]


def test_unrated_is_neutral_not_zero():
    great = _rated(1, ['Reis'], [], 5.0)
    unrated = _rated(2, ['Reis'], [])
    bad = _rated(3, ['Reis'], [], 1.0)

    ranked = match.rank([bad, unrated, great], seed='s', limit=6)

    assert [c.recipe_id for c in ranked] == [1, 2, 3]


def test_fit_beats_fame():
    famous = _rated(1, ['Reis'], ['Kokosmilch'], 5.0)
    plain = _rated(2, ['Reis'], [])

    ranked = match.rank([famous, plain], seed='s', limit=6)

    assert [c.recipe_id for c in ranked] == [2, 1]


def test_min_rating_drops_the_merely_okay():
    good = _rated(1, ['Reis'], [], 4.0)
    meh = _rated(2, ['Reis'], [], 3.0)

    ranked = match.rank([meh, good], seed='s', limit=6, min_rating=4)

    assert [c.recipe_id for c in ranked] == [1]


def test_household_rating_counts_both_people(space):
    with scopes_disabled():
        dish = recipe(space, 'Suppe')
        one = UserFactory.create()
        two = UserFactory.create()
        CookLogFactory.create(recipe=dish, created_by=one, rating=5, space=space)
        CookLogFactory.create(recipe=dish, created_by=two, rating=3, space=space)

    with scope(space=space):
        assert match.household_ratings()[dish.id] == (4.0, 2)


def test_last_note_is_the_newest_one(space):
    from datetime import timedelta
    from django.utils import timezone

    now = timezone.now()
    with scopes_disabled():
        dish = recipe(space, 'Suppe')
        one = UserFactory.create(first_name='Daniel', last_name='')
        two = UserFactory.create(first_name='Franziska', last_name='')
        CookLogFactory.create(recipe=dish, created_by=one, rating=4, space=space,
                              comment='weniger Salz', created_at=now - timedelta(days=3))
        CookLogFactory.create(recipe=dish, created_by=two, rating=5, space=space,
                              comment='mehr Zitrone', created_at=now)

    with scope(space=space):
        when, who, note = match.last_notes()[dish.id]

    assert who == 'Franziska'
    assert note == 'mehr Zitrone'
    assert when == now.date()


def test_a_cleared_star_is_not_a_verdict(space):
    """Vuetify stores 0 when a selected star is clicked again; that is not a rating."""
    with scopes_disabled():
        dish = recipe(space, 'Suppe')
        one = UserFactory.create()
        CookLogFactory.create(recipe=dish, created_by=one, rating=5, space=space)
        CookLogFactory.create(recipe=dish, created_by=one, rating=0, space=space)

    with scope(space=space):
        assert match.household_ratings()[dish.id] == (5.0, 1)


# --- the cookbook tree --------------------------------------------------------


def test_herkunft_reads_both_tree_shapes():
    assert match.herkunft('Herkunft::Mittelmeer::Italien::Toskana') == (
        'Mittelmeer', 'Italien', 'Toskana')
    assert match.herkunft('Herkunft::Italien') == ('Mittelmeer', 'Italien', '')
    assert match.herkunft('Herkunft::Italien::Toskana') == ('Mittelmeer', 'Italien', 'Toskana')
    assert match.herkunft('Beilage::Reis') is None


def test_every_country_belongs_to_exactly_one_shelf():
    countries = [country for shelf in match.SHELVES.values() for country in shelf]
    assert len(countries) == len(set(countries)) == len(match.COUNTRY_SHELF)
    assert set(match.COUNTRY_SHELF.values()) == set(match.SHELVES)


def test_class_of_is_a_partition():
    assert match.class_of(frozenset({'Hauptzutat::Hähnchen'})) == 'fleisch'
    assert match.class_of(frozenset({'Hauptzutat::Fisch'})) == 'fisch'
    # A fish tag wins over a stray vegetarian tag, as `Ernaehrung::Fleisch`
    # includes fish: the gate must never count one recipe twice.
    assert match.class_of(frozenset({'Hauptzutat::Fisch', 'Hauptzutat::Hähnchen'})) == 'fleisch'
    assert match.class_of(frozenset({'Ernaehrung::Vegetarisch'})) == 'vegetarisch'
    assert match.class_of(frozenset({'Ernaehrung::Vegan'})) == 'vegetarisch'
    assert match.class_of(frozenset({'Beilage::Reis'})) == 'ohne'


def test_carb_ohne_also_means_untagged():
    assert match.matches(frozenset({'Beilage::Reis'}), {'carb': 'ohne'}) is False
    assert match.matches(frozenset({'Herkunft::Italien'}), {'carb': 'ohne'}) is True
    assert match.matches(frozenset({'Beilage::Ohne Beilage'}), {'carb': 'ohne'}) is True


def test_carb_kind_accepts_raw_keywords():
    assert match.carb_kind('Beilage::Nudeln') == 'Pasta'
    assert match.carb_kind('Beilage::Teig') == 'Brot/Teig'
    assert match.carb_kind('Pasta') == 'Pasta'
    assert match.carb_kind('Beilage::GibtEsNicht') == 'Beilage::GibtEsNicht'


def test_region_matches_every_country_in_the_shelf():
    names = frozenset({'Herkunft::Spanien'})
    assert match.matches(names, {'region': 'Mittelmeer'}) is True
    assert match.matches(names, {'region': 'DACH'}) is False
    assert match.matches(names, {'region': 'Mittelmeer', 'land': 'Spanien'}) is True
    assert match.matches(names, {'region': 'Mittelmeer', 'land': 'Italien'}) is False
