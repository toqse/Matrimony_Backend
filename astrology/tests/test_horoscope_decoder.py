from django.test import SimpleTestCase

from astrology.services.horoscope_decoder import (
    decode_amsa,
    decode_bhava,
    decode_bundle,
    decode_detailed,
    decode_rasi,
)
from astrology.services.horoscope_verification import (
    compare_chart,
    overall_accuracy,
    verify_record,
)

JOSEPH_RASI = 'BHEJGAFADJC'
JOSEPH_AMSA = 'DGDLBAFFGAL'
JOSEPH_BHAV = 'BHEJGLFADJC'


class DecodeRasiTests(SimpleTestCase):
    def test_decode_rasi_houses(self):
        houses = decode_rasi(JOSEPH_RASI)
        self.assertEqual(houses['1'], ['Ju', 'Sa'])
        self.assertEqual(houses['2'], ['La'])
        self.assertEqual(houses['3'], ['Md'])
        self.assertEqual(houses['4'], ['Ra'])
        self.assertEqual(houses['5'], ['Mo'])
        self.assertEqual(houses['6'], ['Ve'])
        self.assertEqual(houses['7'], ['Me'])
        self.assertEqual(houses['8'], ['Su'])
        self.assertEqual(houses['9'], [])
        self.assertEqual(houses['10'], ['Ma', 'Ke'])
        self.assertEqual(houses['11'], [])
        self.assertEqual(houses['12'], [])

    def test_decode_amsa_houses(self):
        houses = decode_amsa(JOSEPH_AMSA)
        self.assertEqual(houses['1'], ['Ju', 'Ke'])
        self.assertEqual(houses['4'], ['La', 'Mo'])
        self.assertEqual(houses['7'], ['Su', 'Ra'])
        self.assertEqual(houses['12'], ['Ma', 'Md'])

    def test_decode_bhava_houses(self):
        houses = decode_bhava(JOSEPH_BHAV)
        self.assertEqual(houses['1'], ['Sa'])
        self.assertEqual(houses['8'], ['Su'])
        self.assertEqual(houses['10'], ['Ma', 'Ke'])
        self.assertEqual(houses['12'], ['Ju'])

    def test_all_houses_present_for_empty(self):
        houses = decode_rasi('')
        self.assertEqual(set(houses.keys()), {str(i) for i in range(1, 13)})
        self.assertTrue(all(v == [] for v in houses.values()))

    def test_short_string_empty(self):
        self.assertTrue(all(v == [] for v in decode_rasi('ABC').values()))

    def test_decode_detailed_planet_signs(self):
        detail = decode_detailed(JOSEPH_RASI)
        self.assertEqual(detail['lagna_sign'], 2)
        self.assertEqual(detail['planets']['Sun']['sign'], 8)
        self.assertEqual(detail['planets']['Moon']['sign'], 5)
        self.assertEqual(detail['planets']['Venus']['sign'], 6)


class DecodeBundleTests(SimpleTestCase):
    def test_bundle_shape(self):
        bundle = decode_bundle(JOSEPH_RASI, JOSEPH_AMSA, JOSEPH_BHAV)
        self.assertEqual(
            set(bundle.keys()),
            {
                'raw_rasi',
                'raw_amsa',
                'raw_bhava',
                'decoded_rasi',
                'decoded_amsa',
                'decoded_bhava',
            },
        )
        self.assertEqual(bundle['raw_rasi'], JOSEPH_RASI)
        self.assertEqual(bundle['raw_amsa'], JOSEPH_AMSA)
        self.assertEqual(bundle['raw_bhava'], JOSEPH_BHAV)
        self.assertEqual(bundle['decoded_rasi']['1'], ['Ju', 'Sa'])
        self.assertEqual(bundle['decoded_amsa']['1'], ['Ju', 'Ke'])
        self.assertEqual(bundle['decoded_bhava']['1'], ['Sa'])

    def test_bundle_verbose_adds_detail(self):
        bundle = decode_bundle(JOSEPH_RASI, JOSEPH_AMSA, JOSEPH_BHAV, verbose=True)
        self.assertIn('detail', bundle)
        self.assertEqual(bundle['detail']['rasi']['lagna_sign'], 2)
        self.assertEqual(bundle['detail']['rasi']['planets']['Sun']['sign'], 8)

    def test_bundle_handles_none(self):
        bundle = decode_bundle(None, None, None)
        self.assertEqual(bundle['raw_rasi'], '')
        self.assertTrue(all(v == [] for v in bundle['decoded_rasi'].values()))


class VerificationTests(SimpleTestCase):
    def test_compare_chart_all_pass(self):
        exe = decode_rasi(JOSEPH_RASI)
        result = compare_chart('rasi', JOSEPH_RASI, exe)
        self.assertTrue(result.passed)
        self.assertEqual(result.accuracy, 100.0)
        self.assertEqual(result.matched, 12)

    def test_compare_chart_detects_mismatch(self):
        exe = decode_rasi(JOSEPH_RASI)
        exe['1'] = ['Sa', 'Ke']  # deliberately wrong house
        result = compare_chart('rasi', JOSEPH_RASI, exe)
        self.assertFalse(result.passed)
        self.assertEqual(result.matched, 11)
        failing = [h for h in result.houses if not h.passed]
        self.assertEqual(len(failing), 1)
        self.assertEqual(failing[0].house, '1')
        self.assertEqual(sorted(failing[0].django), ['Ju', 'Sa'])

    def test_compare_is_order_independent(self):
        exe = decode_rasi(JOSEPH_RASI)
        exe['1'] = ['Sa', 'Ju']  # same set, different order
        result = compare_chart('rasi', JOSEPH_RASI, exe)
        self.assertTrue(result.passed)

    def test_verify_record_full(self):
        record = {
            'id': 1842,
            'pr_rasi': JOSEPH_RASI,
            'pr_amsa': JOSEPH_AMSA,
            'pr_bhav': JOSEPH_BHAV,
            'exe': {
                'rasi': decode_rasi(JOSEPH_RASI),
                'amsa': decode_amsa(JOSEPH_AMSA),
                'bhava': decode_bhava(JOSEPH_BHAV),
            },
        }
        results = verify_record(record)
        self.assertEqual(set(results.keys()), {'rasi', 'amsa', 'bhava'})
        self.assertTrue(all(r.passed for r in results.values()))
        self.assertEqual(overall_accuracy([results]), 100.0)
