from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cookbook', '0243_auto_20261018_1149'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cooklog',
            name='rating',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True),
        ),
    ]
