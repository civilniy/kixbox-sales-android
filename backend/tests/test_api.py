"""API целиком: авторизация, мета, раздел — на локальном ClickHouse (chdb)."""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SALES_API_TOKEN"] = "test-token"
os.environ["WARMUP"] = "0"

import main  # noqa: E402

try:
    from tests.fixtures import ChdbClient
    HAVE_CHDB = True
except Exception:  # noqa: BLE001
    HAVE_CHDB = False


@unittest.skipUnless(HAVE_CHDB, "chdb не установлен")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.SETTINGS = main.SETTINGS.__class__()  # перечитать токен из окружения
        cls.svc = main.Service(ChdbClient())

    def test_freshness(self):
        fresh = asyncio.run(self.svc.freshness(force=True))
        self.assertIn("end", fresh)
        self.assertEqual(len(fresh["sources"]), 9)

    def test_section_cached(self):
        a = asyncio.run(self.svc.section("overview", "7d"))
        self.assertIsNone(a["error"])
        self.assertTrue(a["widgets"])
        b = asyncio.run(self.svc.section("overview", "7d"))
        self.assertIs(a, b)

    def test_auth(self):
        from fastapi import HTTPException
        main.SETTINGS = type(main.SETTINGS)(api_token="test-token")
        with self.assertRaises(HTTPException):
            main.auth("Bearer wrong")
        main.auth("Bearer test-token")


if __name__ == "__main__":
    unittest.main()
