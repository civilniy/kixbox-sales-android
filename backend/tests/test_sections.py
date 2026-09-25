"""Каждый раздел × каждый период на локальном ClickHouse (chdb) с проверкой формы виджетов."""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from context import Ctx  # noqa: E402
from periods import PRESET_KEYS, resolve  # noqa: E402
from sections import SECTIONS  # noqa: E402

try:
    from tests.fixtures import ChdbClient
    HAVE_CHDB = True
except Exception:  # noqa: BLE001
    HAVE_CHDB = False

FORMATS = {"money", "int", "pct", "dec1", "dec2", "days", "sec", "text"}
TYPES = {"kpis", "hero", "chart", "table", "share", "heatmap", "funnel", "insights", "note", "header"}


def check_number(v, where):
    if v is None or isinstance(v, str):
        return
    assert isinstance(v, (int, float)), f"{where}: {type(v)}"
    assert not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))), f"{where}: {v}"


def validate(widget: dict, where: str) -> None:
    t = widget.get("type")
    assert t in TYPES, f"{where}: type {t}"
    if t == "kpis":
        for it in widget["items"]:
            assert it["format"] in FORMATS, f"{where}: {it}"
            check_number(it["value"], f"{where}/{it['label']}")
    elif t == "chart":
        n = len(widget["x"])
        assert widget["series"], f"{where}: empty series"
        for s in widget["series"]:
            assert len(s["values"]) == n, f"{where}: {s['name']} {len(s['values'])} != {n}"
            assert s["format"] in FORMATS
            for v in s["values"]:
                check_number(v, where)
    elif t == "table":
        n = len(widget["columns"])
        for c in widget["columns"]:
            assert c["format"] in FORMATS, f"{where}: {c}"
        for r in widget["rows"]:
            assert len(r) == n, f"{where}: row {len(r)} != {n}: {r}"
            for v in r:
                check_number(v, where)
    elif t == "heatmap":
        assert len(widget["values"]) == len(widget["y"]), where
        for row in widget["values"]:
            assert len(row) == len(widget["x"]), where
    elif t == "share":
        assert widget["format"] in FORMATS
    json.dumps(widget, ensure_ascii=False, allow_nan=False)


@unittest.skipUnless(HAVE_CHDB, "chdb не установлен")
class SectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = ChdbClient()

    def run_section(self, mod, preset, end=date(2026, 9, 23)):
        ctx = Ctx(period=resolve(preset, end), client=self.client, end=end)
        return asyncio.run(mod.build(ctx))

    def test_all_sections_all_periods(self):
        for mod in SECTIONS:
            for preset in PRESET_KEYS:
                with self.subTest(section=mod.ID, period=preset):
                    widgets = self.run_section(mod, preset)
                    self.assertTrue(widgets, f"{mod.ID}/{preset}: пусто")
                    for i, w in enumerate(widgets):
                        validate(w, f"{mod.ID}/{preset}#{i}")

    def test_month_start_edge(self):
        for mod in SECTIONS:
            with self.subTest(section=mod.ID):
                self.run_section(mod, "mtd", date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
