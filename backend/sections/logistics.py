"""Доставка: Dalli и Алгоритм — статусы, выкуп, сроки, стоимость, экономика доставки."""
from __future__ import annotations

from datetime import timedelta

from ch import lit, num
from context import C1_ROWS, IS_SERVICE, Ctx, by_window
from widgets import (chart, col, insight, insights, kpi, kpis, note, safe_div, series, share, table)

ID = "logistics"
TITLE = "Доставка"
ICON = "truck"

STATUS_GROUP = """multiIf(
    status IN ('COMPLETE', 'COURIERDELIVERED'), 'Выкуплен полностью',
    status IN ('PARTIALLY', 'PARTLYRETURNED', 'PARTLYRETURNING', 'COURIERPARTIALLY'), 'Выкуплен частично',
    status IN ('RETURNED', 'RETURNING', 'CANCELED', 'COURIERRETURN', 'COURIERCANCELED'), 'Отказ и возврат',
    'В пути')"""
FINAL = "status IN ('COMPLETE', 'COURIERDELIVERED', 'PARTIALLY', 'PARTLYRETURNED', 'PARTLYRETURNING', " \
        "'COURIERPARTIALLY', 'RETURNED', 'RETURNING', 'CANCELED', 'COURIERRETURN', 'COURIERCANCELED')"
COD = "paytype IN ('CARD', 'CASH')"


async def totals(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('createdate')} AS w,
    count() AS shipments,
    sum(items_total) AS value,
    sum(delivery_price) AS cost,
    countIf({STATUS_GROUP} = 'Выкуплен полностью') AS full,
    countIf({STATUS_GROUP} = 'Выкуплен частично') AS partial,
    countIf({STATUS_GROUP} = 'Отказ и возврат') AS refused,
    countIf({STATUS_GROUP} = 'В пути') AS in_transit,
    countIf({COD}) AS cod,
    sumIf(items_total, {COD} AND {FINAL}) AS cod_value_final,
    sumIf(receipt_summ, {COD} AND {FINAL}) AS cod_paid_final,
    avgIf(dateDiff('day', createdate, delivered_date), delivered_date IS NOT NULL
          AND status IN ('COMPLETE', 'PARTIALLY', 'PARTLYRETURNED')) AS lead_days,
    quantileIf(0.9)(dateDiff('day', createdate, delivered_date), delivered_date IS NOT NULL
          AND status IN ('COMPLETE', 'PARTIALLY', 'PARTLYRETURNED')) AS lead_p90
FROM kixbox.deliveries
WHERE {ctx.wfilter('createdate')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        if r:
            fin = num(r["full"]) + num(r["partial"]) + num(r["refused"])
            r["full_rate"] = safe_div(r["full"], fin)
            r["refuse_rate"] = safe_div(r["refused"], fin)
            r["buyout"] = safe_div(r["cod_paid_final"], r["cod_value_final"])
            r["avg_cost"] = safe_div(r["cost"], r["shipments"])
            r["cost_share"] = safe_div(r["cost"], r["value"])
    return res


async def carriers(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT carrier, {STATUS_GROUP} AS grp, count() AS n, sum(delivery_price) AS cost, sum(items_total) AS value,
    avgIf(dateDiff('day', createdate, delivered_date), delivered_date IS NOT NULL
          AND status IN ('COMPLETE', 'PARTIALLY', 'PARTLYRETURNED')) AS lead_days
FROM kixbox.deliveries
WHERE {ctx.cur_filter('createdate')}
GROUP BY carrier, grp"""
    return await ctx.q(sql)


async def weekly_buyout(ctx: Ctx) -> list[dict]:
    start = ctx.cur.end - timedelta(days=7 * 16)
    sql = f"""
SELECT toMonday(createdate) AS wk,
    sumIf(items_total, {COD} AND {FINAL}) AS value,
    sumIf(receipt_summ, {COD} AND {FINAL}) AS paid,
    countIf({COD}) AS cod_n,
    countIf({COD} AND {FINAL}) AS cod_final
FROM kixbox.deliveries
WHERE createdate BETWEEN {lit(start)} AND {lit(ctx.cur.end)}
GROUP BY wk ORDER BY wk"""
    return await ctx.q(sql)


async def towns(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT replaceRegexpAll(town, '\\\\s+(город|г\\\\.?)$', '') AS town, count() AS n,
    countIf({STATUS_GROUP} = 'Выкуплен полностью') AS full,
    countIf({STATUS_GROUP} = 'Отказ и возврат') AS refused,
    countIf({FINAL}) AS fin,
    avg(delivery_price) AS avg_cost,
    avgIf(dateDiff('day', createdate, delivered_date), delivered_date IS NOT NULL) AS lead_days,
    sum(items_total) AS value
FROM kixbox.deliveries
WHERE {ctx.cur_filter('createdate')}
GROUP BY town ORDER BY n DESC LIMIT 30"""
    return await ctx.q(sql)


async def status_titles(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT status_title AS t, count() AS n
FROM kixbox.deliveries WHERE {ctx.cur_filter('createdate')}
GROUP BY t ORDER BY n DESC"""
    return await ctx.q(sql)


async def service_income(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('toDate(doc_date)')} AS w, sumIf(amount, {IS_SERVICE}) AS income
FROM kixbox.c1_items WHERE {C1_ROWS} AND {ctx.wfilter('doc_date', 'datetime')}
GROUP BY w"""
    return by_window(await ctx.q(sql))


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    tot, car, wk, tw, st, inc = await ctx.gather(totals(ctx), carriers(ctx), weekly_buyout(ctx), towns(ctx),
                                                 status_titles(ctx), service_income(ctx))
    c, p, l = tot["cur"], tot["prev"], tot["ly"]
    ic, ip, il = inc["cur"], inc["prev"], inc["ly"]

    def margin(t, i):
        return num(i.get("income")) - num(t.get("cost")) if t else None

    w: list[dict] = [kpis(None, [
        kpi("Отправлений", c.get("shipments"), p.get("shipments"), l.get("shipments"), fmt="int", period=P),
        kpi("Товара в отправлениях", c.get("value"), p.get("value"), l.get("value"), period=P),
        kpi("Выкуплено полностью", c.get("full_rate"), p.get("full_rate"), l.get("full_rate"), fmt="pct",
            period=P, hint="Среди завершённых отправлений"),
        kpi("Отказы и возвраты", c.get("refuse_rate"), p.get("refuse_rate"), l.get("refuse_rate"), fmt="pct",
            better="down", period=P),
        kpi("Выкуп при оплате на месте", c.get("buyout"), p.get("buyout"), l.get("buyout"), fmt="pct",
            period=P, hint="Оплачено при получении к стоимости товара, завершённые отправления"),
        kpi("В пути сейчас", c.get("in_transit"), fmt="int", better="none"),
        kpi("Срок доставки", c.get("lead_days"), p.get("lead_days"), l.get("lead_days"), fmt="dec1",
            better="down", period=P, hint="Дней от передачи в службу до вручения"),
        kpi("Срок, 90% заказов", c.get("lead_p90"), p.get("lead_p90"), fmt="dec1", better="down", period=P),
        kpi("Стоимость доставки", c.get("cost"), p.get("cost"), l.get("cost"), better="down", period=P),
        kpi("Средняя на отправление", c.get("avg_cost"), p.get("avg_cost"), l.get("avg_cost"), better="down",
            period=P),
        kpi("Доставка к товару", c.get("cost_share"), p.get("cost_share"), l.get("cost_share"), fmt="pct",
            better="down", period=P),
        kpi("Доход от доставки минус затраты", margin(c, ic), margin(p, ip), margin(l, il), period=P,
            hint="Услуга доставки в реализациях 1С минус тариф Dalli и Алгоритма"),
    ])]

    ins = []
    if c.get("buyout") is not None:
        tone = "bad" if c["buyout"] < 0.5 else "info"
        ins.append(insight(tone, f"Выкуп заказов с оплатой при получении — {c['buyout'] * 100:.0f}% по сумме: "
                                 f"остальное возвращается после примерки."))
    m = margin(c, ic)
    if m is not None and m < 0:
        ins.append(insight("warn", f"Доставка в минусе на {abs(m) / 1000:,.0f} тыс ₽ — клиенты платят меньше "
                                   f"тарифа служб.".replace(",", " ")))
    if tw:
        slow = max((r for r in tw if num(r["n"]) >= 15), key=lambda r: num(r["lead_days"]), default=None)
        if slow and num(slow["lead_days"]) > 0:
            ins.append(insight("info", f"Дольше всего везут в {slow['town']}: {num(slow['lead_days']):.1f} дня "
                                       f"в среднем.".replace(".", ",", 1)))
    if ins:
        w.append(insights("Доставка", ins))

    if st:
        w.append(share("Статусы отправлений периода", [(r["t"], r["n"]) for r in st], fmt="int"))

    cars: dict[str, dict] = {}
    for r in car:
        a = cars.setdefault(r["carrier"], {"n": 0, "cost": 0, "value": 0, "full": 0, "partial": 0, "refused": 0,
                                           "lead_w": 0, "lead_n": 0})
        a["n"] += num(r["n"]); a["cost"] += num(r["cost"]); a["value"] += num(r["value"])
        key = {"Выкуплен полностью": "full", "Выкуплен частично": "partial", "Отказ и возврат": "refused"}.get(r["grp"])
        if key:
            a[key] += num(r["n"])
        if r.get("lead_days") is not None and key in ("full", "partial"):
            a["lead_w"] += num(r["lead_days"]) * num(r["n"]); a["lead_n"] += num(r["n"])
    if cars:
        rows = []
        for k, a in sorted(cars.items(), key=lambda t: -t[1]["n"]):
            fin = a["full"] + a["partial"] + a["refused"]
            rows.append([k, a["n"], safe_div(a["full"], fin), safe_div(a["refused"], fin),
                         safe_div(a["lead_w"], a["lead_n"]), safe_div(a["cost"], a["n"]), a["cost"]])
        w.append(table("Службы доставки", [
            col("Служба"), col("Отправлений", "int"), col("Полный выкуп", "pct"),
            col("Отказы", "pct", better="down"), col("Срок, дн", "dec1", better="down"),
            col("Тариф", "money", better="down"), col("Затраты", "money"),
        ], rows, sortable=False))

    if wk:
        labels = [str(r["wk"])[8:10] + "." + str(r["wk"])[5:7] for r in wk]
        w.append(chart("Выкуп оплаты при получении по неделям", labels, [
            series("Выкуп", [safe_div(r["paid"], r["value"]) for r in wk], fmt="pct", style="line", color=0),
            series("Отправлений", [r["cod_n"] for r in wk], fmt="int", axis="right", color=6),
        ], kind="combo", subtitle="Неделя передачи в службу, сумма оплаченного к стоимости товара",
            note="Последние 2–3 недели ещё дозревают: часть отправлений в пути."))

    if tw:
        w.append(table("Города доставки", [
            col("Город"), col("Отправлений", "int"), col("Полный выкуп", "pct"),
            col("Отказы", "pct", better="down"), col("Срок, дн", "dec1", better="down"),
            col("Тариф", "money", better="down"), col("Товара", "money"),
        ], [[r["town"] or "Не указан", r["n"], safe_div(r["full"], r["fin"]), safe_div(r["refused"], r["fin"]),
             r["lead_days"], r["avg_cost"], r["value"]] for r in tw], collapsed=12))
    w.append(note("Отправления Dalli и Алгоритма по дате создания. Все заказы с оплатой при получении "
                  "едут через Dalli. Выкуп — чек при вручении к стоимости вложения.", title="Методика"))
    return w
