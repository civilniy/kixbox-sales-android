"""Продажи интернет-магазина по 1С: динамика, доставка и оплата, регионы, скидки, отмены."""
from __future__ import annotations

from ch import num
from context import (C1_ROWS, CITY_EXPR, IS_GOODS, IS_ORDER, IS_RET, IS_SALE, WEEKDAYS, Ctx)
from sections import common
from widgets import (bucket_caption, chart, col, fill_buckets, fmt_pct, heatmap, kpi, kpis,
                     note, rel_delta, safe_div, series, share, table)

ID = "sales"
TITLE = "Продажи ИМ"
ICON = "cart"


async def heat(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT toDayOfWeek(doc_date) AS wd, toHour(doc_date) AS h, uniqExact(doc_number) AS orders
FROM kixbox.c1_items
WHERE {IS_ORDER} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY wd, h"""
    return await ctx.q(sql)


async def delivery_mix(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT if(delivery = '', 'Не указан', delivery) AS delivery,
    if(payment = '', 'Не указан', payment) AS payment,
    sumIf(amount, {IS_GOODS}) AS sales,
    sumIf(amount, {IS_RET}) AS returns,
    uniqExactIf(doc_number, {IS_GOODS}) AS shipments
FROM kixbox.c1_items
WHERE row_type IN ('Товар', 'Возврат') AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY delivery, payment
HAVING sales > 0 OR returns > 0
ORDER BY sales DESC"""
    return await ctx.q(sql)


async def order_mix(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT if(delivery = '', 'Не указан', delivery) AS delivery,
    uniqExact(doc_number) AS orders, sum(amount) AS demand,
    uniqExactIf(doc_number, status ILIKE '%Отмен%') AS cancelled
FROM kixbox.c1_items
WHERE {IS_ORDER} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY delivery ORDER BY demand DESC"""
    return await ctx.q(sql)


async def statuses(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT multiIf(status ILIKE '%Выполнен%', 'Выполнен',
               status ILIKE '%Отмен%', 'Отменён',
               status ILIKE '%Возврат%', 'Возврат',
               status ILIKE '[%', 'В работе', 'Прочее') AS st,
    uniqExact(doc_number) AS orders, sum(amount) AS demand
FROM kixbox.c1_items
WHERE {IS_ORDER} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY st ORDER BY orders DESC"""
    return await ctx.q(sql)


async def cities(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT {CITY_EXPR} AS city,
    uniqExactIf(doc_number, {ctx.cur_filter('doc_date', 'datetime')}) AS orders,
    sumIf(amount, {ctx.cur_filter('doc_date', 'datetime')}) AS demand,
    uniqExactIf(doc_number, {ctx.cur_filter('doc_date', 'datetime')} AND status ILIKE '%Отмен%') AS cancelled,
    uniqExactIf(doc_number, NOT {ctx.cur_filter('doc_date', 'datetime')}) AS orders_prev
FROM kixbox.c1_items
WHERE {IS_ORDER} AND {ctx.wfilter('doc_date', 'datetime', ('cur', 'prev'))}
GROUP BY city ORDER BY demand DESC LIMIT 40"""
    return await ctx.q(sql)


async def discount_bands(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT multiIf(d < 0.01, '0: полная цена', d < 0.2, '1–19%', d < 0.4, '20–39%', d < 0.5, '40–49%',
               d < 0.6, '50–59%', '60% и глубже') AS band,
    sum(qty) AS units, sum(amount) AS sales, sum(price * qty) AS full
FROM (
    SELECT qty, amount, price, if(price * qty > 0, 1 - toFloat64(amount) / toFloat64(price * qty), 0) AS d
    FROM kixbox.c1_items
    WHERE {IS_GOODS} AND {ctx.cur_filter('doc_date', 'datetime')}
)
GROUP BY band ORDER BY band"""
    return await ctx.q(sql)


async def price_bands(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT multiIf(p < 3000, 1, p < 7000, 2, p < 15000, 3, p < 30000, 4, 5) AS band,
    sum(qty) AS units, sum(amount) AS sales
FROM (
    SELECT qty, amount, if(qty > 0, toFloat64(amount) / toFloat64(qty), 0) AS p
    FROM kixbox.c1_items
    WHERE {IS_GOODS} AND {ctx.cur_filter('doc_date', 'datetime')}
)
GROUP BY band ORDER BY band"""
    return await ctx.q(sql)


async def seasons(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT if(season = '', 'Без сезона', season) AS season,
    sumIf(amount, {IS_GOODS}) AS sales, sumIf(qty, {IS_GOODS}) AS units,
    sumIf(price * qty, {IS_GOODS}) AS full, sumIf(amount, {IS_RET}) AS returns
FROM kixbox.c1_items
WHERE row_type IN ('Товар', 'Возврат') AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY season HAVING sales > 0 ORDER BY sales DESC LIMIT 12"""
    return await ctx.q(sql)


async def genders(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT if(gender = '', 'Не указан', gender) AS g, sum(amount) AS sales
FROM kixbox.c1_items
WHERE {IS_GOODS} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY g ORDER BY sales DESC"""
    return await ctx.q(sql)


async def weekday_profile(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT toDayOfWeek(doc_date) AS wd,
    uniqExactIf(doc_number, {IS_ORDER}) AS orders, sumIf(amount, {IS_ORDER}) AS demand,
    uniqExact(toDate(doc_date)) AS days
FROM kixbox.c1_items
WHERE {IS_ORDER} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY wd ORDER BY wd"""
    return await ctx.q(sql)


async def build(ctx: Ctx) -> list[dict]:
    (c1, ser, hm, mix, omix, sts, cts, disc, prices, seas, gen, wdp) = await ctx.gather(
        common.c1_kpis(ctx), common.c1_series(ctx), heat(ctx), delivery_mix(ctx), order_mix(ctx),
        statuses(ctx), cities(ctx), discount_bands(ctx), price_bands(ctx), seasons(ctx),
        genders(ctx), weekday_profile(ctx))
    P = ctx.period
    cur, prev, ly = c1["cur"], c1["prev"], c1["ly"]
    x, s = fill_buckets(P, ser, "b", ["sales", "returns", "net", "demand", "orders", "order_units"])
    aov = [safe_div(d, o) for d, o in zip(s["demand"], s["orders"])]

    w: list[dict] = [kpis(None, [
        kpi("Сумма заказов", cur.get("demand"), prev.get("demand"), ly.get("demand"), period=P),
        kpi("Заказы", cur.get("orders"), prev.get("orders"), ly.get("orders"), fmt="int", period=P),
        kpi("Отгрузки", cur.get("sales"), prev.get("sales"), ly.get("sales"), period=P),
        kpi("Отгружено заказов", cur.get("shipments"), prev.get("shipments"), ly.get("shipments"),
            fmt="int", period=P),
        kpi("Возвраты", cur.get("returns"), prev.get("returns"), ly.get("returns"), better="down",
            period=P),
        kpi("Чистая выручка", cur.get("net"), prev.get("net"), ly.get("net"), period=P),
        kpi("Средний чек", cur.get("aov"), prev.get("aov"), ly.get("aov"), period=P),
        kpi("Средняя цена товара", cur.get("avg_price"), prev.get("avg_price"), ly.get("avg_price"),
            period=P, hint="Отгрузки товара на проданную штуку"),
        kpi("Товаров в заказе", cur.get("upt"), prev.get("upt"), ly.get("upt"), fmt="dec2", period=P),
        kpi("Средняя скидка", cur.get("discount"), prev.get("discount"), ly.get("discount"),
            fmt="pct", better="down", period=P),
        kpi("Доставка, выручка", cur.get("service"), prev.get("service"), ly.get("service"), period=P,
            hint="Услуга доставки в реализациях"),
        kpi("Возвращено штук", cur.get("units_ret"), prev.get("units_ret"), ly.get("units_ret"),
            fmt="int", better="down", period=P),
    ])]

    w.append(chart(f"Спрос, отгрузки, возвраты {bucket_caption(P)}", x, [
        series("Заказы, ₽", s["demand"], color=1),
        series("Отгрузки", s["sales"], color=0),
        series("Возвраты", s["returns"], color=4),
    ], subtitle="Три разных потока: заказ, реализация и возврат по своим датам"))
    w.append(chart(f"Заказы и средний чек {bucket_caption(P)}", x, [
        series("Заказы", s["orders"], fmt="int", color=0),
        series("Средний чек", aov, style="line", axis="right", color=2),
    ], kind="combo"))

    # теплокарта день недели × час
    grid = [[0] * 24 for _ in range(7)]
    for r in hm:
        grid[int(r["wd"]) - 1][int(r["h"])] += int(num(r["orders"]))
    w.append(heatmap("Когда оформляют заказы", [f"{h}" for h in range(24)], WEEKDAYS, grid,
                     subtitle="Заказы по дню недели и часу, московское время"))

    if wdp:
        by = {int(r["wd"]): r for r in wdp}
        vals = [safe_div(by.get(i, {}).get("demand"), by.get(i, {}).get("days")) for i in range(1, 8)]
        w.append(chart("Средний спрос по дням недели", WEEKDAYS, [series("₽ в день", vals, color=0)],
                       subtitle="Сумма заказов на один такой день периода"))

    # доставка × оплата
    tot_sales = sum(num(r["sales"]) for r in mix) or 1
    rows = [[r["delivery"], r["payment"], r["sales"], num(r["sales"]) / tot_sales, r["returns"],
             safe_div(r["returns"], r["sales"]), r["shipments"]] for r in mix]
    w.append(table("Доставка и оплата", [
        col("Доставка"), col("Оплата"), col("Отгрузки", "money"), col("Доля", "pct", bar=True),
        col("Возвраты", "money"), col("% возвр.", "pct", better="down"), col("Отгрузок", "int"),
    ], rows, subtitle="Отгрузки и возвраты периода по способам", collapsed=8))

    tot_o = sum(num(r["orders"]) for r in omix) or 1
    w.append(table("Способы получения заказов", [
        col("Способ"), col("Заказы", "int"), col("Доля", "pct", bar=True), col("Сумма", "money"),
        col("Средний чек", "money"), col("% отмен", "pct", better="down"),
    ], [[r["delivery"], r["orders"], num(r["orders"]) / tot_o, r["demand"],
         safe_div(r["demand"], r["orders"]), safe_div(r["cancelled"], r["orders"])] for r in omix],
        note="Отмены дозревают около 22 дней — у свежих заказов доля занижена."))

    if sts:
        w.append(share("Статусы заказов периода", [(r["st"], r["orders"]) for r in sts], fmt="int"))

    # регионы
    tot_c = sum(num(r["demand"]) for r in cts) or 1
    w.append(table("Города", [
        col("Город"), col("Заказы", "int"), col("Сумма", "money"), col("Доля", "pct", bar=True),
        col("Средний чек", "money"), col("% отмен", "pct", better="down"),
        col("Заказы, дин.", "pct", delta=True, better="up"),
    ], [[r["city"], r["orders"], r["demand"], num(r["demand"]) / tot_c, safe_div(r["demand"], r["orders"]),
         safe_div(r["cancelled"], r["orders"]), rel_delta(r["orders"], r["orders_prev"])]
        for r in cts if num(r["orders"]) > 0], subtitle="Город из адреса доставки, самовывоз — Москва",
        collapsed=12))

    # скидки и цены
    if disc:
        tot_u = sum(num(r["units"]) for r in disc) or 1
        tot_s = sum(num(r["sales"]) for r in disc) or 1
        w.append(table("Глубина скидки", [
            col("Скидка"), col("Штук", "int"), col("Доля штук", "pct", bar=True), col("Выручка", "money"),
            col("Доля выручки", "pct"), col("Отдано скидкой", "money"),
        ], [[r["band"], r["units"], num(r["units"]) / tot_u, r["sales"], num(r["sales"]) / tot_s,
             num(r["full"]) - num(r["sales"])] for r in disc], sortable=False,
            subtitle="Отгрузки товара по скидке от базовой цены"))
    if prices:
        names = {1: "до 3 тыс", 2: "3–7 тыс", 3: "7–15 тыс", 4: "15–30 тыс", 5: "от 30 тыс"}
        w.append(chart("Ценовые сегменты", [names[int(r["band"])] for r in prices], [
            series("Выручка", [r["sales"] for r in prices], color=0),
            series("Штук", [r["units"] for r in prices], fmt="int", style="line", axis="right", color=2),
        ], subtitle="Фактическая цена продажи за штуку", kind="combo"))
    if seas:
        w.append(table("Сезоны коллекций", [
            col("Сезон"), col("Выручка", "money"), col("Доля", "pct", bar=True), col("Штук", "int"),
            col("Скидка", "pct"), col("Возвраты", "money"),
        ], [[r["season"], r["sales"], safe_div(r["sales"], sum(num(t["sales"]) for t in seas)),
             r["units"], (1 - num(r["sales"]) / num(r["full"])) if num(r["full"]) else None, r["returns"]]
            for r in seas], collapsed=6))
    if gen:
        w.append(share("Пол", [(r["g"], r["sales"]) for r in gen]))
    w.append(note("Чистая выручка = отгрузки товара и доставки минус возвраты со складов 400 и 401, "
                  "сайт не Hike. Совпадает с витриной plan_fact и отчётом 1С. Сумма заказов — спрос "
                  "по дате оформления, отгрузки и возвраты — по датам своих документов.",
                  title="Методика"))
    return w
