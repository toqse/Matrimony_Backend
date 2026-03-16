# Generated manually for UserReligion.caste_fk

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0002_caste'),
        ('profiles', '0002_add_profile_completion_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='userreligion',
            name='caste_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='master.caste'),
        ),
    ]
