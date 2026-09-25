"""Трафик kixbox.ru по сырым визитам Метрики с фактической атрибуцией заказов 1С."""
from __future__ import annotations

from datetime import timedelta

from ch import lit, num
from config import DEVICE_NAMES, FUNNEL_GOALS, TRAFFIC_SOURCE_NAMES
from context import IS_ORDER, Ctx, by_window
from sections import common
from widgets import (bucket_caption, chart, col, fill_buckets, funnel, insight, insights, kpi, kpis,
                     note, rel_delta, safe_div, series, share, table)

ID = "traffic"
TITLE = "Трафик"
ICON = "traffic"

HAS_PURCHASE = "purchase_id NOT IN ('', '[]')"
PAGE_TYPE = """multiIf(
    path(start_url) IN ('', '/'), 'Главная',
    startsWith(path(start_url), '/product/'), 'Карточка товара',
    startsWith(path(start_url), '/collection/'), 'Каталог и коллекции',
    startsWith(path(start_url), '/search'), 'Поиск по сайту',
    startsWith(path(start_url), '/blogs') OR startsWith(path(start_url), '/page/'), 'Контент',
    startsWith(path(start_url), '/client_account') OR startsWith(path(start_url), '/orders'), 'Личный кабинет',
    startsWith(path(start_url), '/cart') OR startsWith(path(start_url), '/new_order'), 'Корзина',
    'Прочее')"""


def _dim_sql(ctx: Ctx, dim: str, limit: int = 30, where: str = "1") -> str:
    cur = ctx.cur_filter("date")
    a, b = ctx.cur.start - timedelta(days=1), ctx.cur.end + timedelta(days=1)
    return f"""
WITH v AS (
    SELECT visit_id, client_id, bounce, visit_duration, page_views, is_new_user, purchase_id,
        {dim} AS k, {cur} AS c
    FROM kixbox.ym_visits
    WHERE {ctx.wfilter('date', 'date', ('cur', 'prev'))} AND {where}
),
att AS (
    SELECT visit_id, arrayJoin(extractAll(purchase_id, '[0-9]+')) AS pid
    FROM v WHERE c AND {HAS_PURCHASE}
),
ord AS (
    SELECT doc_number, sum(amount) AS amt
    FROM kixbox.c1_items
    WHERE {IS_ORDER} AND {ctx.range_filter('doc_date', a, b, 'datetime')}
    GROUP BY doc_number
),
va AS (
    SELECT att.visit_id AS visit_id, uniqExact(ord.doc_number) AS orders, sum(ord.amt) AS amt
    FROM att INNER JOIN ord ON ord.doc_number = concat('KB', att.pid)
    GROUP BY att.visit_id
)
SELECT v.k AS k,
    uniqExactIf(v.visit_id, v.c) AS visits,
    uniqExactIf(v.visit_id, NOT v.c) AS visits_prev,
    uniqExactIf(v.client_id, v.c) AS users,
    sumIf(v.bounce, v.c) AS bounces,
    avgIf(v.visit_duration, v.c) AS dur,
    avgIf(v.page_views, v.c) AS depth,
    sumIf(v.is_new_user, v.c) AS new_users,
    countIf(v.c AND {HAS_PURCHASE.replace('purchase_id', 'v.purchase_id')}) AS buy_visits,
    sumIf(va.orders, v.c) AS orders,
    sumIf(va.amt, v.c) AS amt
FROM v LEFT JOIN va ON va.visit_id = v.visit_id
GROUP BY k
HAVING visits > 0
ORDER BY visits DESC
LIMIT {limit}"""


async def visit_kpis(ctx: Ctx) -> dict[str, dict]:
    goals = ",\n    ".join(
        f"countIf(goals_id LIKE '%{gid}%') AS g{i}" for i, (_, gid) in enumerate(FUNNEL_GOALS))
    sql = f"""
SELECT {ctx.wexpr('date')} AS w,
    uniqExact(visit_id) AS visits,
    uniqExact(client_id) AS users,
    sum(is_new_user) AS new_users,
    sum(bounce) AS bounces,
    avg(visit_duration) AS dur,
    avg(page_views) AS depth,
    countIf({HAS_PURCHASE}) AS buy_visits,
    countIf(device_category = '2') AS mobile,
    {goals}
FROM kixbox.ym_visits
WHERE {ctx.wfilter('date')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if r:
            v = num(r.get("visits"))
            r["bounce_rate"] = safe_div(r["bounces"], v)
            r["new_share"] = safe_div(r["new_users"], v)
            r["cr_ym"] = safe_div(r["buy_visits"], v)
            r["mobile_share"] = safe_div(r["mobile"], v)
            r["cart_rate"] = safe_div(r.get("g0"), v)
    return res


def _dim_rows(rows, names=None, total=None):
    total = total or sum(num(r["visits"]) for r in rows) or 1
    out = []
    for r in rows:
        k = r["k"]
        label = names.get(str(k), str(k)) if names else (str(k) if k not in (None, "") else "Не определён")
        out.append([label, r["visits"], num(r["visits"]) / total, rel_delta(r["visits"], r["visits_prev"]),
                    safe_div(r["bounces"], r["visits"]), r["dur"], r["orders"],
                    safe_div(r["orders"], r["visits"]), r["amt"]])
    return out


DIM_COLS = [
    col("Визиты", "int"), col("Доля", "pct", bar=True), col("Дин.", "pct", delta=True),
    col("Отказы", "pct", better="down"), col("Время", "sec"), col("Заказы", "int"),
    col("CR", "pct", better="up"), col("Сумма заказов", "money"),
]


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    (vk, c1, ser, c1ser, src, dev, city, land, ptype, utm, newret) = await ctx.gather(
        visit_kpis(ctx), common.c1_kpis(ctx), common.metrika_series(ctx), common.c1_series(ctx),
        ctx.q(_dim_sql(ctx, "traffic_source", 20)),
        ctx.q(_dim_sql(ctx, "device_category", 10)),
        ctx.q(_dim_sql(ctx, "if(region_city = '', 'Не определён', region_city)", 25)),
        ctx.q(_dim_sql(ctx, "path(start_url)", 30)),
        ctx.q(_dim_sql(ctx, PAGE_TYPE, 12)),
        ctx.q(_dim_sql(ctx, "concat(utm_source, ' / ', utm_campaign)", 25, "utm_source != ''")),
        ctx.q(_dim_sql(ctx, "if(is_new_user = 1, 'Новые', 'Вернувшиеся')", 2)),
    )
    c, p, l = vk["cur"], vk["prev"], vk["ly"]
    oc, op_, ol = c1["cur"], c1["prev"], c1["ly"]
    att_orders = sum(num(r["orders"]) for r in src)
    att_amt = sum(num(r["amt"]) for r in src)

    w: list[dict] = [kpis(None, [
        kpi("Визиты", c.get("visits"), p.get("visits"), l.get("visits"), fmt="int", period=P),
        kpi("Посетители", c.get("users"), p.get("users"), l.get("users"), fmt="int", period=P),
        kpi("Новые посетители", c.get("new_share"), p.get("new_share"), l.get("new_share"), fmt="pct",
            better="none", period=P, hint="Доля визитов новых посетителей"),
        kpi("Отказы", c.get("bounce_rate"), p.get("bounce_rate"), l.get("bounce_rate"), fmt="pct",
            better="down", period=P),
        kpi("Время на сайте", c.get("dur"), p.get("dur"), l.get("dur"), fmt="sec", period=P),
        kpi("Глубина просмотра", c.get("depth"), p.get("depth"), l.get("depth"), fmt="dec1", period=P),
        kpi("Со смартфона", c.get("mobile_share"), p.get("mobile_share"), l.get("mobile_share"), fmt="pct",
            better="none", period=P),
        kpi("Добавили в корзину", c.get("cart_rate"), p.get("cart_rate"), l.get("cart_rate"), fmt="pct",
            period=P, hint="Доля визитов с целью «добавление в корзину»"),
        kpi("Конверсия в заказ 1С", safe_div(oc.get("orders"), c.get("visits")),
            safe_div(op_.get("orders"), p.get("visits")), safe_div(ol.get("orders"), l.get("visits")),
            fmt="pct", period=P, hint="Все заказы 1С на визит"),
        kpi("Конверсия по Метрике", c.get("cr_ym"), p.get("cr_ym"), l.get("cr_ym"), fmt="pct", period=P,
            hint="Визиты с покупкой в ecommerce Метрики — недосчитывает около 25–35%"),
    ])]

    ins = []
    cov = safe_div(att_orders, oc.get("orders"))
    if cov is not None:
        ins.append(insight("info", f"Метрика увидела {int(att_orders)} из {int(num(oc.get('orders')))} "
                                   f"заказов 1С ({cov * 100:.0f}%) — по ним известен источник."))
    if src:
        best = max((r for r in src if num(r["visits"]) >= 300), key=lambda r: safe_div(r["orders"], r["visits"]) or 0,
                   default=None)
        if best:
            ins.append(insight("good", f"Лучшая конверсия у источника «{TRAFFIC_SOURCE_NAMES.get(best['k'], best['k'])}»: "
                                       f"{(safe_div(best['orders'], best['visits']) or 0) * 100:.2f}%."))
        grow = sorted(src, key=lambda r: -(num(r["visits"]) - num(r["visits_prev"])))
        if grow and num(grow[0]["visits"]) - num(grow[0]["visits_prev"]) > 0:
            g = grow[0]
            ins.append(insight("info", f"Больше всего прибавил «{TRAFFIC_SOURCE_NAMES.get(g['k'], g['k'])}»: "
                                       f"+{int(num(g['visits']) - num(g['visits_prev']))} визитов."))
    if newret and len(newret) == 2:
        by = {r["k"]: r for r in newret}
        n, rtn = by.get("Новые"), by.get("Вернувшиеся")
        if n and rtn:
            crn, crr = safe_div(n["orders"], n["visits"]), safe_div(rtn["orders"], rtn["visits"])
            if crn and crr:
                ins.append(insight("info", f"Вернувшиеся покупают в {crr / crn:.1f} раза чаще новых "
                                           f"({crr * 100:.2f}% против {crn * 100:.2f}%)."))
    if ins:
        w.append(insights("Трафик", ins))

    x, s = fill_buckets(P, ser, "b", ["visits"])
    _, o = fill_buckets(P, c1ser, "b", ["orders"])
    w.append(chart(f"Визиты и конверсия {bucket_caption(P)}", x, [
        series("Визиты", s["visits"], fmt="int", color=0),
        series("CR в заказ 1С", [safe_div(a, b) for a, b in zip(o["orders"], s["visits"])], fmt="pct",
               style="line", axis="right", color=2),
    ], kind="combo"))

    steps = [("Визиты", c.get("visits"))] + [(name, c.get(f"g{i}")) for i, (name, _) in enumerate(FUNNEL_GOALS)]
    steps.append(("Заказы в 1С", oc.get("orders")))
    w.append(funnel("Воронка сайта", steps, subtitle="Визиты с достижением цели Метрики",
                    note="Последний шаг — все заказы 1С: часть покупок Метрика не фиксирует."))

    w.append(table("Источники трафика", [col("Источник")] + DIM_COLS,
                   _dim_rows(src, TRAFFIC_SOURCE_NAMES), collapsed=12,
                   subtitle="Последний значимый источник · заказы — фактические из 1С по номеру заказа"))
    if src:
        w.append(share("Сумма заказов по источникам",
                       [(TRAFFIC_SOURCE_NAMES.get(r["k"], r["k"]), r["amt"]) for r in src],
                       subtitle=f"{att_amt / 1e6:.1f} млн ₽ заказов с известным источником".replace(".", ",")))
    w.append(table("Устройства", [col("Устройство")] + DIM_COLS, _dim_rows(dev, DEVICE_NAMES), sortable=False))
    w.append(table("Новые и вернувшиеся", [col("Посетители")] + DIM_COLS, _dim_rows(newret), sortable=False))
    w.append(table("Типы входных страниц", [col("Страница")] + DIM_COLS, _dim_rows(ptype), collapsed=10))
    w.append(table("Страницы входа", [col("Адрес", width=2.0)] + DIM_COLS, _dim_rows(land), collapsed=12))
    w.append(table("Города", [col("Город")] + DIM_COLS, _dim_rows(city), collapsed=12))
    if utm:
        w.append(table("UTM-метки", [col("Источник / кампания", width=2.2)] + DIM_COLS, _dim_rows(utm),
                       collapsed=10))
    w.append(note("Визиты — сырые данные Logs API. Заказы в таблицах — это номера заказов, которые Метрика "
                  "передала в покупке, найденные в 1С (KB + номер): сумма оформленного заказа, а не выручка.",
                  title="Методика"))
    return w
