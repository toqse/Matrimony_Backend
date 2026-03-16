# Generated manually for Caste model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Caste',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150)),
                ('is_active', models.BooleanField(default=True)),
                ('religion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='castes', to='master.religion')),
            ],
            options={
                'db_table': 'master_caste',
                'ordering': ['name'],
                'unique_together': {('religion', 'name')},
            },
        ),
    ]
