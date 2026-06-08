"""Legacy Prokerala porutham float-score tests removed; see test_porutham_service."""

import unittest


class ProkeralaPoruthamRegressionTests(unittest.TestCase):
    @unittest.skip('Prokerala koota scoring replaced by VB dashakoot in astrology.porutham.')
    def test_superseded(self):
        pass


if __name__ == '__main__':
    unittest.main()
