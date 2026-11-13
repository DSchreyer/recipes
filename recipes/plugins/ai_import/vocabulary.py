"""Shared vocabulary for the AI import plugin.

Everything a model may propose is checked against what the household's space
already has. Two reasons:

1. Tandoor's own ``scripts/tandoor-organise.py`` owns the keyword tree
   (``Herkunft::``, ``Aufwand::``, ``Ernaehrung::``, ...). A model that invents
   ``Mediterranean Cuisine`` next to ``Herkunft::Italien`` breaks the filters
   and the audit that checks them.
2. An unknown unit silently changes a shopping list, and an unknown food is
   exactly the duplicate the library spent a week removing.

Nothing here calls a model. It only reads the space.
"""

from __future__ import annotations

import re
import unicodedata

from cookbook.models import Food, Keyword, Unit
from django_scopes import scopes_disabled

# Keywords the model may never invent. They are taxonomy axes with a fixed
# value table; the model picks an existing leaf or leaves the axis alone.
CLOSED_AXES = {
    'Herkunft',
    'Rezepttyp',
    'Beilage',
    'Hauptzutat',
    'Methode',
    'Aufwand',
    'Ernaehrung',
    'Saison',
    'Temperatur',
    'Vorbereitung',
    'Quelle',
}

MAX_TAGS = 6
MAX_INSTRUCTION_CHARS = 4000
MAX_TITLE_CHARS = 120


def _fold(text: str) -> str:
    """Comparison key: casefolded, umlauts folded, punctuation to spaces."""
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^a-z0-9 ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def food_key(name: str) -> str:
    """Comparison key for a food name: ``Eier`` and ``Ei`` are the same food.

    This is Atlas's ``key()`` from ``scripts/tandoor-normalise-foods.py``,
    which produced the live library's 716-to-453 reduction. Reused rather than
    reinvented: the plugin must fold names the same way the library was folded,
    or a model's "Eier" lands as a new food next to "Ei".
    """
    text = _fold(name).split(',')[0].strip()
    words = []
    for word in text.split():
        # "Ei" is four letters and "Eier" its plural; Atlas's original rule
        # (len > 4) missed every short stem and is the reason `Ei`/`Eier`
        # survives in the live library today.
        if len(word) > 3:
            for suffix in ('en', 'er', 'n', 'e'):
                if word.endswith(suffix):
                    word = word[:-len(suffix)]
                    break
        words.append(word)
    return ' '.join(words)


# Tandoor guards every space-owned table with django-scopes. The plugin runs
# inside a request that has a scope, but the preview endpoint also builds the
# vocabulary for a space it names explicitly, so the scope is disabled and the
# space is filtered by hand -- one rule, in one place.
def space_keywords(space) -> list[Keyword]:
    with scopes_disabled():
        return list(Keyword.objects.filter(space=space))


def space_foods(space) -> list[Food]:
    with scopes_disabled():
        return list(Food.objects.filter(space=space))


def space_units(space) -> list[Unit]:
    with scopes_disabled():
        return list(Unit.objects.filter(space=space))


def keyword_index(space) -> dict[str, Keyword]:
    """Every existing keyword, by folded full name and by folded leaf name.

    ``Herkunft::Italien`` is indexed both as ``herkunft::italien`` and as
    ``italien``, because a model asked for a country will answer "Italien"
    and not the tree path.
    """
    index: dict[str, Keyword] = {}
    for keyword in space_keywords(space):
        index[_fold(keyword.name)] = keyword
        if '::' in keyword.name:
            index.setdefault(_fold(keyword.name.split('::')[-1]), keyword)
    return index


def _axis_of(name: str) -> str | None:
    root = name.split('::')[0].strip()
    return root if root in CLOSED_AXES else None


def _parent_path(keyword: Keyword) -> str:
    parts = []
    node = keyword
    with scopes_disabled():
        while node is not None:
            parts.append(node.name)
            node = node.parent
    return '::'.join(reversed(parts))


def resolve_keywords(space, proposed: list[str]) -> tuple[list[Keyword], list[str]]:
    """Map proposed tag strings onto existing keywords.

    Returns ``(accepted, rejected)``. A proposal is accepted when it names an
    existing keyword exactly, or when it names an existing leaf inside a
    closed axis. Anything else is rejected: creating a keyword on the model's
    word is how a library grows two names for one thing.
    """
    index = keyword_index(space)
    accepted: list[Keyword] = []
    rejected: list[str] = []
    seen: set[int] = set()

    for raw in proposed or []:
        name = (raw or '').strip()
        if not name:
            continue
        keyword = index.get(_fold(name))
        if keyword is None:
            rejected.append(name)
            continue
        path = _parent_path(keyword)
        if '::' in name and _axis_of(path) is None and _axis_of(name) is None:
            rejected.append(name)
            continue
        if keyword.pk not in seen:
            seen.add(keyword.pk)
            accepted.append(keyword)

    return accepted[:MAX_TAGS], rejected


def food_index(space) -> dict[str, Food]:
    return {food_key(food.name): food for food in space_foods(space)}


def food_suggestions(space, proposed_names: list[str]) -> list[dict]:
    """Foods the recipe names that the space does not have yet.

    The model is not allowed to create them: Tandoor's importer creates a food
    on save, and the library treats every new spelling as a duplicate to merge
    later. Showing them in the preview lets the household merge them first.
    """
    index = food_index(space)
    out = []
    seen: set[str] = set()
    for name in proposed_names:
        folded = food_key(name)
        if not folded or folded in index or folded in seen:
            continue
        seen.add(folded)
        out.append({'name': name.strip(), 'folded': folded})
    return out


def sanitize_instruction(text: str) -> str:
    """Strip HTML and cap length.

    Tandoor renders instructions with markdown; a model that answers in HTML
    produces literal tags on the recipe page.
    """
    text = re.sub(r'<[^<]+?>', '', text or '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:MAX_INSTRUCTION_CHARS]


def sanitize_title(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^<]+?>', '', text or '')).strip()[:MAX_TITLE_CHARS]
