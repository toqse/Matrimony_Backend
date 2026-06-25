"""Ground-truth tests for Jyothishadeepti Thalakuri paragraph fields."""
from datetime import date, time
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from astrology.thalakkuri_calc import (
    _format_dasa_ml,
    _format_tob_ml,
    _gana_ml,
    _gender_ml,
    _kollavarsham_date,
    _pada_ordinal_ml,
    _saka_date,
    calculate_all,
)


class ThalakkuriCalendarTests(SimpleTestCase):
    def test_saka_date_april_20_2001(self):
        dob = date(2001, 4, 20)
        year, month, day = _saka_date(dob)
        self.assertEqual(year, 1923)
        self.assertEqual(month, 'ചൈത്രം')
        self.assertEqual(day, 30)

    def test_pada_ordinal(self):
        self.assertEqual(_pada_ordinal_ml(2), 'ദ്വിതീയ')

    def test_gana_manushya_for_pooruruttathi(self):
        self.assertEqual(_gana_ml('Manusha', 25), 'മനുഷ്യ')
        self.assertEqual(_gana_ml('', 25), 'മനുഷ്യ')

    def test_gender_ml(self):
        self.assertEqual(_gender_ml('F'), 'സ്ത്രീജനം')
        self.assertEqual(_gender_ml('M'), 'പുരുഷജനം')

    def test_tob_ml_morning(self):
        self.assertEqual(_format_tob_ml(time(9, 0)), 'പകൽ 9മ')

    def test_dasa_ml_format(self):
        # 9y 5m 10d ≈ 3450 days (approximate)
        from astrology.charts import format_dasa_balance
        # Use a known balance from EXE ground truth if available
        result = _format_dasa_ml(3450)
        self.assertIn('വ', result)
        self.assertIn('മാ', result)
        self.assertIn('ദിവസ', result)


class ThalakkuriCalculateAllTests(SimpleTestCase):
    """Integration test using reference birth: Radhs, 2001-04-20 09:00, Ernakulam."""

    def _make_hp(self, dasabalance=3450):
        hp = MagicMock()
        hp.pr_name = 'Radhs'
        hp.pr_dob = date(2001, 4, 20)
        hp.pr_tob = time(9, 0)
        hp.pr_lat = 10.0
        hp.pr_lon = 76.25
        hp.pr_tz = 5.5
        hp.pr_rasi = 'BABABABABAB'  # placeholder 11 chars
        hp.pr_amsa = 'BABABABABAB'
        hp.pr_bhav = 'BABABABABAB'
        hp.pr_star = 25  # Pooruruttathi
        hp.pr_pada = 2
        hp.pr_dasabalance = dasabalance
        hp.gana = 'Manusha'
        return hp

    def test_calculate_all_season_vasantha(self):
        ctx = calculate_all(self._make_hp(), gender='F')
        self.assertEqual(ctx['season'], 'വസന്ത')
        self.assertEqual(ctx['kollam_year'], 1176)
        self.assertEqual(ctx['kollam_month'], 'മേടം')
        self.assertEqual(ctx['saka_year'], 1923)
        self.assertEqual(ctx['saka_month'], 'ചൈത്രം')
        self.assertEqual(ctx['saka_day'], 30)
        self.assertEqual(ctx['gana_ml'], 'മനുഷ്യ')
        self.assertEqual(ctx['gender_ml'], 'സ്ത്രീജനം')
        self.assertEqual(ctx['star_pada_ml'], 'ദ്വിതീയ')

    def test_kollavarsham_medam_day(self):
        import swisseph as swe
        from astrology.thalakkuri_calc import _get_jd, EPHE_PATH

        swe.set_ephe_path(EPHE_PATH)
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        dob = date(2001, 4, 20)
        jd = _get_jd(dob, time(9, 0), 5.5)
        ayan = swe.get_ayanamsa_ut(jd)
        year, month, day = _kollavarsham_date(dob, jd, ayan)
        self.assertEqual(year, 1176)
        self.assertEqual(month, 'മേടം')
        self.assertGreaterEqual(day, 5)
        self.assertLessEqual(day, 10)

    def test_paragraph_fields_present(self):
        ctx = calculate_all(self._make_hp(), gender='F')
        for key in (
            'sun_rasi_phrase', 'guru_rasi_phrase', 'lagna_degree_ml',
            'tob_ml', 'dasa_display_ml', 'dinantham', 'greg_month_ml',
        ):
            self.assertIn(key, ctx)
            self.assertTrue(ctx[key])
