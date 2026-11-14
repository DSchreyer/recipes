"""Per-space switches for the AI import.

One row per space, created on demand. A space without a row behaves exactly
like the plugin did before settings existed, so an upgrade changes nothing
until someone opens *Settings → Space → AI Import* and presses a switch.

The reason this is a table and not environment variables: the household wants
new users to be able to turn a feature off without a redeploy, and an operator
should not need to know that a compose file exists.
"""

from __future__ import annotations

from django.core.validators import MaxLengthValidator
from django.db import models


class AiImportSettings(models.Model):
    """What one space wants the import to do.

    ``custom_prompt`` is appended to the built-in rules, never replacing them.
    The rules that stop invented amounts and dropped units are not a
    preference, and a text field that could delete them is a footgun dressed
    as configuration.
    """

    space = models.OneToOneField('cookbook.Space', on_delete=models.CASCADE,
                                 related_name='ai_import_settings')

    # Insert `{{ ingredients[n] }}` where a step names one of its ingredients.
    placeholders_enabled = models.BooleanField(
        default=True,
        help_text='Mengen als Template-Platzhalter in den Schrittanweisungen; '
                  'sie skalieren dann mit den Portionen.',
    )
    # Take the page's own photos into the draft so the editor can pick one.
    images_enabled = models.BooleanField(
        default=True,
        help_text='Bilder der Seite als Fotoauswahl anbieten.',
    )
    # Lift a step title the model wrote into the text back into the title field.
    enforce_step_titles = models.BooleanField(
        default=True,
        help_text='Schritttitel aus dem Anweisungstext zurück in das Titelfeld heben.',
    )

    custom_prompt = models.TextField(
        blank=True, default='',
        validators=[MaxLengthValidator(2000)],
        help_text='Zusätzliche Anweisungen an das Modell, z. B. "Kürzer, keine Floskeln". '
                  'Die eingebauten Regeln bleiben daneben bestehen.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('space_id',)
        verbose_name = 'AI Import settings'
        verbose_name_plural = 'AI Import settings'

    def __str__(self):
        return f'AI Import settings for {self.space}'


DEFAULTS = {
    'placeholders_enabled': True,
    'images_enabled': True,
    'enforce_step_titles': True,
    'custom_prompt': '',
}


class _UnsavedSettings:
    """What a space uses before anyone opened the settings page."""

    placeholders_enabled = True
    images_enabled = True
    enforce_step_titles = True
    custom_prompt = ''
    pk = None


def settings_for(space):
    """The row for ``space``, or an in-memory default.

    Reading must never create rows: a GET from the settings page would
    otherwise write to the database, and a space that never uses the import
    would still grow a table entry.
    """
    row = AiImportSettings.objects.filter(space=space).first()
    return row or _UnsavedSettings()
