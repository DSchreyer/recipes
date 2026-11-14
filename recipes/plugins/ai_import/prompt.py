"""The prompt sent to the household's AI provider.

Written in German because the library is German, and because the rules below
were learned the hard way: the existing import contract
(``docs/tandoor-import-contract.md`` in Atlas) records every one of them as a
defect that reached a recipe page at least once.

The model is asked for one JSON object and nothing else. The call itself uses
``response_format: json_object`` and Tandoor's own LiteLLM wrapper, so the
provider, the key and the credit accounting are Tandoor's, not this plugin's.
"""

from __future__ import annotations

SYSTEM = """Du bist Koch und Redakteur für eine deutsche Rezeptdatenbank.

Du bekommst entweder den Text einer Rezeptseite, eine freie Beschreibung oder
beides. Antworte ausschließlich mit einem JSON-Objekt, ohne Erklärungen.

Erfinde nichts, was nicht in der Quelle steht. Was nicht dasteht, bleibt null.
Lieber ein Feld leer als eine plausibel klingende Zahl.

Deutsch, du-Form ist nicht nötig: schreibe sachlich und knapp."""

SCHEMA = """Antwortformat:

{
  "name": "Name des Gerichts, wie man es ausspricht",
  "description": "Ein bis drei Sätze: was das ist und was es besonders macht.",
  "servings": 4,
  "servings_text": "",
  "working_time": 30,
  "waiting_time": 20,
  "steps": [
    {
      "name": "Kurzer Titel, eine Tätigkeit",
      "instruction": "Fließtext, was passiert und warum.",
      "ingredients": [
        {"amount": 200, "unit": "g", "food": "Spaghetti", "note": ""},
        {"amount": 0, "unit": "", "food": "", "note": "Für die Sauce", "is_header": true, "no_amount": true}
      ]
    }
  ],
  "tags": ["Herkunft::Italien", "Rezepttyp::Pasta", "Aufwand::Schnell"]
}

Arbeitszeit (working_time) und Wartezeit (waiting_time) in Minuten, ganzzahlig."""

RULES = """Regeln:

1. name ist das Gericht, nicht der Titel der Website. "Spaghetti Carbonara -
   schnell & einfach" ist ein Seitentitel, "Spaghetti Carbonara" das Gericht.

2. Eine Zutatengruppe ist eine eigene Zeile mit "is_header": true, "no_amount":
   true, "amount": 0, "unit": "" und dem Gruppentitel in "note". Die Zutaten
   der Gruppe stehen in den Schritten danach.

3. Jede Zutat hat genau eine Menge, und sie steht an dem Schritt, an dem die
   Zutat zum ersten Mal gebraucht wird. Kommt dieselbe Zutat später noch einmal
   vor, nenne sie im Text, aber schreibe sie nicht noch einmal als Zutat.

4. Mengen im Fließtext sind verboten. "200 g Spaghetti kochen" wird zu
   "Die Spaghetti bissfest kochen." Sonst lässt sich das Rezept nicht
   hochrechnen.

5. "unit" ist Pflicht, notfalls "". Ohne unit verwirft Tandoor die Zutat.

6. Jeder Schritt hat einen Titel, der eine Tätigkeit nennt ("Guanciale langsam
   auslassen"), keine Nummer. Der Text erklärt, was passiert und warum, nicht
   nur welche Handgriffe zu tun sind.

7. "food" ist der reine Zutatenname, ohne Menge und ohne Einheit, im
   Nominativ Singular und in der Schreibweise der Liste unten, wenn vorhanden
   ("Ei", nicht "Eier"). Erfinde keine neuen Namen für bekannte Dinge.

8. "unit" ebenfalls in der Schreibweise der Liste unten, wenn vorhanden.

9. "tags" nur aus der Liste unten. Wenn keine passt, lass den Tag weg.
   Höchstens sechs. Nie einen neuen Tag erfinden."""


def build_messages(source: str, *, source_kind: str, known_foods: list[str],
                   known_units: list[str], known_tags: list[str], language: str = 'de',
                   custom_prompt: str = '') -> list[dict]:
    """Prompt messages for one import.

    ``known_*`` are the space's own vocabulary. They are passed as a
    newline-separated list rather than JSON so a long food list costs few
    tokens; 700 foods fit comfortably next to the recipe text.

    ``custom_prompt`` is the space's own extra instruction. It is appended
    after the rules rather than mixed into them, because the rules are what
    stop invented amounts and dropped units -- a preference field must not be
    able to delete them. It is placed last so it is the most recent
    instruction the model reads.
    """
    kind = 'Rezeptseite' if source_kind == 'url' else 'Beschreibung des Gerichts'
    user = '\n'.join([
        SCHEMA,
        RULES,
        f'Bekannte Zutaten ({len(known_foods)}):\n' + ', '.join(sorted(known_foods)),
        f'Bekannte Einheiten:\n' + ', '.join(sorted(known_units)),
        f'Erlaubte Tags:\n' + '\n'.join(sorted(known_tags)),
        f'Ausgabe-Sprache: {language}',
        *([f'Zusätzliche Anweisungen des Haushalts (gehen den Regeln oben vor, wo sie '
           f'sich auf Stil und Kürze beziehen, aber nicht bei Punkt 3 bis 6):\n{custom_prompt.strip()}']
          if (custom_prompt or '').strip() else []),
        f'Quelle ({kind}):',
        source,
    ])
    return [
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': user},
    ]
