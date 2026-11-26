"""Merge keywords that differ only in the path they were created under.

The keyword list grew from two sources: an import that wrote whole paths into
`name` ("Zutaten::Fleisch", "Basis::Zutaten::Fleisch") and leaves created by
hand ("Fleisch"). 46 leaf words therefore exist two to four times, and every
chip row, saved filter and search field shows the same word more than once.

The command groups by leaf name inside one space, keeps the most-used spelling
(shortest name on a tie), moves the recipe links and the ids inside saved custom
filters onto the survivor, then deletes the rest.

    manage.py dedupe_keywords                 # print the plan and the cookbook deltas
    manage.py dedupe_keywords --apply         # do it
"""
import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django_scopes import scopes_disabled

from cookbook.models import CustomFilter, Keyword, Recipe, Space

KEYS = ('keywords_or', 'keywords_and', 'keywords_or_not', 'keywords_and_not')


def leaf(name):
    return name.split('::')[-1].strip().casefold()


def group_key(name):
    """Leaf plus, for a four-part origin path, the country it sits in.

    "Herkunft::Nordamerika::USA::Texas" and "Herkunft::Lateinamerika::Mexiko::Texas"
    share a leaf and are two different places; merging them would move a recipe
    from Mexico to the USA.
    """
    parts = [p.strip().casefold() for p in name.split('::')]
    context = parts[2] if len(parts) >= 4 else ''
    return parts[-1], context


def book_count(space, search):
    """Recipe count of one saved filter, through the same code path the API uses."""
    if not search:
        return None
    qs = Recipe.objects.filter(space=space).by_keywords(
        or_=search.get('keywords_or'),
        and_=search.get('keywords_and'),
        or_not=search.get('keywords_or_not'),
        and_not=search.get('keywords_and_not'),
        include_children=search.get('include_children', True),
    )
    return qs.distinct().count()


class Command(BaseCommand):
    help = 'Merge keywords whose names share a leaf word, and repoint filters.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write the changes')
        parser.add_argument('--space', type=int, default=None, help='only this space')

    def handle(self, *args, **options):
        with scopes_disabled():
            spaces = list(Space.objects.all())
            if options['space']:
                spaces = [s for s in spaces if s.id == options['space']]
            for space in spaces:
                self.do_space(space, options['apply'])

    def do_space(self, space, apply_changes):
        keywords = list(Keyword.objects.filter(space=space))
        if not keywords:
            return
        usage = defaultdict(int)
        for recipe_id, keyword_id in Recipe.keywords.through.objects.filter(
                keyword__space=space).values_list('recipe_id', 'keyword_id'):
            usage[keyword_id] += 1

        groups = defaultdict(list)
        for kw in keywords:
            groups[group_key(kw.name)].append(kw)

        groups = {k: v for k, v in groups.items() if len(v) > 1}
        if not groups:
            self.stdout.write(f'{space.name}: no duplicate leaves, nothing to do')
            return

        mapping = {}
        self.stdout.write(f'\n{space.name}: {len(keywords)} keywords, '
                          f'{len(groups)} leaf words with duplicates\n')
        self.stdout.write(f'{"keep":32} {"merge away":60} recipes\n')
        for word, members in sorted(groups.items()):
            members.sort(key=lambda k: (-usage[k.id], len(k.name), k.id))
            keep, losers = members[0], members[1:]
            for loser in losers:
                mapping[loser.id] = keep.id
            self.stdout.write(
                f'{keep.name[:32]:32} {", ".join(l.name for l in losers)[:60]:60} '
                f'{sum(usage[m.id] for m in members)}\n')

        filters = [f for f in CustomFilter.objects.filter(space=space) if f.search]
        before = {f.id: (f.name, book_count(space, json.loads(f.search))) for f in filters}
        mapped = {f.id: self.remap(json.loads(f.search), mapping) for f in filters}
        after = {f.id: book_count(space, mapped[f.id]) for f in filters}

        changed = [(fid, before[fid][0], before[fid][1], after[fid])
                   for fid in before if before[fid][1] != after[fid]]
        if changed:
            self.stdout.write(f'\n{len(changed)} cookbook(s) change size:\n')
            for fid, name, b, a in sorted(changed, key=lambda r: -(r[3] or 0) + (r[2] or 0)):
                self.stdout.write(f'  {name[:44]:44} {b:3} -> {a:3}  (+{(a or 0) - (b or 0)})\n')
        else:
            self.stdout.write('\nno cookbook changes size\n')

        if not apply_changes:
            self.stdout.write(self.style.WARNING('\ndry run: nothing written, pass --apply'))
            return

        through = Recipe.keywords.through
        with transaction.atomic():
            for word, members in groups.items():
                keep = members[0]
                ids = [m.id for m in members]
                recipe_ids = list(through.objects.filter(keyword_id__in=ids)
                                  .values_list('recipe_id', flat=True).distinct())
                through.objects.filter(keyword_id__in=ids).delete()
                through.objects.bulk_create(
                    [through(recipe_id=r, keyword_id=keep.id) for r in recipe_ids],
                    ignore_conflicts=True)
            for f in filters:
                f.search = json.dumps(mapped[f.id])
                f.save(update_fields=['search'])
            Keyword.objects.filter(id__in=list(mapping.keys())).delete()

        remaining = Keyword.objects.filter(space=space).count()
        self.stdout.write(self.style.SUCCESS(
            f'\napplied: {len(mapping)} keywords merged, {remaining} left'))

    @staticmethod
    def remap(search, mapping):
        out = dict(search)
        for key in KEYS:
            if key in out and isinstance(out[key], list):
                seen, ids = set(), []
                for value in out[key]:
                    value = mapping.get(value, value)
                    if value not in seen:
                        seen.add(value)
                        ids.append(value)
                out[key] = ids
        return out
