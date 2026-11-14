import pytest
from cookbook.models import Food, Ingredient, Recipe, Step, Unit
from django_scopes import scope, scopes_disabled

pytestmark = pytest.mark.django_db


def test_tandoor_renders_our_placeholder(space_1):
    """The end-to-end truth: a placeholder produced by the plugin must render
    as amount + unit + food through Tandoor's own template helper."""
    from django_scopes import scopes_disabled
    from cookbook.tests.factories import UserFactory
    from cookbook.helper.template_helper import render_instructions

    with scopes_disabled():
        user = UserFactory.create()
        unit = Unit.objects.create(name='Gramm', space=space_1)
        food = Food.objects.create(name='Weizenmehl', space=space_1)
        recipe = Recipe.objects.create(name='T', space=space_1, created_by=user)
        step = Step.objects.create(instruction='{{ ingredients[0] }} in eine Schüssel geben.', space=space_1)
        ingredient = Ingredient.objects.create(amount=450, unit=unit, food=food, space=space_1)
        step.ingredients.add(ingredient)
        recipe.steps.add(step)

    with scopes_disabled():
        with scope(space=space_1):
            html = render_instructions(step)
    print('RENDERED:', html)
    assert '450' in html
    assert 'Gramm' in html
    assert 'Weizenmehl' in html
    assert 'ingredients[0]' not in html
    assert 'scalable-number' in html
