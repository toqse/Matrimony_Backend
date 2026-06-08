"""
Former Prokerala / table-driven porutham regression suite.

Porutham is now Kerala Dashakoot from ``astrology.porutham`` (VB port).
See ``astrology.tests.test_porutham_service``.
"""
import unittest


class PoruthamRegressionPlaceholder(unittest.TestCase):
    @unittest.skip('Legacy regression data targeted Prokerala scoring (removed).')
    def test_skipped(self):
        pass


if __name__ == '__main__':
    unittest.main()
