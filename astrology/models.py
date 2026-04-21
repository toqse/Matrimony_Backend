from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


def _horoscope_json_default():
    return {}


class Horoscope(TimeStampedModel):
    profile = models.OneToOneField(
        'profiles.UserProfile',
        on_delete=models.CASCADE,
        related_name='horoscope',
    )
    date_of_birth = models.DateField()
    time_of_birth = models.TimeField()
    place_of_birth = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()

    lagna = models.CharField(max_length=50)
    rasi = models.CharField(max_length=50)
    nakshatra = models.CharField(max_length=50)
    nakshatra_pada = models.PositiveSmallIntegerField()

    gana = models.CharField(max_length=50)
    yoni = models.CharField(max_length=50)
    nadi = models.CharField(max_length=50)
    rajju = models.CharField(max_length=50)

    grahanila = models.JSONField(default=dict, blank=True)
    janana_shishtam = models.FloatField(blank=True, null=True)
    navamsa_chart = models.JSONField(default=_horoscope_json_default, blank=True, null=True)
    shishta_dasa = models.JSONField(default=_horoscope_json_default, blank=True, null=True)
    birth_input_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = 'astrology_horoscope'
        app_label = 'astrology'

    def __str__(self):
        return f'Horoscope<{self.profile_id}>'


class AstrologyPdfCredit(TimeStampedModel):
    """One successful PDF purchase = one credit; consumed on first PDF download."""

    PRODUCT_JATHAKAM = 'jathakam'
    PRODUCT_THALAKURI = 'thalakuri'
    PRODUCT_CHOICES = [
        (PRODUCT_JATHAKAM, 'Jathakam'),
        (PRODUCT_THALAKURI, 'Thalakuri'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='astrology_pdf_credits',
    )
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    transaction = models.ForeignKey(
        'plans.Transaction',
        on_delete=models.PROTECT,
        related_name='astrology_pdf_credits',
    )
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'astrology_pdf_credit'
        constraints = [
            models.UniqueConstraint(
                fields=['transaction'],
                name='uniq_astrology_pdf_credit_transaction',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'product', 'consumed_at']),
        ]

    def __str__(self):
        return f'AstrologyPdfCredit<{self.user_id} {self.product}>'
