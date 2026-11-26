from django.core.validators import MaxLengthValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_import', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiimportsettings',
            name='wish_prompt',
            field=models.TextField(
                blank=True, default='',
                help_text='Hauptprompt für Rezeptwünsche. Leer heißt: der eingebaute. '
                          'Antwortformat, Regeln und Wortlisten kommen immer dazu.',
                validators=[MaxLengthValidator(4000)],
            ),
        ),
    ]
