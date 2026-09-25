"""Розница и вся сеть по Mindbox: магазины, чеки, часы, идентификация покупателей."""
from __future__ import annotations

from ch import lits, num
from config import POINTS_OF_CONTACT, STORE_IDS
from context import WEEKDAYS, Ctx
from sections import common
from widgets import (bucket_caption, chart, col, fill_buckets, heatmap, insight, insights, kpi,
                     kpis, note, rel_delta, safe_div, series, table)

ID = "stores"
TITLE = "Магазины"
ICON = "store"


async def per_store(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {common.mb_orders_cte(ctx)}
SELECT {ctx.wexpr('d')} AS w, poc,
    sum(amt) AS amt, count() AS orders, sum(qty) AS units,
    countIf(cid IS NOT NULL) AS ident, uniqExactIf(cid, cid IS NOT NULL) AS buyers
FROM op
GROUP BY w, poc"""
    return await ctx.q(sql)


async def series_by_store(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))}
SELECT {ctx.bexpr('d')} AS b, poc, sum(amt) AS amt, count() AS orders
FROM op GROUP BY b, poc ORDER BY b"""
    return await ctx.q(sql)


async def hours(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))}
SELECT toHour(ts + INTERVAL 3 HOUR) AS h, toDayOfWeek(d) AS wd, count() AS orders, sum(amt) AS amt
FROM op WHERE poc IN {lits(STORE_IDS)}
GROUP BY h, wd"""
    return await ctx.q(sql)


async def store_weekday(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))}
SELECT poc, toDayOfWeek(d) AS wd, sum(amt) AS amt, uniqExact(d) AS days
FROM op WHERE poc IN {lits(STORE_IDS)}
GROUP BY poc, wd"""
    return await ctx.q(sql)


async def basket_bands(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))}
SELECT multiIf(t.amt < 5000, 1, t.amt < 10000, 2, t.amt < 20000, 3, t.amt < 40000, 4, 5) AS band,
    count() AS orders, sum(t.amt) AS amt
FROM op AS t WHERE t.poc IN {lits(STORE_IDS)}
GROUP BY band ORDER BY band"""
    return await ctx.q(sql)


def _name(poc: str | None) -> tuple[str, str]:
    return POINTS_OF_CONTACT.get(poc or "", ("Прочее", "other"))


async def build(ctx: Ctx) -> list[dict]:
    net, rows, ser, hr, swd, bands = await ctx.gather(
        common.mb_network(ctx), per_store(ctx), series_by_store(ctx), hours(ctx), store_weekday(ctx),
        basket_bands(ctx))
    P = ctx.period
    nc, np_, nl = net["cur"], net["prev"], net["ly"]
    w: list[dict] = [kpis(None, [
        kpi("Выручка сети", nc.get("total"), np_.get("total"), nl.get("total"), period=P),
        kpi("Розничные магазины", nc.get("stores"), np_.get("stores"), nl.get("stores"), period=P),
        kpi("Онлайн kixbox.ru", nc.get("online"), np_.get("online"), nl.get("online"), period=P),
        kpi("Доля розницы", nc.get("retail_share"), np_.get("retail_share"), nl.get("retail_share"),
            fmt="pct", better="none", period=P),
        kpi("Чеков в рознице", nc.get("store_orders"), np_.get("store_orders"), nl.get("store_orders"),
            fmt="int", period=P),
        kpi("Средний чек розницы", nc.get("store_aov"), np_.get("store_aov"), nl.get("store_aov"), period=P),
        kpi("Товаров в чеке", nc.get("store_upt"), np_.get("store_upt"), nl.get("store_upt"), fmt="dec2",
            period=P),
        kpi("Чеки с картой клиента", nc.get("ident"), np_.get("ident"), nl.get("ident"), fmt="pct", period=P,
            hint="Доля розничных чеков, где покупатель опознан в Mindbox"),
    ])]

    agg: dict[str, dict[str, dict]] = {}
    for r in rows:
        name, kind = _name(r.get("poc"))
        if kind == "other_online":
            name, kind = "Другие сайты", "other"
        a = agg.setdefault(name, {"kind": kind}).setdefault(r["w"], {"amt": 0, "orders": 0, "units": 0,
                                                                     "ident": 0})
        for f in ("amt", "orders", "units", "ident"):
            a[f] += num(r[f])
    total = sum(v.get("cur", {}).get("amt", 0) for v in agg.values()) or 1
    trows = []
    for name, v in sorted(agg.items(), key=lambda t: -t[1].get("cur", {}).get("amt", 0)):
        c, p, l = v.get("cur", {}), v.get("prev", {}), v.get("ly", {})
        if not c.get("amt"):
            continue
        trows.append([name, c.get("amt"), c["amt"] / total, rel_delta(c.get("amt"), p.get("amt")),
                      None if P.prev_is_ly else rel_delta(c.get("amt"), l.get("amt")),
                      c.get("orders"), safe_div(c.get("amt"), c.get("orders")),
                      safe_div(c.get("units"), c.get("orders")), safe_div(c.get("ident"), c.get("orders"))])
    w.append(table("Каналы и магазины", [
        col("Точка"), col("Выручка", "money"), col("Доля", "pct", bar=True),
        col("Дин.", "pct", delta=True),
        col("К году", "pct", delta=True), col("Чеки", "int"), col("Чек", "money"),
        col("UPT", "dec2"), col("С картой", "pct"),
    ], trows, collapsed=15, subtitle="Mindbox · позиции без отмен и возвратов"))

    # выводы по магазинам
    stores_only = [r for r in trows if agg[r[0]]["kind"] == "store"]
    ins = []
    if stores_only:
        best = max(stores_only, key=lambda r: r[3] if r[3] is not None else -9)
        worst = min(stores_only, key=lambda r: r[3] if r[3] is not None else 9)
        if best[3] is not None:
            ins.append(insight("good", f"Сильнее всех вырос {best[0]}: {best[3] * 100:+.0f}% {P.prev_name}."))
        if worst[3] is not None and worst is not best:
            ins.append(insight("bad" if worst[3] < 0 else "info",
                               f"Слабее всех {worst[0]}: {worst[3] * 100:+.0f}%."))
        low_ident = [r for r in stores_only if r[8] is not None and r[8] < 0.75]
        if low_ident:
            ins.append(insight("warn", "Мало чеков с картой клиента: " + ", ".join(
                f"{r[0]} {r[8] * 100:.0f}%" for r in low_ident) + " — эти покупатели не попадают в CRM."))
        big_aov = max(stores_only, key=lambda r: r[6] or 0)
        ins.append(insight("info", f"Самый высокий чек — {big_aov[0]}: {num(big_aov[6]):,.0f} ₽".replace(",", " ")
                           + "."))
    if ins:
        w.append(insights("Розница", ins))

    # динамика по каналам
    names = [n for n, v in sorted(agg.items(), key=lambda t: -t[1].get("cur", {}).get("amt", 0))
             if v.get("cur", {}).get("amt")]
    x, _ = fill_buckets(P, [], "b", [])
    series_list = []
    for i, name in enumerate(names[:8]):
        pts = [r for r in ser if (_name(r.get("poc"))[0] == name or
                                  (name == "Другие сайты" and _name(r.get("poc"))[1] == "other_online"))]
        _, vals = fill_buckets(P, pts, "b", ["amt"])
        series_list.append(series(name, vals["amt"], color=i))
    if series_list:
        w.append(chart(f"Выручка по каналам {bucket_caption(P)}", x, series_list, stacked=True,
                       subtitle="Mindbox, ₽"))

    # часы работы
    grid = [[0.0] * 24 for _ in range(7)]
    for r in hr:
        grid[int(r["wd"]) - 1][int(r["h"])] += num(r["orders"])
    hours_used = [h for h in range(24) if any(grid[d][h] for d in range(7))]
    if hours_used:
        lo, hi = min(hours_used), max(hours_used)
        w.append(heatmap("Чеки в магазинах по часам", [str(h) for h in range(lo, hi + 1)], WEEKDAYS,
                         [row[lo:hi + 1] for row in grid], subtitle="Все розничные точки, московское время"))

    # магазин × день недели: средняя выручка дня
    by: dict[str, list] = {}
    for r in swd:
        name = _name(r.get("poc"))[0]
        by.setdefault(name, [None] * 7)[int(r["wd"]) - 1] = safe_div(r["amt"], r["days"])
    if by:
        order = [n for n in names if n in by]
        w.append(heatmap("Средняя выручка дня недели", WEEKDAYS, order, [by[n] for n in order], fmt="money",
                         subtitle="₽ за один такой день периода"))

    if bands:
        labels = {1: "до 5 тыс", 2: "5–10 тыс", 3: "10–20 тыс", 4: "20–40 тыс", 5: "от 40 тыс"}
        w.append(chart("Размер розничного чека", [labels[int(r["band"])] for r in bands], [
            series("Чеков", [r["orders"] for r in bands], fmt="int", color=0),
            series("Выручка", [r["amt"] for r in bands], style="line", axis="right", color=2),
        ], kind="combo"))
    w.append(note("Розница видна только через Mindbox: суммы позиций заказа после скидок и баллов, "
                  "без отменённых и возвращённых позиций. Возврат уменьшает выручку дня покупки. "
                  "Даты переведены из UTC в московское время.", title="Методика"))
    return w
