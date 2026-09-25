"""Контекст построения раздела: период, клиент ClickHouse и SQL-фрагменты."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Iterable

from ch import Client, dt_bounds, lit, utc_bounds
from periods import Period, Window

# ---------- контур Kixbox в c1_items ----------
WH = "splitByChar(' ', warehouse)[1]"
KIX_WH = f"{WH} IN ('400', '401') AND site != 'Hike'"
IS_SALE = f"(row_type IN ('Товар', 'Услуга') AND {KIX_WH})"
IS_GOODS = f"(row_type = 'Товар' AND {KIX_WH})"
IS_SERVICE = f"(row_type = 'Услуга' AND {KIX_WH})"
IS_RET = f"(row_type = 'Возврат' AND {KIX_WH})"
IS_ORDER = "(row_type = 'Заказ' AND org = 'ООО \"Спейс Джем\"' AND site = 'Копия kixbox')"
IS_ORDER_GOODS = IS_ORDER  # в заказе строки доставки отдельно не приходят
C1_ROWS = "row_type IN ('Заказ', 'Товар', 'Услуга', 'Возврат')"

# Выручка с минусом возвратов на уровне строки — удобна для разрезов по товарам
NET_EXPR = f"multiIf({IS_GOODS}, amount, {IS_RET}, -amount, 0)"
UNITS_NET_EXPR = f"multiIf({IS_GOODS}, qty, {IS_RET}, -qty, 0)"

# Укрупнённые категории по полю ptype
CATEGORY_EXPR = """multiIf(
    ptype ILIKE '%куртк%' OR ptype ILIKE '%пуховик%' OR ptype ILIKE '%парк%' OR ptype ILIKE '%ветровк%'
        OR ptype ILIKE '%бомбер%' OR ptype ILIKE '%пальто%' OR ptype ILIKE '%жилет%' OR ptype ILIKE '%анорак%'
        OR ptype ILIKE '%олимпийк%' OR ptype ILIKE '%дождевик%', 'Верхняя одежда',
    ptype ILIKE '%кроссов%' OR ptype ILIKE '%ботин%' OR ptype ILIKE '%кеды%' OR ptype ILIKE '%клоги%'
        OR ptype ILIKE '%мюли%' OR ptype ILIKE '%лофер%' OR ptype ILIKE '%сандал%' OR ptype ILIKE '%сланц%'
        OR ptype ILIKE '%туфли%' OR ptype ILIKE '%сапог%' OR ptype ILIKE '%слипон%' OR ptype ILIKE '%шлепан%'
        OR ptype ILIKE '%обув%', 'Обувь',
    ptype ILIKE '%толстовк%' OR ptype ILIKE '%худи%' OR ptype ILIKE '%свитер%' OR ptype ILIKE '%джемпер%'
        OR ptype ILIKE '%кардиган%' OR ptype ILIKE '%свитшот%' OR ptype ILIKE '%лонгслив%', 'Худи и трикотаж',
    ptype ILIKE '%футболк%' OR ptype ILIKE '%рубашк%' OR ptype ILIKE '%поло%' OR ptype ILIKE '%майк%'
        OR ptype ILIKE '%топ%' OR ptype ILIKE '%платье%' OR ptype ILIKE '%боди%', 'Верх',
    ptype ILIKE '%джинс%' OR ptype ILIKE '%брюк%' OR ptype ILIKE '%шорт%' OR ptype ILIKE '%юбк%'
        OR ptype ILIKE '%штан%' OR ptype ILIKE '%комбинезон%', 'Низ',
    ptype ILIKE '%кепк%' OR ptype ILIKE '%шапк%' OR ptype ILIKE '%панам%' OR ptype ILIKE '%бейсболк%'
        OR ptype ILIKE '%балаклав%' OR ptype ILIKE '%капюшон-шапк%' OR ptype ILIKE '%шляп%', 'Головные уборы',
    ptype ILIKE '%сумк%' OR ptype ILIKE '%рюкзак%' OR ptype ILIKE '%носки%' OR ptype ILIKE '%ремень%'
        OR ptype ILIKE '%брелок%' OR ptype ILIKE '%ключниц%' OR ptype ILIKE '%кошел%' OR ptype ILIKE '%очки%'
        OR ptype ILIKE '%шарф%' OR ptype ILIKE '%перчат%' OR ptype ILIKE '%значок%' OR ptype ILIKE '%трусы%'
        OR ptype ILIKE '%бутыл%' OR ptype ILIKE '%чехол%' OR ptype ILIKE '%кружк%' OR ptype ILIKE '%украшен%'
        OR ptype ILIKE '%цепоч%' OR ptype ILIKE '%кольц%' OR ptype ILIKE '%браслет%', 'Аксессуары',
    'Прочее')"""

# Город из адреса заказа: первый сегмент до запятой без «г »/«г. »
CITY_EXPR = """multiIf(
    delivery = 'Самовывоз', 'Москва',
    replaceRegexpAll(replaceRegexpAll(trimBoth(splitByChar(',', address)[1]), '^(г\\\\.?\\\\s+|город\\\\s+)', ''), '\\\\s+г$', '') = '', 'Не указан',
    replaceRegexpAll(replaceRegexpAll(trimBoth(splitByChar(',', address)[1]), '^(г\\\\.?\\\\s+|город\\\\s+)', ''), '\\\\s+г$', ''))"""

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass
class Ctx:
    period: Period
    client: Client
    end: date
    freshness: dict[str, Any] = field(default_factory=dict)

    async def q(self, sql: str) -> list[dict[str, Any]]:
        return await self.client.query(sql)

    async def gather(self, *aws: Awaitable[Any]) -> list[Any]:
        return list(await asyncio.gather(*aws))

    # ----- окна -----
    def wins(self, keys: Iterable[str] = ("cur", "prev", "ly")) -> list[Window]:
        by = {w.key: w for w in self.period.windows}
        return [by[k] for k in keys]

    def wexpr(self, dexpr: str, keys: Iterable[str] = ("cur", "prev", "ly")) -> str:
        parts = [
            f"if({dexpr} BETWEEN {lit(w.start)} AND {lit(w.end)}, ['{w.key}'], emptyArrayString())"
            for w in self.wins(keys)
        ]
        return f"arrayJoin(arrayConcat({', '.join(parts)}))"

    def wfilter(self, col: str, kind: str = "date",
                keys: Iterable[str] = ("cur", "prev", "ly")) -> str:
        conds = []
        for w in self.wins(keys):
            if kind == "date":
                conds.append(f"({col} BETWEEN {lit(w.start)} AND {lit(w.end)})")
            elif kind == "datetime":
                a, b = dt_bounds(w.start, w.end)
                conds.append(f"({col} >= {a} AND {col} < {b})")
            elif kind == "utc":
                a, b = utc_bounds(w.start, w.end)
                conds.append(f"({col} >= {a} AND {col} < {b})")
            else:
                raise ValueError(kind)
        return "(" + " OR ".join(conds) + ")"

    def cur_filter(self, col: str, kind: str = "date") -> str:
        return self.wfilter(col, kind, ("cur",))

    def range_filter(self, col: str, start: date, end: date, kind: str = "date") -> str:
        if kind == "date":
            return f"({col} BETWEEN {lit(start)} AND {lit(end)})"
        if kind == "datetime":
            a, b = dt_bounds(start, end)
        else:
            a, b = utc_bounds(start, end)
        return f"({col} >= {a} AND {col} < {b})"

    def bexpr(self, dexpr: str) -> str:
        b = self.period.bucket
        if b == "day":
            return dexpr
        if b == "week":
            return f"toMonday({dexpr})"
        return f"toStartOfMonth({dexpr})"

    @property
    def cur(self) -> Window:
        return self.period.cur

    @property
    def prev(self) -> Window:
        return self.period.prev

    @property
    def ly(self) -> Window:
        return self.period.ly


def by_window(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {"cur": {}, "prev": {}, "ly": {}}
    for r in rows:
        out[r["w"]] = r
    return out


def mb_date(col: str = "firstDateTimeUtc") -> str:
    """Дата по Москве из UTC-поля Mindbox."""
    return f"toDate({col} + INTERVAL 3 HOUR)"


def days_between(a: date, b: date) -> int:
    return (b - a).days + 1


def minus(d: date, n: int) -> date:
    return d - timedelta(days=n)
