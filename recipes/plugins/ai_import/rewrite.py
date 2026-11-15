"""Step titles and Jinja placeholders, applied after the model answers.

Both exist because a model cannot be trusted with them:

* A title is metadata in one field and prose in another, and a model given
  both spaces sometimes writes "**Schritt 1: Teig ansetzen**" into the
  instruction. A recipe imported that way shows seven untitled steps, which is
  what the household found on recipe 199.
* A placeholder is a *positional* reference (``{{ ingredients[2] }}``). Asking
  a model to count its own rows invites off-by-one errors that read as
  "450 Gramm Zimt" at the stove. The plugin knows the list exactly.

Tandoor renders placeholders through a sandboxed Jinja environment
(``cookbook/helper/template_helper.py``): ``{{ ingredients[0] }}`` becomes a
scalable amount, unit and food, and ``.amount``, ``.unit``, ``.food``,
``.note`` are available individually.
"""

from __future__ import annotations

import re

# "Schritt 1:", "1.", "Schritt 3 -" at the start of an instruction, optionally
# wrapped in bold by markdown.
_STEP_NUMBER = re.compile(
    r'^\s*(?:\*\*|__)?\s*(?:Schritt|Step)\s*\d+\s*[:.\-–]?\s*(?:\*\*|__)?\s*', re.IGNORECASE)
# Bold text followed by *body* text. The lookahead needs a real character
# after the optional separator, so "**Kochen und essen**" (a whole instruction
# in bold) is not lifted into an empty step. A closing "**" is not body.
_LEADING_BOLD = re.compile(r'^\s*\*\*(?P<title>[^*\n]{2,80})\*\*\s*[:.\-–]?\s*(?=[^\s*])')
_LEADING_HEADING = re.compile(r'^\s*#{1,6}\s+(?P<title>[^\n]{2,80})\n+')

# A title that names an action. Used only to reject captions like "Schritt 1"
# or a title that is really the first sentence of the instruction.
_NOT_A_TITLE = re.compile(r'^\s*(?:Schritt|Step)\s*\d+\s*$', re.IGNORECASE)


def lift_title(instruction: str, name: str = '') -> tuple[str, str]:
    """``(name, instruction)`` with a title the model buried in the text moved out.

    Only runs when ``name`` is empty: a title the model put in the right field
    is left alone, even if the text also repeats it.
    """
    text = (instruction or '').lstrip('\n')
    if name:
        return name, text

    for pattern in (_LEADING_HEADING, _LEADING_BOLD):
        match = pattern.match(text)
        if match:
            candidate = match.group('title').strip().rstrip(':.-– ')
            rest = text[match.end():].strip()
            # A title needs a body to introduce; bold text alone is the whole
            # instruction and lifting it would leave an empty step.
            if rest and candidate and not _NOT_A_TITLE.match(candidate) and len(candidate.split()) <= 8:
                return candidate[:120], rest

    stripped = _STEP_NUMBER.sub('', text, count=1)
    if stripped != text:
        # A bare "Schritt 1:" carries no action, so it is removed and no title
        # is invented from it.
        text = stripped
    return name, text.strip()


def ensure_title(name: str, instruction: str) -> str:
    """A title derived from the instruction when none survived.

    Deliberately mechanical: the first sentence, cut to an imperative phrase.
    Inventing a poetic title is the model's job; this is the fallback that
    stops a recipe from showing "Schritt 1" over seven unnamed rows.
    """
    if name:
        return name
    first = re.split(r'(?<=[.!?])\s', (instruction or '').strip(), maxsplit=1)[0]
    first = re.sub(r'^(?:Den|Die|Das|Der|Dem)\s+', '', first)
    first = first.rstrip('.,;:')
    words = first.split()
    if not words:
        return ''
    return ' '.join(words[:6])[:120]


def _placeholder(index: int) -> str:
    return '{{ ingredients[%d] }}' % index


# Words that legitimately sit between an amount and the food: units, not
# conjunctions. An earlier, generic \w{1,12} ate the "und" between two
# ingredients, so "Mehl und Zucker" became "<ph> <ph>".
_UNIT_WORDS = (
    'g', 'kg', 'mg', 'ml', 'l', 'cl', 'dl', 'tl', 'el', 'stk', 'st', 'stück',
    'gramm', 'kilogramm', 'milliliter', 'liter', 'teelöffel', 'esslöffel',
    'prise', 'prisen', 'bund', 'zehe', 'zehen', 'päckchen', 'pkg', 'dose',
    'dosen', 'becher', 'tasse', 'tassen', 'scheibe', 'scheiben', 'stange',
    'stangen', 'blätter', 'blatt', 'handvoll', 'dash', 'spritzer', 'schuss',
)


def insert_placeholders(instruction: str, ingredients: list[dict]) -> str:
    """Replace the first mention of each ingredient's food with a placeholder.

    ``ingredients`` are the step's ingredient dicts as built by ``shaping``,
    in the order Tandoor will store them, because the reference is positional.
    Group headers are skipped: they render as a section title, not a food.

    Longest name first, so ``Vollkornweizenmehl`` matches before ``Weizenmehl``.
    One replacement per ingredient per step: a sentence that names butter four
    times should not read as four placeholders.
    """
    text = instruction or ''
    if not text:
        return text

    entries = []
    for index, ingredient in enumerate(ingredients):
        if ingredient.get('is_header'):
            continue
        name = ((ingredient.get('food') or {}).get('name') or '').strip()
        if len(name) < 3:
            continue
        entries.append((index, name))
    entries.sort(key=lambda pair: len(pair[1]), reverse=True)

    consumed: list[tuple[int, int]] = []  # spans already replaced
    for index, name in entries:
        # An amount already written beside the name goes with it: a scalable
        # 450 next to the literal text "450 g" becomes 900 after scaling.
        pattern = re.compile(
            r'(?<![\w{])(?:\d+(?:[.,]\d+)?\s*)?'
            r'(?:(?:' + '|'.join(_UNIT_WORDS) + r')\.?\s+)?'
            + re.escape(name) + r'(?![\w}])',
            re.IGNORECASE)
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in consumed):
                continue
            text = text[:match.start()] + _placeholder(index) + text[match.end():]
            consumed.append((match.start(), match.start() + len(_placeholder(index))))
            break
    return text


def placeholders_are_safe(instruction: str, ingredients: list[dict]) -> tuple[bool, str]:
    """Whether inserting placeholders here would produce a readable sentence.

    Measured 2026-11-14 on Zimtschnecken: the text said "Mehl, Zucker, Salz und
    Kardamom" and the step's ingredient list was ordered differently, so index 2
    pointed at Salz. The rendered sentence would read "Mehl, 0.5 Teelöffel Salz,
    0.5 Teelöffel Kardamom und Kardamom" -- two facts, both wrong, and only
    visible at the stove.

    A placeholder is safe only when every replaced ingredient appears in the
    text in the same order as in the ingredient list, and nothing named in the
    list is missing from the text. Anything else keeps the plain text: a
    sentence with the amount written out is still correct, a sentence with the
    wrong amount is not.
    """
    positions: list[tuple[int, int]] = []
    for index, ingredient in enumerate(ingredients):
        if ingredient.get('is_header'):
            continue
        name = ((ingredient.get('food') or {}).get('name') or '').strip()
        if len(name) < 3:
            continue
        match = re.search(r'(?<![\w{])' + re.escape(name) + r'(?![\w}])', instruction or '', re.IGNORECASE)
        if match is None:
            # The step does not name this ingredient at all, which is normal for
            # a later step that only uses part of the list. It cannot be placed
            # wrong, so it does not block the others.
            continue
        positions.append((match.start(), index))

    ordered = sorted(positions)
    indexes = [index for _pos, index in ordered]
    if indexes != sorted(indexes):
        return False, 'Zutaten stehen im Text in anderer Reihenfolge als in der Liste'
    return True, ''


def named_ingredients(instruction: str, ingredients: list[dict]) -> int:
    """How many distinct ingredients this sentence names.

    Read from the sentence *before* substitution: afterwards the food names are
    gone and only ``{{ ingredients[n] }}`` is left, so counting from the
    finished text always says zero.
    """
    text = instruction or ''
    named = 0
    for ingredient in ingredients or []:
        if ingredient.get('is_header'):
            continue
        name = ((ingredient.get('food') or {}).get('name') or '').strip()
        if len(name) < 3:
            continue
        if re.search(r'(?<![\w{])' + re.escape(name) + r'(?![\w}])', text, re.IGNORECASE):
            named += 1
    return named


def placeholder_state(instruction: str, ingredients: list[dict]) -> str:
    """What became of this step's amounts: ``all``, ``partial`` or ``none``.

    Called on the finished instruction together with the ingredients, and the
    count is taken from the placeholders, because the names are gone by then.

    Measured 2026-11-14 on Zimtschnecken: the plugin refused the placeholders
    and said so only in ``warnings``, so the text read "Mehl" without a number
    and nothing on the page explained why. The household found out at the stove.

    * ``all`` -- every ingredient the step lists carries a placeholder;
    * ``partial`` -- some do, some do not;
    * ``none`` -- none do, which is honest for a step that names no
      ingredient at all.
    """
    text = instruction or ''
    replaced = len(re.findall(r'\{\{\s*ingredients\[\d+\]\s*\}\}', text))
    available = sum(
        1 for ingredient in (ingredients or [])
        if not ingredient.get('is_header')
        and len(((ingredient.get('food') or {}).get('name') or '').strip()) >= 3
    )
    if replaced == 0 or available == 0:
        return 'none'
    if replaced >= available:
        return 'all'
    return 'partial'
