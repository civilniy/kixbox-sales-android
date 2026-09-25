import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from periods import bucket_keys, resolve  # noqa: E402


class PeriodsTest(unittest.TestCase):
    def test_mtd(self):
        p = resolve("mtd", date(2026, 9, 23))
        self.assertEqual((p.cur.start, p.cur.end), (date(2026, 9, 1), date(2026, 9, 23)))
        self.assertEqual((p.prev.start, p.prev.end), (date(2026, 8, 1), date(2026, 8, 23)))
        self.assertEqual((p.ly.start, p.ly.end), (date(2025, 9, 1), date(2025, 9, 23)))
        self.assertEqual(p.bucket, "day")

    def test_mtd_31(self):
        p = resolve("mtd", date(2026, 3, 31))
        self.assertEqual(p.prev.end, date(2026, 2, 28))

    def test_last_month(self):
        p = resolve("last_month", date(2026, 9, 23))
        self.assertEqual((p.cur.start, p.cur.end), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual((p.prev.start, p.prev.end), (date(2026, 7, 1), date(2026, 7, 31)))

    def test_rolling(self):
        p = resolve("7d", date(2026, 9, 23))
        self.assertEqual((p.cur.start, p.prev.end), (date(2026, 9, 17), date(2026, 9, 16)))
        self.assertEqual(p.ly.end, date(2025, 9, 24))

    def test_ytd(self):
        p = resolve("ytd", date(2026, 9, 23))
        self.assertTrue(p.prev_is_ly)
        self.assertEqual(p.bucket, "month")
        self.assertEqual(len(bucket_keys(p.cur, p.bucket)), 9)

    def test_qtd(self):
        p = resolve("qtd", date(2026, 9, 23))
        self.assertEqual(p.cur.start, date(2026, 7, 1))
        self.assertEqual(p.prev.start, date(2026, 4, 1))
        self.assertLessEqual(p.prev.end, date(2026, 6, 30))
        self.assertEqual(p.bucket, "week")

    def test_weeks_cover(self):
        p = resolve("90d", date(2026, 9, 23))
        keys = bucket_keys(p.cur, "week")
        self.assertLessEqual(keys[0], p.cur.start)
        self.assertEqual(keys[0].weekday(), 0)


if __name__ == "__main__":
    unittest.main()
