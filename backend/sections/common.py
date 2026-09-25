"""Запросы, которые нужны сразу нескольким разделам."""
from __future__ import annotations

from ch import lit, lits, num
from config import MB_EXCLUDED_STATUSES, ONLINE_ID, SETTINGS, STORE_IDS
from context import (C1_ROWS, IS_GOODS, IS_ORDER, IS_RET, IS_SALE, IS_SERVICE, Ctx,
                     by_window, mb_date)


async def c1_kpis(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('toDate(doc_date)')} AS w,
    sumIf(amount, {IS_SALE}) AS sales,
    sumIf(amount, {IS_GOODS}) AS goods,
    sumIf(amount, {IS_SERVICE}) AS service,
    sumIf(amount, {IS_RET}) AS returns,
    sumIf(qty, {IS_GOODS}) AS units,
    sumIf(qty, {IS_RET}) AS units_ret,
    sumIf(price * qty, {IS_GOODS}) AS goods_full,
    uniqExactIf(doc_number, {IS_GOODS}) AS shipments,
    sumIf(amount, {IS_ORDER}) AS demand,
    uniqExactIf(doc_number, {IS_ORDER}) AS orders,
    sumIf(qty, {IS_ORDER}) AS order_units
FROM kixbox.c1_items
WHERE {C1_ROWS} AND {ctx.wfilter('doc_date', 'datetime')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if not r:
            continue
        r["net"] = num(r.get("sales")) - num(r.get("returns"))
        r["aov"] = num(r["demand"]) / num(r["orders"]) if num(r.get("orders")) else None
        r["upt"] = num(r["order_units"]) / num(r["orders"]) if num(r.get("orders")) else None
        r["ret_rate"] = num(r["returns"]) / num(r["sales"]) if num(r.get("sales")) else None
        r["discount"] = (1 - num(r["goods"]) / num(r["goods_full"])) if num(r.get("goods_full")) else None
        r["avg_price"] = num(r["goods"]) / num(r["units"]) if num(r.get("units")) else None
    return res


async def c1_series(ctx: Ctx) -> list[dict]:
    b = ctx.bexpr("toDate(doc_date)")
    sql = f"""
SELECT {b} AS b,
    sumIf(amount, {IS_SALE}) AS sales,
    sumIf(amount, {IS_RET}) AS returns,
    sumIf(amount, {IS_SALE}) - sumIf(amount, {IS_RET}) AS net,
    sumIf(amount, {IS_ORDER}) AS demand,
    uniqExactIf(doc_number, {IS_ORDER}) AS orders,
    sumIf(qty, {IS_ORDER}) AS order_units
FROM kixbox.c1_items
WHERE {C1_ROWS} AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def c1_net_ly_series(ctx: Ctx) -> list[dict]:
    """Чистая выручка год назад, со сдвигом дат на окно текущего периода."""
    shift = (ctx.cur.start - ctx.ly.start).days
    d = f"toDate(doc_date) + {shift}"
    sql = f"""
SELECT {ctx.bexpr(d)} AS b,
    sumIf(amount, {IS_SALE}) - sumIf(amount, {IS_RET}) AS net,
    uniqExactIf(doc_number, {IS_ORDER}) AS orders
FROM kixbox.c1_items
WHERE {C1_ROWS} AND {ctx.range_filter('doc_date', ctx.ly.start, ctx.ly.end, 'datetime')}
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def metrika_kpis(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('date')} AS w,
    sum(visits) AS visits,
    sum(bounces) AS bounces,
    sum(toFloat64(m.page_depth) * m.visits) AS depth_w,
    sum(purchases) AS purchases,
    sum(revenue) AS revenue
FROM kixbox.ya_metrika AS m FINAL
WHERE site = {lit(SETTINGS.metrika_site)} AND {ctx.wfilter('date')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if r:
            r["bounce_rate"] = num(r["bounces"]) / num(r["visits"]) if num(r.get("visits")) else None
            r["depth"] = num(r["depth_w"]) / num(r["visits"]) if num(r.get("visits")) else None
    return res


async def metrika_series(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT {ctx.bexpr('date')} AS b, sum(visits) AS visits, sum(bounces) AS bounces,
    sum(purchases) AS purchases
FROM kixbox.ya_metrika FINAL
WHERE site = {lit(SETTINGS.metrika_site)} AND {ctx.cur_filter('date')}
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def direct_kpis(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('date')} AS w,
    sum(cost) AS cost, sum(clicks) AS clicks, sum(impressions) AS impressions,
    sum(conversions) AS conversions
FROM kixbox.ya_direct FINAL
WHERE client_login = {lit(SETTINGS.direct_login)} AND {ctx.wfilter('date')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if r:
            r["ctr"] = num(r["clicks"]) / num(r["impressions"]) if num(r.get("impressions")) else None
            r["cpc"] = num(r["cost"]) / num(r["clicks"]) if num(r.get("clicks")) else None
            r["cpa"] = num(r["cost"]) / num(r["conversions"]) if num(r.get("conversions")) else None
    return res


def mb_orders_cte(ctx: Ctx, keys=("cur", "prev", "ly"), extra_cols: str = "") -> str:
    """Заказы Mindbox с суммами позиций без отмен и возвратов."""
    return f"""
o AS (
    SELECT id, unmergedCustomerId AS cid, pointOfContactInternalId AS poc,
        firstDateTimeUtc AS ts, {mb_date()} AS d {extra_cols}
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE {ctx.wfilter('firstDateTimeUtc', 'utc', keys)} AND coalesce(_isDeleted, false) = false
),
p AS (
    SELECT orderId, sum(quantity) AS qty, sum(priceOfLine) AS amt
    FROM kixbox.mb_ProcessingOrders_Purchases FINAL
    WHERE orderId IN (SELECT id FROM o)
      AND statusInternalId NOT IN {lits(MB_EXCLUDED_STATUSES)}
    GROUP BY orderId
),
op AS (
    SELECT o.id AS id, o.cid AS cid, o.poc AS poc, o.ts AS ts, o.d AS d, p.qty AS qty, p.amt AS amt
    FROM o INNER JOIN p ON p.orderId = o.id
    WHERE p.amt > 0
)"""


def store_kind_expr(col: str = "poc") -> str:
    return (f"multiIf({col} = {lit(ONLINE_ID)}, 'online', {col} IN {lits(STORE_IDS)}, 'store', "
            f"'other')")


async def mb_network(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
WITH {mb_orders_cte(ctx)}
SELECT {ctx.wexpr('d')} AS w,
    sum(amt) AS total,
    sumIf(amt, poc = {lit(ONLINE_ID)}) AS online,
    sumIf(amt, poc IN {lits(STORE_IDS)}) AS stores,
    countIf(poc IN {lits(STORE_IDS)}) AS store_orders,
    sumIf(qty, poc IN {lits(STORE_IDS)}) AS store_units,
    countIf(poc = {lit(ONLINE_ID)}) AS online_orders,
    count() AS orders,
    uniqExactIf(cid, cid IS NOT NULL) AS customers,
    countIf(poc IN {lits(STORE_IDS)} AND cid IS NOT NULL) AS store_ident
FROM op
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if r:
            r["retail_share"] = num(r["stores"]) / num(r["total"]) if num(r.get("total")) else None
            r["store_aov"] = num(r["stores"]) / num(r["store_orders"]) if num(r.get("store_orders")) else None
            r["store_upt"] = num(r["store_units"]) / num(r["store_orders"]) if num(r.get("store_orders")) else None
            r["ident"] = num(r["store_ident"]) / num(r["store_orders"]) if num(r.get("store_orders")) else None
    return res


async def mb_new_customers(ctx: Ctx) -> dict[str, dict]:
    """Покупатели окна и новые (первый заказ в истории попал в окно)."""
    sql = f"""
WITH {mb_orders_cte(ctx)},
firsts AS (
    SELECT unmergedCustomerId AS cid, min(firstDateTimeUtc) AS first_ts
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE unmergedCustomerId IN (SELECT cid FROM op WHERE cid IS NOT NULL)
      AND coalesce(_isDeleted, false) = false
    GROUP BY cid
)
SELECT {ctx.wexpr('op.d')} AS w,
    uniqExact(op.cid) AS buyers,
    uniqExactIf(op.cid, {mb_date('f.first_ts')} = op.d) AS new_buyers,
    sumIf(op.amt, {mb_date('f.first_ts')} = op.d) AS new_amt,
    sum(op.amt) AS amt
FROM op INNER JOIN firsts AS f ON f.cid = op.cid
GROUP BY w"""
    return by_window(await ctx.q(sql))
