# Data migration: seed 3 plans for testing (Special Offer, Silver, Gold)

from decimal import Decimal
from django.db import migrations


def seed_three_plans(apps, schema_editor):
    Plan = apps.get_model('plans', 'Plan')
    plans_data = [
        {
            'name': 'Special Offer',
            'price': Decimal('499'),
            'duration_days': 30,
            'profile_view_limit': 6,
            'interest_limit': 6,
            'chat_limit': 6,
            'horoscope_match_limit': 6,
            'contact_view_limit': 6,
            'description': 'Quick trial plan',
            'is_active': True,
        },
        {
            'name': 'Silver',
            'price': Decimal('999'),
            'duration_days': 90,
            'profile_view_limit': 15,
            'interest_limit': 15,
            'chat_limit': 15,
            'horoscope_match_limit': 15,
            'contact_view_limit': 15,
            'description': 'Perfect to get started',
            'is_active': True,
        },
        {
            'name': 'Gold',
            'price': Decimal('1499'),
            'duration_days': 180,
            'profile_view_limit': 30,
            'interest_limit': 30,
            'chat_limit': 30,
            'horoscope_match_limit': 30,
            'contact_view_limit': 30,
            'description': 'Most popular choice',
            'is_active': True,
        },
    ]
    for data in plans_data:
        Plan.objects.get_or_create(
            name=data['name'],
            defaults=data,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0002_plan_price_service_charge_transaction_userplan_extras'),
    ]

    operations = [
        migrations.RunPython(seed_three_plans, noop),
    ]
