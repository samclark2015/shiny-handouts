# Generated manually on 2026-01-31
# Removes the deprecated UserSettings model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_settingprofile'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UserSettings',
        ),
    ]
