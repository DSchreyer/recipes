"""Put the Herkunft keywords into cookbook shelves, and fold synonyms.

The picker groups regions like a cookbook: `Herkunft::Mittelmeer::Italien`.
This command owns the data half of that -- the picker already reads both the
old country-only shape and the new shelf path, so running it is safe at any
time and running it twice changes nothing.

Why a command and not a migration: the keyword tree is data the household
maintains, a migration would have to be reversed by hand on a downgrade, and
a rename of 84 rows should be inspectable (--dry-run) before it happens.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled

from cookbook.models import Keyword
from recipes.plugins.kitchen import match

# Synonyms that mean the same thing on a chip. Measured 2026-11-25: no recipe
# carries both spellings, so nothing is lost by folding them.
FOLDS: tuple[tuple[str, str], ...] = (
    ("Beilage::Nudeln", "Beilage::Pasta"),
    ("Beilage::Teig", "Beilage::Brot"),
    ("Aufwand::quick", "Aufwand::Schnell"),
    ("Aufwand::weekend", "Aufwand::Wochenende"),
)


class Command(BaseCommand):
    help = "Rename Herkunft keywords into shelf paths and fold synonym keywords."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="print what would change, write nothing")

    def handle(self, *args, **options):
        dry = bool(options["dry_run"])
        with scopes_disabled():
            renamed = self._rename_regions(dry)
            merged = self._fold(dry)
        prefix = "DRY RUN: " if dry else ""
        self.stdout.write(f"{prefix}{renamed} renamed, {merged} merged")

    def _rename_regions(self, dry: bool) -> int:
        changed = 0
        for keyword in Keyword.objects.filter(name__startswith="Herkunft::").order_by("name"):
            old = keyword.name
            parts = match.herkunft(old)
            if not parts or not parts[0]:
                self.stderr.write(f"  no shelf for {old} (space {keyword.space_id})")
                continue
            shelf, country, region = parts
            target = f"Herkunft::{shelf}::{country}" + (f"::{region}" if region else "")
            if target == old:
                continue
            twin = Keyword.objects.filter(space_id=keyword.space_id, name=target).first()
            if twin is not None:
                self._move(keyword, twin, dry)
            elif not dry:
                keyword.name = target
                keyword.save(update_fields=["name"])
            self.stdout.write(f"  {old} -> {target}")
            changed += 1
        return changed

    def _fold(self, dry: bool) -> int:
        changed = 0
        for source_name, target_name in FOLDS:
            for source in list(Keyword.objects.filter(name=source_name)):
                target = Keyword.objects.filter(
                    space_id=source.space_id, name=target_name
                ).first()
                if target is None:
                    if not dry:
                        source.name = target_name
                        source.save(update_fields=["name"])
                    self.stdout.write(f"  {source_name} -> {target_name}")
                else:
                    self._move(source, target, dry)
                changed += 1
        return changed

    def _move(self, source: Keyword, target: Keyword, dry: bool) -> None:
        """Move every recipe from one keyword to another, then drop the source."""
        recipes = list(source.recipe_set.all())
        if not dry:
            for recipe in recipes:
                recipe.keywords.add(target)
            source.delete()
        self.stdout.write(f"  {source.name} -> {target.name} ({len(recipes)} recipes)")
