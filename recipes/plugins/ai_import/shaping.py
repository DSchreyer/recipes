"""The JSON contract between the model and Tandoor's import dialog.

The shape is Tandoor's own: ``POST /api/recipe-from-source/`` already returns
``{'recipe': {...}, 'duplicates': [...]}`` and the Vue import page writes the
recipe straight into the editor. Returning the same shape means the plugin
needs no new UI and cannot drift from what the editor expects.

Two things differ from a plain scrape:

* every step carries its ingredients, because Tandoor silently drops a nested
  ingredient without ``unit`` and the Butter Chicken defect (one ingredient
  counted twice) is what happens when they are guessed;
* nothing is invented. A field the source does not state is ``None`` and the
  editor leaves the household's default.
"""

from __future__ import annotations

import json
import re

from .rewrite import (ensure_title, insert_placeholders, lift_title,
                      placeholders_are_safe)
from .vocabulary import food_key, sanitize_instruction, sanitize_title


class ShapeError(ValueError):
    """The model answered in a shape that cannot be shown to a person."""


def strip_fences(text: str) -> str:
    """Extract the JSON object from a model answer.

    Reasoning models wrap JSON in fences or add a sentence before it even when
    asked for a JSON object. ``cookbook.helper.ai_helper.strip_json_fences``
    does this for Tandoor's own AI views; this is the same idea, kept local so
    the plugin does not depend on a private helper's error behaviour.
    """
    text = (text or '').strip()
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end < start:
        raise ShapeError('Kein JSON in der Antwort')
    return text[start:end + 1]


def parse_model_answer(text: str) -> dict:
    try:
        payload = json.loads(strip_fences(text))
    except json.JSONDecodeError as exc:
        raise ShapeError(f'Antwort ist kein gültiges JSON: {exc.msg}') from exc
    if not isinstance(payload, dict):
        raise ShapeError('Antwort ist kein Objekt')
    return payload


def _number(value) -> float | None:
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(',', '.').strip()
    match = re.search(r'-?\d+(?:\.\d+)?', text)
    return float(match.group(0)) if match else None


def _ingredient(raw: dict, units: dict, foods: dict) -> dict:
    """One ingredient row, in the shape the recipe editor posts back.

    ``unit`` is never ``None``: Tandoor drops a nested ingredient that lacks
    it, with a 201, which is the silent failure the import contract records.
    """
    name = (raw.get('food') or '').strip()
    unit_name = (raw.get('unit') or '').strip()
    unit = units.get(unit_name.casefold().strip())
    food = foods.get(food_key(name))
    return {
        'amount': _number(raw.get('amount')) or 0,
        'unit': {'name': unit.name if unit else unit_name},
        'food': {'name': food.name if food else name},
        'note': (raw.get('note') or '').strip(),
        'original_text': (raw.get('original_text') or f"{raw.get('amount') or ''} {unit_name} {name}").strip()[:512],
        'is_header': bool(raw.get('is_header')),
        'no_amount': bool(raw.get('no_amount')),
    }


def _step(raw: dict, units: dict, foods: dict) -> dict:
    return {
        'name': sanitize_title(raw.get('name') or ''),
        'instruction': sanitize_instruction(raw.get('instruction') or ''),
        'ingredients': [_ingredient(i, units, foods) for i in (raw.get('ingredients') or [])],
        'show_ingredients_table': True,
    }


def to_recipe_payload(answer: dict, *, units: dict, foods: dict, keywords: list,
                      options: dict | None = None, warnings: list[str] | None = None) -> dict:
    """The ``recipe`` object Tandoor's import dialog expects.

    ``options`` carries the space's switches (``placeholders_enabled``,
    ``enforce_step_titles``) and defaults to the same behaviour as before the
    switches existed, so a caller that does not pass them gets the old result
    plus the title fix.

    Raises ``ShapeError`` when the answer has no usable name or no step: an
    import that produces an empty recipe is worse than no import, because the
    household only finds out at the stove.
    """
    options = options or {}
    name = sanitize_title(answer.get('name') or '')
    if not name:
        raise ShapeError('Rezept ohne Namen')

    steps = [_step(s, units, foods) for s in (answer.get('steps') or []) if isinstance(s, dict)]
    steps = [s for s in steps if s['instruction'] or s['ingredients']]
    if not steps:
        raise ShapeError('Rezept ohne Schritte')

    warnings = warnings if warnings is not None else []
    enforce_titles = options.get('enforce_step_titles', True)
    placeholders = options.get('placeholders_enabled', True)
    for number, step in enumerate(steps, 1):
        if enforce_titles:
            step['name'], step['instruction'] = lift_title(step['instruction'], step['name'])
            step['name'] = ensure_title(step['name'], step['instruction'])
        if placeholders:
            safe, reason = placeholders_are_safe(step['instruction'], step['ingredients'])
            if safe:
                step['instruction'] = insert_placeholders(step['instruction'], step['ingredients'])
            else:
                warnings.append(f'Schritt {number}: {reason}')
    return {
        'name': name,
        'description': sanitize_instruction(answer.get('description') or ''),
        'servings': int(_number(answer.get('servings')) or 1),
        'servings_text': (answer.get('servings_text') or '').strip(),
        'working_time': int(_number(answer.get('working_time')) or 0),
        'waiting_time': int(_number(answer.get('waiting_time')) or 0),
        'source_url': (answer.get('source_url') or '').strip(),
        'internal': True,
        'keywords': [
            {'id': k.pk, 'name': k.name, 'label': k.name}
            for k in keywords
        ],
        'steps': steps,
        'properties': [],
    }
