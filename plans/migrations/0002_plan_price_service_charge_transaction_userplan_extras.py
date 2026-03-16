# Generated migration for Plan price, ServiceCharge, Transaction, UserPlan extras

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_service_charges(apps, schema_editor):
    ServiceCharge = apps.get_model('plans', 'ServiceCharge')
    for gender, amount in [('M', Decimal('15000')), ('F', Decimal('1000')), ('O', Decimal('5000'))]:
        ServiceCharge.objects.get_or_create(gender=gender, defaults={'amount': amount})


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('plans', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Plan price (before service charge)', max_digits=12),
        ),
        migrations.AddField(
            model_name='plan',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='horoscope_match_limit',
            field=models.PositiveIntegerField(default=0, help_text='Number of horoscope matches allowed; 0 = unlimited'),
        ),
        migrations.AddField(
            model_name='plan',
            name='contact_view_limit',
            field=models.PositiveIntegerField(default=0, help_text='Number of contact views allowed; 0 = unlimited'),
        ),
        migrations.CreateModel(
            name='ServiceCharge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('gender', models.CharField(choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], max_length=1, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ],
            options={
                'db_table': 'plans_service_charge',
                'ordering': ['gender'],
            },
        ),
        migrations.AddField(
            model_name='userplan',
            name='price_paid',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Plan price at time of purchase', max_digits=12),
        ),
        migrations.AddField(
            model_name='userplan',
            name='service_charge',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Service charge applied at purchase', max_digits=12),
        ),
        migrations.AddField(
            model_name='userplan',
            name='horoscope_used',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='userplan',
            name='contact_views_used',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='userplan',
            name='valid_from',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userplan',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('service_charge', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('payment_method', models.CharField(choices=[('razorpay', 'Razorpay'), ('stripe', 'Stripe'), ('upi', 'UPI'), ('manual', 'Manual (Admin approval)')], default='manual', max_length=20)),
                ('payment_status', models.CharField(choices=[('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='pending', max_length=20)),
                ('transaction_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='plans.plan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'plans_transaction',
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(seed_service_charges, migrations.RunPython.noop),
    ]
