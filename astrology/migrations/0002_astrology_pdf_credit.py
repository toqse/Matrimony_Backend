import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('plans', '0014_transaction_astrology_pdf_types'),
        ('astrology', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AstrologyPdfCredit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'product',
                    models.CharField(
                        choices=[('jathakam', 'Jathakam'), ('thalakuri', 'Thalakuri')],
                        max_length=20,
                    ),
                ),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                (
                    'transaction',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='astrology_pdf_credits',
                        to='plans.transaction',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='astrology_pdf_credits',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'astrology_pdf_credit',
            },
        ),
        migrations.AddConstraint(
            model_name='astrologypdfcredit',
            constraint=models.UniqueConstraint(fields=('transaction',), name='uniq_astrology_pdf_credit_transaction'),
        ),
        migrations.AddIndex(
            model_name='astrologypdfcredit',
            index=models.Index(fields=['user', 'product', 'consumed_at'], name='astrology_pd_user_id_2b8fbd_idx'),
        ),
    ]
