"""Реклама: Яндекс Директ, эффективность кампаний и окупаемость по заказам 1С."""
from __future__ import annotations

from datetime import timedelta

from ch import lit, num
from config import SETTINGS
from context import IS_ORDER, Ctx
from sections import common
from widgets import (bucket_caption, chart, col, fill_buckets, fmt_money_short, insight, insights,
                     kpi, kpis, note, rel_delta, safe_div, series, share, table)

ID = "ads"
TITLE = "Реклама"
ICON = "ads"

def campaign_type(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("товарная"):
        return "Товарные"
    if n.startswith("мастер") or n.startswith("мк "):
        return "Мастер кампаний"
    if "retarget" in n or "ретарг" in n or "smartbanner" in n or "смарт" in n:
        return "Ретаргетинг и смарт-баннеры"
    if "brand" in n or "бренд" in n:
        return "Брендовые"
    if n.startswith("поиск") or "search" in n:
        return "Поиск"
    if "рся" in n or "rsy" in n or "yan" in n:
        return "РСЯ"
    return "Прочие"


async def campaigns(ctx: Ctx) -> list[dict]:
    cur = ctx.cur_filter("date")
    sql = f"""
SELECT campaign_id, argMax(campaign_name, date) AS name,
    sumIf(d.cost, {cur}) AS cost, sumIf(d.clicks, {cur}) AS clicks, sumIf(d.impressions, {cur}) AS impressions,
    sumIf(d.conversions, {cur}) AS conversions, sumIf(d.cost, NOT {cur}) AS cost_prev,
    sumIf(d.conversions, NOT {cur}) AS conversions_prev
FROM kixbox.ya_direct AS d FINAL
WHERE client_login = {lit(SETTINGS.direct_login)} AND {ctx.wfilter('date', 'date', ('cur', 'prev'))}
GROUP BY campaign_id
HAVING cost > 0 OR cost_prev > 0
ORDER BY cost DESC"""
    return await ctx.q(sql)


async def direct_series(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT {ctx.bexpr('date')} AS b, sum(cost) AS cost, sum(clicks) AS clicks, sum(conversions) AS conv
FROM kixbox.ya_direct FINAL
WHERE client_login = {lit(SETTINGS.direct_login)} AND {ctx.cur_filter('date')}
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def ad_attribution(ctx: Ctx) -> list[dict]:
    """Заказы 1С из рекламных визитов по кампаниям (utm_campaign → id кампании Директа)."""
    a, b = ctx.cur.start - timedelta(days=1), ctx.cur.end + timedelta(days=1)
    sql = f"""
WITH att AS (
    SELECT extract(utm_campaign, '[0-9]{{6,}}') AS cid, utm_campaign,
        arrayJoin(extractAll(purchase_id, '[0-9]+')) AS pid
    FROM kixbox.ym_visits
    WHERE {ctx.cur_filter('date')} AND traffic_source = 'ad' AND purchase_id NOT IN ('', '[]')
),
ord AS (
    SELECT doc_number, sum(amount) AS amt
    FROM kixbox.c1_items
    WHERE {IS_ORDER} AND {ctx.range_filter('doc_date', a, b, 'datetime')}
    GROUP BY doc_number
)
SELECT att.cid AS cid, uniqExact(ord.doc_number) AS orders, sum(ord.amt) AS amt
FROM att INNER JOIN ord ON ord.doc_number = concat('KB', att.pid)
GROUP BY cid"""
    return await ctx.q(sql)


async def ad_visits(ctx: Ctx) -> dict:
    sql = f"""
SELECT uniqExact(visit_id) AS visits, sum(bounce) AS bounces
FROM kixbox.ym_visits
WHERE {ctx.cur_filter('date')} AND traffic_source = 'ad'"""
    rows = await ctx.q(sql)
    return rows[0] if rows else {}


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    dr, c1, camps, ser, att, adv = await ctx.gather(
        common.direct_kpis(ctx), common.c1_kpis(ctx), campaigns(ctx), direct_series(ctx),
        ad_attribution(ctx), ad_visits(ctx))
    dc, dp, dl = dr["cur"], dr["prev"], dr["ly"]
    cc, cp, cl = c1["cur"], c1["prev"], c1["ly"]
    att_by = {str(r["cid"]): r for r in att}
    att_orders = sum(num(r["orders"]) for r in att)
    att_amt = sum(num(r["amt"]) for r in att)

    w: list[dict] = [kpis(None, [
        kpi("Расход", dc.get("cost"), dp.get("cost"), dl.get("cost"), better="down", period=P),
        kpi("ДРР от выручки ИМ", safe_div(dc.get("cost"), cc.get("net")), safe_div(dp.get("cost"), cp.get("net")),
            safe_div(dl.get("cost"), cl.get("net")), fmt="pct", better="down", period=P,
            hint="Весь расход Директа к чистой выручке интернет-магазина"),
        kpi("Показы", dc.get("impressions"), dp.get("impressions"), dl.get("impressions"), fmt="int", period=P),
        kpi("Клики", dc.get("clicks"), dp.get("clicks"), dl.get("clicks"), fmt="int", period=P),
        kpi("CTR", dc.get("ctr"), dp.get("ctr"), dl.get("ctr"), fmt="pct", period=P),
        kpi("Цена клика", dc.get("cpc"), dp.get("cpc"), dl.get("cpc"), better="down", period=P),
        kpi("Конверсии Директа", dc.get("conversions"), dp.get("conversions"), dl.get("conversions"),
            fmt="int", period=P, hint="Цели, настроенные в кампаниях — не равны заказам"),
        kpi("Цена конверсии", dc.get("cpa"), dp.get("cpa"), dl.get("cpa"), better="down", period=P),
        kpi("Заказы из рекламы", att_orders, fmt="int",
            hint="Заказы 1С, которые Метрика связала с рекламным визитом"),
        kpi("Стоимость заказа", safe_div(dc.get("cost"), att_orders), better="down",
            hint="Расход к заказам из рекламы — верхняя оценка, Метрика видит не все заказы"),
        kpi("ROAS по заказам", safe_div(att_amt, dc.get("cost")), fmt="dec2",
            hint="Сумма заказов из рекламы на рубль расхода"),
        kpi("Отказы рекламного трафика", safe_div(adv.get("bounces"), adv.get("visits")), fmt="pct",
            better="down"),
    ])]

    ins = []
    cpc_d = rel_delta(dc.get("cpc"), dp.get("cpc"))
    if cpc_d is not None and abs(cpc_d) > 0.1:
        ins.append(insight("bad" if cpc_d > 0 else "good", f"Цена клика {cpc_d * 100:+.0f}% {P.prev_name}: "
                           f"{num(dc.get('cpc')):.1f} ₽ против {num(dp.get('cpc')):.1f} ₽.".replace(".", ",", 2)))
    cost_d = rel_delta(dc.get("cost"), dp.get("cost"))
    net_d = rel_delta(cc.get("net"), cp.get("net"))
    if cost_d is not None and net_d is not None:
        tone = "good" if net_d >= cost_d else "warn"
        ins.append(insight(tone, f"Расход {cost_d * 100:+.0f}%, выручка ИМ {net_d * 100:+.0f}%."))
    untagged = att_by.get("", {})
    if num(untagged.get("orders")) and att_orders:
        ins.append(insight("info", f"{int(num(untagged['orders']))} из {int(att_orders)} заказов из рекламы "
                                   f"пришли без utm_campaign — их нельзя привязать к кампании."))
    burners = [r for r in camps if num(r["cost"]) > 5000 and not att_by.get(str(r["campaign_id"]))]
    if burners:
        spend = sum(num(r["cost"]) for r in burners)
        ins.append(insight("warn", f"{len(burners)} кампаний потратили {fmt_money_short(spend)} "
                                   f"без заказов с их меткой."))
    if ins:
        w.append(insights("Реклама", ins))

    x, s = fill_buckets(P, ser, "b", ["cost", "clicks", "conv"])
    w.append(chart(f"Расход и клики {bucket_caption(P)}", x, [
        series("Расход", s["cost"], color=0),
        series("Цена клика", [safe_div(a, b) for a, b in zip(s["cost"], s["clicks"])], style="line",
               axis="right", color=2),
    ], kind="combo"))

    types: dict[str, dict] = {}
    for r in camps:
        r["type"] = campaign_type(r["name"])
        t = types.setdefault(r["type"], {"cost": 0, "clicks": 0, "impr": 0, "conv": 0, "orders": 0, "amt": 0,
                                         "cost_prev": 0})
        a = att_by.get(str(r["campaign_id"]), {})
        t["cost"] += num(r["cost"]); t["clicks"] += num(r["clicks"]); t["impr"] += num(r["impressions"])
        t["conv"] += num(r["conversions"]); t["orders"] += num(a.get("orders")); t["amt"] += num(a.get("amt"))
        t["cost_prev"] += num(r["cost_prev"])
    if types:
        w.append(share("Расход по типам кампаний", [(k, v["cost"]) for k, v in
                                                     sorted(types.items(), key=lambda t: -t[1]["cost"])]))
        w.append(table("Типы кампаний", [
            col("Тип"), col("Расход", "money"), col("Дин.", "pct", delta=True, better="down"),
            col("CPC", "money", better="down"), col("Заказы", "int"), col("Сумма заказов", "money"),
            col("ДРР", "pct", better="down"), col("CPO", "money", better="down"),
        ], [[k, v["cost"], rel_delta(v["cost"], v["cost_prev"]), safe_div(v["cost"], v["clicks"]), v["orders"],
             v["amt"], safe_div(v["cost"], v["amt"]), safe_div(v["cost"], v["orders"])]
            for k, v in sorted(types.items(), key=lambda t: -t[1]["cost"])],
            subtitle="Тип определяется по названию кампании"))

    rows = []
    for r in camps:
        a = att_by.get(str(r["campaign_id"]), {})
        rows.append([r["name"], r["cost"], rel_delta(r["cost"], r["cost_prev"]), r["clicks"],
                     safe_div(r["clicks"], r["impressions"]), safe_div(r["cost"], r["clicks"]),
                     r["conversions"], a.get("orders", 0), a.get("amt", 0),
                     safe_div(r["cost"], a.get("amt")), safe_div(r["cost"], a.get("orders"))])
    w.append(table("Кампании", [
        col("Кампания", width=2.4), col("Расход", "money"), col("Дин.", "pct", delta=True, better="down"),
        col("Клики", "int"), col("CTR", "pct"), col("CPC", "money", better="down"), col("Конв.", "int"),
        col("Заказы 1С", "int"), col("Сумма заказов", "money"), col("ДРР", "pct", better="down"),
        col("CPO", "money", better="down"),
    ], rows, collapsed=15, subtitle="Заказы 1С — по utm_campaign рекламного визита с покупкой"))
    w.append(note("Расход — из API Директа (логин Kixbox-cnx). ДРР кампании считается к сумме оформленных "
                  "заказов из её визитов; Метрика видит около двух третей заказов, поэтому ДРР и CPO по "
                  "кампаниям — оценка сверху. Для офлайн-эффекта рекламы действует коэффициент ROPO 1,36.",
                  title="Методика"))
    return w
