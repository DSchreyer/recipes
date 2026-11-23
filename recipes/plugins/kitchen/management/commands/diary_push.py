"""``manage.py diary-push`` -- the day's meal plan into the calorie diary.

The cook log pushes itself (``apps.KitchenConfig.ready``); a *plan* has no such
moment. This command makes one: it walks the ``MealPlan`` rows that start on a
day and posts each planned recipe the same way a cook is posted -- same
transport, same inert-without-key behaviour, same ``source_id`` idempotency
(``mealplan:<pk>``).
"""

from __future__ import annotations

from datetime import date

from cookbook.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_scopes import scopes_disabled

from recipes.plugins.kitchen import diary


class Command(BaseCommand):
    help = "Push the day's planned recipes to SparkyFitness as planned food entries."

    def add_arguments(self, parser):
        parser.add_argument('--date', default='', help='Day to push, YYYY-MM-DD (default: today).')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Resolve and print the entries; write nothing to the diary.',
        )
        parser.add_argument(
            '--user', default='',
            help='Tandoor username whose diary receives the entries (default: whoever planned the meal).',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Send even if this process already pushed the same plan.',
        )

    def handle(self, *args, **options):
        day = _day(options['date'])
        target = _user(options['user'])
        plans = diary.plan_rows(day)

        if not diary.enabled():
            # The deployed default: say what the plan holds, send nothing.
            self.stdout.write(
                self.style.WARNING(
                    'diary: inert -- SPARKY_FITNESS_API_KEY is unset; nothing was sent.'
                )
            )
            for plan in plans:
                self.stdout.write(f'  {_stamp(plan)}  {plan.get_label()}')
            return

        if not plans:
            self.stdout.write(f'No meals planned for {day.isoformat()}.')
            return

        sent = failed = 0
        for plan in plans:
            payload = diary.push_plan(
                plan, user=target, dry_run=options['dry_run'], force=options['force'],
            )
            if payload is None:
                failed += 1
                self.stdout.write(self.style.WARNING(f'  {plan.get_label()}: not pushed (see log)'))
            elif options['dry_run']:
                sent += 1
                self.stdout.write(f'  {plan.get_label()}:')
                self.stdout.write(f'    {diary.describe(payload)}')
            else:
                sent += 1
                self.stdout.write(
                    f'  {plan.get_label()}: {payload["entry_date"]} '
                    f'{payload["meal_type"]} {payload.get("calories", "?")} kcal'
                )

        verb = 'would push' if options['dry_run'] else 'pushed'
        self.stdout.write(f'{verb} {sent} of {len(plans)} planned meals for {day.isoformat()}'
                          + (f', {failed} failed' if failed else '') + '.')


def _day(raw: str) -> date:
    if not raw:
        return timezone.localdate()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(f'--date needs YYYY-MM-DD, got "{raw}"') from exc


def _user(raw: str):
    if not raw:
        return None
    with scopes_disabled():
        user = User.objects.filter(username__iexact=raw).first()
    if user is None:
        raise CommandError(f'no Tandoor user called "{raw}"')
    return user


def _stamp(plan) -> str:
    return timezone.localtime(plan.from_date).strftime('%Y-%m-%d %H:%M')
