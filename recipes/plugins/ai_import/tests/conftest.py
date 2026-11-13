import pytest
from cookbook.tests.factories import SpaceFactory


@pytest.fixture
def space_1(db):
    return SpaceFactory.create(name='AI Import Test')


@pytest.fixture
def space_2(db):
    return SpaceFactory.create(name='Other Space')
