from django.test import SimpleTestCase

from astrology.charts import (
    build_horoscope_charts,
    dasa_lord,
    decode_chart,
    format_dasa_balance,
)
from astrology.models import HoroscopeProfile
from astrology.serializers import HoroscopeProfileSerializer


class DecodeChartTests(SimpleTestCase):
    JOSEPH_RASI = 'BHEJGAFADJC'
    JOSEPH_AMSA = 'DGDLBAFFGAL'
    JOSEPH_BHAV = 'BHEJGLFADJC'

    def test_decode_joseph_rasi_placements(self):
        chart = decode_chart(self.JOSEPH_RASI)
        houses = chart['houses']

        self.assertEqual(chart['lagna_sign'], 2)
        self.assertEqual([p['key'] for p in houses['1']], ['ju', 'sa'])
        self.assertEqual([p['key'] for p in houses['2']], ['la'])
        self.assertEqual([p['key'] for p in houses['3']], ['md'])
        self.assertEqual([p['key'] for p in houses['4']], ['ra'])
        self.assertEqual([p['key'] for p in houses['5']], ['mo'])
        self.assertEqual([p['key'] for p in houses['6']], ['ve'])
        self.assertEqual([p['key'] for p in houses['7']], ['me'])
        self.assertEqual([p['key'] for p in houses['8']], ['su'])
        self.assertEqual(houses['9'], [])
        self.assertEqual([p['key'] for p in houses['10']], ['ma', 'ke'])
        self.assertEqual(houses['11'], [])
        self.assertEqual(houses['12'], [])

    def test_rahu_ketu_opposition(self):
        for encoded in (self.JOSEPH_RASI, self.JOSEPH_AMSA, self.JOSEPH_BHAV):
            planets = decode_chart(encoded)['planets']
            rahu = next(p for p in planets if p['key'] == 'ra')
            ketu = next(p for p in planets if p['key'] == 'ke')
            diff = (ketu['sign'] - rahu['sign']) % 12
            self.assertEqual(diff, 6, msg=encoded)

    def test_empty_string_returns_empty_houses(self):
        chart = decode_chart('')
        self.assertIsNone(chart['lagna_sign'])
        self.assertEqual(chart['planets'], [])
        for sign in range(1, 13):
            self.assertEqual(chart['houses'][str(sign)], [])

    def test_short_string_returns_empty_houses(self):
        chart = decode_chart('ABC')
        self.assertIsNone(chart['lagna_sign'])
        self.assertEqual(chart['planets'], [])

    def test_sign_names_present(self):
        chart = decode_chart(self.JOSEPH_RASI)
        self.assertEqual(chart['sign_names']['1'], 'Medam')
        self.assertEqual(chart['sign_names']['12'], 'Meenam')


class DasaTests(SimpleTestCase):
    def test_dasa_lord_makam_is_ketu(self):
        self.assertEqual(dasa_lord(10), 'Ketu')

    def test_dasa_lord_invalid_star(self):
        self.assertEqual(dasa_lord(None), '')
        self.assertEqual(dasa_lord(0), '')
        self.assertEqual(dasa_lord(28), '')

    def test_format_dasa_balance_491(self):
        result = format_dasa_balance(491)
        self.assertEqual(result['years'], 1)
        self.assertEqual(result['months'], 4)
        self.assertEqual(result['days'], 4)
        self.assertEqual(result['balance_text'], '01y 04m 04d')

    def test_format_dasa_balance_2459_matches_exe(self):
        result = format_dasa_balance(2459)
        self.assertEqual(result['years'], 6)
        self.assertEqual(result['months'], 8)
        self.assertEqual(result['days'], 25)
        self.assertEqual(result['balance_text'], '06y 08m 25d')

    def test_format_dasa_balance_none(self):
        result = format_dasa_balance(None)
        self.assertEqual(result['balance_text'], '')


class BuildHoroscopeChartsTests(SimpleTestCase):
    def test_build_horoscope_charts(self):
        hp = HoroscopeProfile(
            pr_rasi='BHEJGAFADJC',
            pr_amsa='DGDLBAFFGAL',
            pr_bhav='BHEJGLFADJC',
            pr_star=10,
            pr_pada=4,
            pr_dasabalance=491,
        )
        charts = build_horoscope_charts(hp)

        self.assertEqual(charts['star']['number'], 10)
        self.assertEqual(charts['star']['name'], 'Makam')
        self.assertEqual(charts['star']['pada'], 4)
        self.assertEqual(charts['dasa']['lord'], 'Ketu')
        self.assertEqual(charts['dasa']['balance_days'], 491)
        self.assertEqual(charts['dasa']['balance_text'], '01y 04m 04d')
        self.assertEqual(charts['rasi']['lagna_sign'], 2)
        self.assertEqual(charts['amsa']['lagna_sign'], 4)
        self.assertEqual(charts['bhava']['lagna_sign'], 2)


class HoroscopeProfileSerializerChartsTests(SimpleTestCase):
    def test_serializer_includes_charts(self):
        hp = HoroscopeProfile(
            id=1842,
            pr_rasi='BHEJGAFADJC',
            pr_amsa='DGDLBAFFGAL',
            pr_bhav='BHEJGLFADJC',
            pr_star=10,
            pr_pada=4,
            pr_dasabalance=491,
        )
        data = HoroscopeProfileSerializer(hp).data

        self.assertIn('charts', data)
        self.assertEqual(data['charts']['dasa']['lord'], 'Ketu')
        self.assertEqual(data['charts']['dasa']['balance_text'], '01y 04m 04d')
        self.assertEqual(data['charts']['rasi']['houses']['10'][0]['key'], 'ma')

    def test_serializer_includes_display_fields(self):
        hp = HoroscopeProfile(
            id=7928,
            pr_rasi='AGEEHKGAEKJ',
            pr_star=10,
            pr_pada=1,
            pr_dasabalance=2459,
            lagnam='Medam',
            rasi_sign='Chingam',
            star_name='Makam',
            gana='Asura',
            yoni='Mushika',
            rajju='Kanda',
            nakshatra_pada=1,
            is_calculated=True,
        )
        data = HoroscopeProfileSerializer(hp).data
        self.assertEqual(data['star_display'], 'Makam')
        self.assertEqual(data['lagnam_display'], 'Medam')
        self.assertEqual(data['rasi_display'], 'Chingam')
        self.assertEqual(data['dasa_display'], '06y 08m 25d')
