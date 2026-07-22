from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


def _horoscope_json_default():
    """Referenced by historical migrations only (legacy Horoscope JSON fields)."""
    return {}


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


class HoroscopeProfile(TimeStampedModel):
    """
    Bridge table for Windows EXE horoscope integration.
    EXE reads input fields, writes output fields directly to MySQL.
    db_table matches what client configures in the Windows EXE.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='horoscope_profile',
    )

    # EXE INPUT fields (Windows EXE reads these)
    pr_name = models.CharField(max_length=255, blank=True)
    pr_dob = models.DateField(null=True, blank=True)
    pr_tob = models.TimeField(null=True, blank=True)
    pr_lat = models.FloatField(null=True, blank=True)
    pr_lon = models.FloatField(null=True, blank=True)
    pr_tz = models.FloatField(default=5.5)

    # EXE OUTPUT fields (Windows EXE writes these after calculation)
    pr_rasi = models.CharField(
        max_length=11,
        blank=True,
        help_text='11-char string A-L: each position = planet zodiac sign',
    )
    pr_amsa = models.CharField(max_length=11, blank=True)
    pr_bhav = models.CharField(max_length=11, blank=True)
    pr_star = models.IntegerField(
        null=True,
        blank=True,
        help_text='Nakshatra number 1-27',
    )
    pr_pada = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Nakshatra padam 1-4',
    )
    pr_dasabalance = models.IntegerField(
        null=True,
        blank=True,
        help_text='Sishta dasa balance in days',
    )

    # Derived fields (filled by mark_horoscope_done management command)
    lagnam = models.CharField(max_length=50, blank=True)
    rasi_sign = models.CharField(max_length=50, blank=True)
    star_name = models.CharField(max_length=50, blank=True)
    nakshatra_pada = models.PositiveSmallIntegerField(null=True, blank=True)
    gana = models.CharField(max_length=20, blank=True)
    yoni = models.CharField(max_length=20, blank=True)
    rajju = models.CharField(max_length=20, blank=True)

    # Status tracking
    is_calculated = models.BooleanField(default=False, db_index=True)
    calculated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'horoscope_profile'
        app_label = 'astrology'
        indexes = [
            models.Index(fields=['is_calculated', 'pr_star'], name='horoscope_calc_star_idx'),
            models.Index(fields=['pr_star'], name='horoscope_pr_star_idx'),
        ]

    def get_rasi_array(self):
        """Convert pr_rasi string to list of ints 1-12."""
        if not self.pr_rasi or len(self.pr_rasi) < 11:
            return []
        return [ord(c) - ord('A') + 1 for c in self.pr_rasi[:11]]

    def is_exe_ready(self):
        """True when all EXE input fields are populated."""
        return bool(
            self.pr_dob
            and self.pr_tob
            and self.pr_lat is not None
            and self.pr_lon is not None
        )

    def is_exe_done(self):
        """True when EXE has written output fields."""
        return bool(self.pr_rasi and self.pr_star is not None)

    def __str__(self):
        return f'HoroscopeProfile<{self.user_id}>'


class PoruthamGrade(models.IntegerChoices):
    UTHAMAM = 1, 'Uthamam'
    MADHYAMAM = 2, 'Madhyamam'
    ADHAMAM = 3, 'Adhamam'
    NEECHAM = 4, 'Neecham'


class PoruthamResult(models.Model):
    bride = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='porutham_as_bride',
    )
    groom = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='porutham_as_groom',
    )
    dinam = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    ganam = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    mahendra = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    sthree_deerga = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    yoni = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    rasi = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    rasyadhipam = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    vasyam = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    rajju_dosham = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    vedha_dosham = models.IntegerField(choices=PoruthamGrade.choices, null=True)
    chovva_dosham = models.BooleanField(null=True)
    dasa_sandhi = models.BooleanField(null=True)
    bride_papatha = models.FloatField(null=True)
    groom_papatha = models.FloatField(null=True)
    total_porutham_count = models.IntegerField(default=0)
    uthamam_count = models.IntegerField(default=0)
    madhyamam_count = models.IntegerField(default=0)
    adhamam_count = models.IntegerField(default=0)
    has_dosha = models.BooleanField(default=False)
    overall_result = models.CharField(max_length=20, blank=True)
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'porutham_result'
        app_label = 'astrology'
        unique_together = ('bride', 'groom')

    def __str__(self):
        return f'{self.bride} vs {self.groom} | {self.overall_result}'
