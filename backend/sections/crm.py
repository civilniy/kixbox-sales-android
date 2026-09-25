"""Рассылки Mindbox: отправки, открытия, клики, отписки, лучшие рассылки и влияние на сайт."""
from __future__ import annotations

from ch import num
from context import IS_ORDER, Ctx, by_window
from widgets import (bucket_caption, chart, col, fill_buckets, insight, insights, kpi, kpis, note,
                     safe_div, series, share, table)

ID = "crm"
TITLE = "Рассылки"
ICON = "mail"

STATUS_COLS = """
    countIf(mailingStatusSystemName = 'Sent') AS sent,
    countIf(mailingStatusSystemName = 'Opened') AS opened,
    countIf(mailingStatusSystemName = 'Clicked') AS clicked,
    countIf(mailingStatusSystemName = 'Unsubscribe') AS unsub,
    countIf(mailingStatusSystemName = 'NotDelivered') AS not_delivered,
    countIf(mailingStatusSystemName = 'NotSent') AS not_sent"""


def _rates(r: dict) -> dict:
    if r:
        r["open_rate"] = safe_div(r.get("opened"), r.get("sent"))
        r["ctr"] = safe_div(r.get("clicked"), r.get("sent"))
        r["ctor"] = safe_div(r.get("clicked"), r.get("opened"))
        r["unsub_rate"] = safe_div(r.get("unsub"), r.get("sent"))
        r["fail_rate"] = safe_div(num(r.get("not_delivered")), r.get("sent"))
    return r


async def totals(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('toDate(dateTimeUtc + INTERVAL 3 HOUR)')} AS w, {STATUS_COLS},
    uniqExactIf(unmergedCustomerId, mailingStatusSystemName = 'Sent') AS reached
FROM kixbox.mb_Mailings_CustomerMessagesStatuses
WHERE {ctx.wfilter('dateTimeUtc', 'utc')}
GROUP BY w"""
    res = by_window(await ctx.q(sql))
    for r in res.values():
        _rates(r)
    return res


async def by_mailing(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH s AS (
    SELECT mailingInternalId AS mid, {STATUS_COLS}
    FROM kixbox.mb_Mailings_CustomerMessagesStatuses
    WHERE {ctx.cur_filter('dateTimeUtc', 'utc')}
    GROUP BY mid
),
m AS (
    SELECT id, any(name) AS name, any(type) AS type, any(channel) AS channel
    FROM kixbox.mb_Mailings_Mailings FINAL GROUP BY id
)
SELECT s.mid AS mid, m.name AS name, m.type AS type, m.channel AS channel,
    s.sent AS sent, s.opened AS opened, s.clicked AS clicked, s.unsub AS unsub,
    s.not_delivered AS not_delivered, s.not_sent AS not_sent
FROM s LEFT JOIN m ON m.id = s.mid
WHERE s.sent > 0
ORDER BY s.sent DESC"""
    return await ctx.q(sql)


async def daily(ctx: Ctx) -> list[dict]:
    d = "toDate(dateTimeUtc + INTERVAL 3 HOUR)"
    sql = f"""
SELECT {ctx.bexpr(d)} AS b, {STATUS_COLS}
FROM kixbox.mb_Mailings_CustomerMessagesStatuses
WHERE {ctx.cur_filter('dateTimeUtc', 'utc')}
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def mail_traffic(ctx: Ctx) -> dict[str, dict]:
    from datetime import timedelta
    a, b = ctx.cur.start - timedelta(days=1), ctx.cur.end + timedelta(days=1)
    sql = f"""
WITH v AS (
    SELECT visit_id, purchase_id, {ctx.wexpr('date', ('cur', 'prev'))} AS w
    FROM kixbox.ym_visits
    WHERE {ctx.wfilter('date', 'date', ('cur', 'prev'))} AND traffic_source = 'email'
),
att AS (SELECT w, arrayJoin(extractAll(purchase_id, '[0-9]+')) AS pid FROM v
        WHERE purchase_id NOT IN ('', '[]')),
ord AS (SELECT doc_number, sum(amount) AS amt FROM kixbox.c1_items
        WHERE {IS_ORDER} AND {ctx.range_filter('doc_date', ctx.prev.start - timedelta(days=1), b, 'datetime')}
        GROUP BY doc_number),
o AS (SELECT att.w AS w, uniqExact(ord.doc_number) AS orders, sum(ord.amt) AS amt
      FROM att INNER JOIN ord ON ord.doc_number = concat('KB', att.pid) GROUP BY w),
vv AS (SELECT w, uniqExact(visit_id) AS visits FROM v GROUP BY w)
SELECT vv.w AS w, vv.visits AS visits, o.orders AS orders, o.amt AS amt
FROM vv LEFT JOIN o ON o.w = vv.w"""
    return by_window(await ctx.q(sql))


CHANNELS = {"Email": "Email", "Sms": "SMS", "OSMICardsApp": "Карта OSMI", "MobilePush": "Push",
            "WebPush": "Web push", "Viber": "Viber"}


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    tot, mails, ser, mt = await ctx.gather(totals(ctx), by_mailing(ctx), daily(ctx), mail_traffic(ctx))
    c, p, l = tot["cur"], tot["prev"], tot["ly"]
    mc, mp = mt["cur"], mt["prev"]
    w: list[dict] = [kpis(None, [
        kpi("Отправлено", c.get("sent"), p.get("sent"), l.get("sent"), fmt="int", better="none", period=P),
        kpi("Получателей", c.get("reached"), p.get("reached"), l.get("reached"), fmt="int", period=P),
        kpi("Открытия", c.get("open_rate"), p.get("open_rate"), l.get("open_rate"), fmt="pct", period=P,
            hint="Открытые сообщения к отправленным"),
        kpi("Клики", c.get("ctr"), p.get("ctr"), l.get("ctr"), fmt="pct", period=P,
            hint="Сообщения с кликом к отправленным"),
        kpi("Клики из открытых", c.get("ctor"), p.get("ctor"), l.get("ctor"), fmt="pct", period=P),
        kpi("Отписки", c.get("unsub_rate"), p.get("unsub_rate"), l.get("unsub_rate"), fmt="pct",
            better="down", period=P),
        kpi("Не доставлено", c.get("fail_rate"), p.get("fail_rate"), l.get("fail_rate"), fmt="pct",
            better="down", period=P),
        kpi("Визиты из писем", mc.get("visits"), mp.get("visits"), fmt="int", period=P),
        kpi("Заказы из писем", mc.get("orders"), mp.get("orders"), fmt="int", period=P,
            hint="Заказы 1С, которые Метрика связала с визитом из рассылки"),
        kpi("Сумма заказов из писем", mc.get("amt"), mp.get("amt"), period=P),
    ])]

    # каналы и типы
    ch: dict[str, dict] = {}
    tp: dict[str, dict] = {}
    for r in mails:
        for bucket, key in ((ch, CHANNELS.get(r.get("channel") or "", r.get("channel") or "Другое")),
                            (tp, {"trigger": "Триггерные", "mass": "Массовые", "bulk": "Массовые"}.get(r.get("type") or "",
                                                                                   r.get("type") or "Другие"))):
            a = bucket.setdefault(key, {"sent": 0, "opened": 0, "clicked": 0, "unsub": 0, "n": 0})
            for f in ("sent", "opened", "clicked", "unsub"):
                a[f] += num(r[f])
            a["n"] += 1

    ins = []
    if tp:
        trig, bulk = tp.get("Триггерные"), tp.get("Массовые")
        if trig and bulk and bulk["sent"]:
            ct, cb = safe_div(trig["clicked"], trig["sent"]), safe_div(bulk["clicked"], bulk["sent"])
            if ct and cb:
                ins.append(insight("info", f"Триггерные письма кликают в {ct / cb:.1f} раза чаще массовых "
                                           f"({ct * 100:.2f}% против {cb * 100:.2f}%)."))
    if mails:
        best = max((r for r in mails if num(r["sent"]) >= 500), key=lambda r: safe_div(r["clicked"], r["sent"]) or 0,
                   default=None)
        if best:
            ins.append(insight("good", f"Лучший CTR: «{best.get('name') or best['mid']}» — "
                                       f"{(safe_div(best['clicked'], best['sent']) or 0) * 100:.2f}%."))
        worst = max((r for r in mails if num(r["sent"]) >= 500), key=lambda r: safe_div(r["unsub"], r["sent"]) or 0,
                    default=None)
        if worst and num(worst["unsub"]) > 0:
            ins.append(insight("warn", f"Больше всего отписок: «{worst.get('name') or worst['mid']}» — "
                                       f"{(safe_div(worst['unsub'], worst['sent']) or 0) * 100:.2f}%."))
    if ins:
        w.append(insights("Рассылки", ins))

    x, s = fill_buckets(P, ser, "b", ["sent", "opened", "clicked"])
    w.append(chart(f"Отправки и открытия {bucket_caption(P)}", x, [
        series("Отправлено", s["sent"], fmt="int", color=0),
        series("Открыто", s["opened"], fmt="int", color=1),
        series("CTR", [safe_div(a, b) for a, b in zip(s["clicked"], s["sent"])], fmt="pct", style="line",
               axis="right", color=2),
    ], kind="combo"))

    def rows(d):
        return [[k, v["sent"], safe_div(v["opened"], v["sent"]), safe_div(v["clicked"], v["sent"]),
                 safe_div(v["clicked"], v["opened"]), safe_div(v["unsub"], v["sent"]), v["n"]]
                for k, v in sorted(d.items(), key=lambda t: -t[1]["sent"])]
    cols = [col("Отправлено", "int"), col("Открытия", "pct"), col("CTR", "pct"), col("CTOR", "pct"),
            col("Отписки", "pct", better="down"), col("Рассылок", "int")]
    if ch:
        w.append(table("Каналы", [col("Канал")] + cols, rows(ch), sortable=False))
    if tp:
        w.append(table("Типы рассылок", [col("Тип")] + cols, rows(tp), sortable=False))
    w.append(table("Рассылки", [
        col("Рассылка", width=2.4), col("Канал"), col("Отправлено", "int"), col("Открытия", "pct"),
        col("CTR", "pct"), col("CTOR", "pct"), col("Отписки", "pct", better="down"),
    ], [[r.get("name") or r["mid"], CHANNELS.get(r.get("channel") or "", r.get("channel") or ""), r["sent"],
         safe_div(r["opened"], r["sent"]), safe_div(r["clicked"], r["sent"]), safe_div(r["clicked"], r["opened"]),
         safe_div(r["unsub"], r["sent"])] for r in mails], collapsed=15))
    w.append(note("Статусы сообщений из выгрузки Mindbox. Открытия считаются по событиям Opened, "
                  "у SMS их нет, поэтому общий Open Rate занижен долей SMS.", title="Методика"))
    return w
