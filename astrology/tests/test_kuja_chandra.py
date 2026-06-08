"""Kuja dosham from grahanila is not computed in Django after the EXE bridge refactor."""

import unittest


@unittest.skip('Kuja dosham requires grahanila longitudes; stubbed until EXE provides them.')
class KujaDoshamChandraTests(unittest.TestCase):
    def test_placeholder(self):
        pass


if __name__ == '__main__':
    unittest.main()
