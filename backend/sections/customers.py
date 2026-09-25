"""Клиенты по Mindbox: новые и повторные, омниканальность, частота, когорты, база и баллы."""
from __future__ import annotations

from datetime import date, timedelta

from ch import lit, lits, num, utc_bounds
from config import MB_EXCLUDED_STATUSES, ONLINE_ID, STORE_IDS
from context import Ctx
from periods import MONTHS_NOM, add_months, month_start
from sections import common
from widgets import (bucket_caption, chart, col, fill_buckets, heatmap, insight, insights, kpi, kpis,
                     note, safe_div, series, share, table)

ID = "customers"
TITLE = "Клиенты"
ICON = "people"


def _all_orders_cte(since: date) -> str:
    """Все заказы опознанных клиентов с суммами — для истории, когорт и частоты."""
    a, _ = utc_bounds(since, since)
    return f"""
ao AS (
    SELECT id, unmergedCustomerId AS cid, pointOfContactInternalId AS poc,
        toDate(firstDateTimeUtc + INTERVAL 3 HOUR) AS d
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE unmergedCustomerId IS NOT NULL AND coalesce(_isDeleted, false) = false
      AND firstDateTimeUtc >= {a}
),
ap AS (
    SELECT orderId, sum(priceOfLine) AS amt
    FROM kixbox.mb_ProcessingOrders_Purchases FINAL
    WHERE statusInternalId NOT IN {lits(MB_EXCLUDED_STATUSES)} AND orderId IN (SELECT id FROM ao)
    GROUP BY orderId
),
hist AS (
    SELECT ao.cid AS cid, ao.poc AS poc, ao.d AS d, ap.amt AS amt
    FROM ao INNER JOIN ap ON ap.orderId = ao.id WHERE ap.amt > 0
)"""


async def buyers_series(ctx: Ctx) -> list[dict]:
    b = ctx.bexpr("op.d")
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))},
firsts AS (
    SELECT unmergedCustomerId AS cid, min(firstDateTimeUtc) AS first_ts
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE unmergedCustomerId IN (SELECT cid FROM op WHERE cid IS NOT NULL)
      AND coalesce(_isDeleted, false) = false
    GROUP BY cid
)
SELECT {b} AS b,
    uniqExactIf(op.cid, toDate(f.first_ts + INTERVAL 3 HOUR) = op.d) AS new_buyers,
    uniqExactIf(op.cid, toDate(f.first_ts + INTERVAL 3 HOUR) < op.d) AS repeat_buyers,
    sumIf(op.amt, toDate(f.first_ts + INTERVAL 3 HOUR) = op.d) AS new_amt,
    sumIf(op.amt, toDate(f.first_ts + INTERVAL 3 HOUR) < op.d) AS repeat_amt
FROM op INNER JOIN firsts AS f ON f.cid = op.cid
GROUP BY b ORDER BY b"""
    return await ctx.q(sql)


async def omni(ctx: Ctx) -> list[dict]:
    """Каналы покупателей текущего периода и за 12 месяцев до конца периода."""
    since = min(ctx.cur.end - timedelta(days=364), ctx.cur.start)
    kind = ("multiIf(on_{s} > 0 AND off_{s} > 0, 'Онлайн и магазины', on_{s} > 0, 'Только онлайн', "
            "off_{s} > 0, 'Только магазины', 'Другие каналы')")
    sql = f"""
WITH {_all_orders_cte(since)},
pc AS (
    SELECT cid,
        countIf(poc = {lit(ONLINE_ID)} AND in_p) AS on_p,
        countIf(poc IN {lits(STORE_IDS)} AND in_p) AS off_p,
        countIf(in_p) AS n_p, sumIf(amt, in_p) AS amt_p,
        countIf(poc = {lit(ONLINE_ID)} AND in_y) AS on_y,
        countIf(poc IN {lits(STORE_IDS)} AND in_y) AS off_y,
        countIf(in_y) AS n_y, sumIf(amt, in_y) AS amt_y
    FROM (
        SELECT cid, poc, amt,
            d BETWEEN {lit(ctx.cur.start)} AND {lit(ctx.cur.end)} AS in_p,
            d BETWEEN {lit(ctx.cur.end - timedelta(days=364))} AND {lit(ctx.cur.end)} AS in_y
        FROM hist WHERE d <= {lit(ctx.cur.end)}
    )
    GROUP BY cid
)
SELECT 'period' AS scope, {kind.format(s='p')} AS kind, count() AS buyers, sum(amt_p) AS amt,
    sum(n_p) AS orders
FROM pc WHERE n_p > 0 GROUP BY kind
UNION ALL
SELECT 'year' AS scope, {kind.format(s='y')} AS kind, count() AS buyers, sum(amt_y) AS amt,
    sum(n_y) AS orders
FROM pc WHERE n_y > 0 GROUP BY kind"""
    return await ctx.q(sql)


async def frequency(ctx: Ctx) -> list[dict]:
    since = ctx.cur.end - timedelta(days=364)
    sql = f"""
WITH {_all_orders_cte(since)}
SELECT multiIf(n = 1, '1 покупка', n = 2, '2', n = 3, '3', n <= 5, '4–5', n <= 9, '6–9', '10 и больше') AS band,
    min(n) AS ord, count() AS buyers, sum(amt) AS amt
FROM (SELECT cid, count() AS n, sum(amt) AS amt FROM hist WHERE d <= {lit(ctx.cur.end)} GROUP BY cid)
GROUP BY band ORDER BY ord"""
    return await ctx.q(sql)


async def recency(ctx: Ctx) -> list[dict]:
    end = ctx.cur.end
    a, _ = utc_bounds(date(2016, 1, 1), end)
    _, b = utc_bounds(end, end)
    sql = f"""
WITH last AS (
    SELECT unmergedCustomerId AS cid, max(firstDateTimeUtc) AS last_ts, count() AS n
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE unmergedCustomerId IS NOT NULL AND coalesce(_isDeleted, false) = false
      AND firstDateTimeUtc < {b}
    GROUP BY cid
)
SELECT multiIf(days <= 30, 1, days <= 90, 2, days <= 180, 3, days <= 365, 4, days <= 730, 5, 6) AS band,
    count() AS buyers, avg(n) AS avg_orders
FROM (SELECT cid, n, dateDiff('day', toDate(last_ts + INTERVAL 3 HOUR), toDate({lit(end)})) AS days FROM last)
GROUP BY band ORDER BY band"""
    return await ctx.q(sql)


async def cohorts(ctx: Ctx) -> list[dict]:
    end = ctx.cur.end
    first_month = add_months(month_start(end), -11)
    sql = f"""
WITH {_all_orders_cte(add_months(first_month, -1))},
f AS (
    SELECT unmergedCustomerId AS cid, toStartOfMonth(toDate(min(firstDateTimeUtc) + INTERVAL 3 HOUR)) AS cm
    FROM kixbox.mb_ProcessingOrders_Orders FINAL
    WHERE unmergedCustomerId IS NOT NULL AND coalesce(_isDeleted, false) = false
    GROUP BY cid
    HAVING cm >= {lit(first_month)} AND cm <= {lit(month_start(end))}
)
SELECT f.cm AS cm, dateDiff('month', f.cm, toStartOfMonth(hist.d)) AS k, uniqExact(hist.cid) AS buyers,
    sum(hist.amt) AS amt
FROM hist INNER JOIN f ON f.cid = hist.cid
WHERE hist.d <= {lit(end)}
GROUP BY cm, k ORDER BY cm, k"""
    return await ctx.q(sql)


async def base(ctx: Ctx) -> dict:
    sql = """
SELECT count() AS total,
    countIf(email != '' AND email_invalid = 0) AS with_email,
    countIf(phone != '' AND phone_invalid = 0) AS with_phone,
    countIf(sex = 'female') AS female, countIf(sex = 'male') AS male,
    countIf(JSONExtractString(custom_fields, 'bPRProcentskidki') = '3') AS l3,
    countIf(JSONExtractString(custom_fields, 'bPRProcentskidki') = '5') AS l5,
    countIf(JSONExtractString(custom_fields, 'bPRProcentskidki') = '7') AS l7,
    countIf(JSONExtractString(custom_fields, 'bPRProcentskidki') = '10') AS l10,
    countIf(JSONExtractString(custom_fields, 'bPRProcentskidki') = '') AS l0,
    countIf(birth_date != '') AS with_birth,
    avgIf(dateDiff('year', toDate(parseDateTimeBestEffortOrNull(birth_date)), today()),
          parseDateTimeBestEffortOrNull(birth_date) IS NOT NULL
          AND toYear(parseDateTimeBestEffortOrNull(birth_date)) BETWEEN 1940 AND 2012) AS avg_age
FROM kixbox.mb_customers FINAL"""
    rows = await ctx.q(sql)
    return rows[0] if rows else {}


async def bonus(ctx: Ctx) -> dict[str, dict]:
    sql = f"""
SELECT {ctx.wexpr('toDate(dateTimeUtc + INTERVAL 3 HOUR)')} AS w,
    sumIf(changeAmount, kindSystemName = 'RetailOrderBonus') AS earned,
    -sumIf(changeAmount, kindSystemName = 'RetailOrderPayment') AS spent,
    sumIf(changeAmount, kindSystemName = 'Custom' AND changeAmount > 0) AS promo,
    -sumIf(changeAmount, kindSystemName = 'Expired') AS expired,
    uniqExactIf(unmergedCustomerId, kindSystemName = 'RetailOrderPayment') AS payers
FROM kixbox.mb_ProcessingOrders_BonusPointChanges_v3 FINAL
WHERE {ctx.wfilter('dateTimeUtc', 'utc')} AND coalesce(_isDeleted, false) = false
GROUP BY w"""
    out = {"cur": {}, "prev": {}, "ly": {}}
    for r in await ctx.q(sql):
        out[r["w"]] = r
    return out


async def age_sex(ctx: Ctx) -> list[dict]:
    """Покупатели периода по полу и возрасту из карточек клиентов."""
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))},
b AS (SELECT cid, sum(amt) AS amt FROM op WHERE cid IS NOT NULL GROUP BY cid)
SELECT multiIf(c.sex = 'female', 'Женщины', c.sex = 'male', 'Мужчины', 'Не указан') AS sex,
    multiIf(age = 0, 'Не указан', age < 18, 'до 18', age < 25, '18–24', age < 35, '25–34', age < 45, '35–44',
            '45+') AS age_band,
    count() AS buyers, sum(b.amt) AS amt
FROM b INNER JOIN (
    SELECT toInt64OrZero(mindbox_id) AS cid, sex,
        if(toYear(parseDateTimeBestEffortOrNull(birth_date)) BETWEEN 1940 AND 2012,
           dateDiff('year', toDate(parseDateTimeBestEffortOrNull(birth_date)), today()), 0) AS age
    FROM kixbox.mb_customers FINAL
) AS c ON c.cid = b.cid
GROUP BY sex, age_band"""
    return await ctx.q(sql)


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    (nb, net, ser, om, fr, rec, coh, bs, bn, ags) = await ctx.gather(
        common.mb_new_customers(ctx), common.mb_network(ctx), buyers_series(ctx), omni(ctx),
        frequency(ctx), recency(ctx), cohorts(ctx), base(ctx), bonus(ctx), age_sex(ctx))
    c, p, l = nb["cur"], nb["prev"], nb["ly"]

    def rep(r):
        return num(r.get("buyers")) - num(r.get("new_buyers")) if r else None

    def per(r):
        return safe_div(r.get("amt"), r.get("buyers")) if r else None

    w: list[dict] = [kpis(None, [
        kpi("Покупатели", c.get("buyers"), p.get("buyers"), l.get("buyers"), fmt="int", period=P),
        kpi("Новые", c.get("new_buyers"), p.get("new_buyers"), l.get("new_buyers"), fmt="int", period=P),
        kpi("Повторные", rep(c), rep(p), rep(l), fmt="int", period=P),
        kpi("Доля новых", safe_div(c.get("new_buyers"), c.get("buyers")),
            safe_div(p.get("new_buyers"), p.get("buyers")), safe_div(l.get("new_buyers"), l.get("buyers")),
            fmt="pct", better="none", period=P),
        kpi("Выручка на покупателя", per(c), per(p), per(l), period=P),
        kpi("Выручка повторных", safe_div(num(c.get("amt")) - num(c.get("new_amt")), c.get("amt")),
            safe_div(num(p.get("amt")) - num(p.get("new_amt")), p.get("amt")),
            safe_div(num(l.get("amt")) - num(l.get("new_amt")), l.get("amt")), fmt="pct", period=P,
            hint="Доля выручки опознанных клиентов, купивших не впервые"),
        kpi("Клиентская база", bs.get("total"), fmt="int", hint="Карточки Mindbox на дату загрузки"),
        kpi("С рабочим email", safe_div(bs.get("with_email"), bs.get("total")), fmt="pct"),
        kpi("С телефоном", safe_div(bs.get("with_phone"), bs.get("total")), fmt="pct"),
        kpi("Средний возраст", bs.get("avg_age"), fmt="dec1",
            hint=f"По {int(num(bs.get('with_birth')))} клиентам с датой рождения"),
    ])]

    # выводы
    ins = []
    year = {r["kind"]: r for r in om if r["scope"] == "year"}
    per_ = {r["kind"]: r for r in om if r["scope"] == "period"}
    tot_year = sum(num(r["buyers"]) for r in year.values()) or 1
    both = year.get("Онлайн и магазины")
    if both:
        amt_year = sum(num(r["amt"]) for r in year.values()) or 1
        ins.append(insight("info", f"Омниканальные клиенты — {num(both['buyers']) / tot_year * 100:.0f}% "
                                   f"покупателей года и {num(both['amt']) / amt_year * 100:.0f}% их выручки."))
        one = [r for k, r in year.items() if k != "Онлайн и магазины"]
        avg_one = safe_div(sum(num(r["amt"]) for r in one), sum(num(r["buyers"]) for r in one))
        avg_both = safe_div(both["amt"], both["buyers"])
        if avg_one and avg_both:
            ins.append(insight("good", f"Покупатель обоих каналов тратит в {avg_both / avg_one:.1f} раза больше "
                                       f"одноканального за год."))
    if fr:
        one = next((r for r in fr if r["band"] == "1 покупка"), None)
        tot = sum(num(r["buyers"]) for r in fr) or 1
        if one:
            ins.append(insight("warn", f"{num(one['buyers']) / tot * 100:.0f}% покупателей за 12 месяцев "
                                       f"купили только один раз."))
    if rec:
        risk = next((r for r in rec if int(r["band"]) == 4), None)
        if risk:
            ins.append(insight("warn", f"{int(num(risk['buyers']))} клиентов не покупали 6–12 месяцев — "
                                       f"окно для реактивации."))
    if ins:
        w.append(insights("Клиенты", ins))

    x, s = fill_buckets(P, ser, "b", ["new_buyers", "repeat_buyers", "new_amt", "repeat_amt"])
    w.append(chart(f"Новые и повторные покупатели {bucket_caption(P)}", x, [
        series("Новые", s["new_buyers"], fmt="int", color=2),
        series("Повторные", s["repeat_buyers"], fmt="int", color=0),
    ], stacked=True, subtitle="Опознанные клиенты, все каналы"))
    w.append(chart(f"Выручка новых и повторных {bucket_caption(P)}", x, [
        series("Новые", s["new_amt"], color=2), series("Повторные", s["repeat_amt"], color=0),
    ], stacked=True))

    if per_:
        w.append(share("Каналы покупателей периода",
                       [(k, v["buyers"]) for k, v in sorted(per_.items(), key=lambda t: -num(t[1]["buyers"]))],
                       fmt="int"))
    if year:
        w.append(table("Каналы покупателей за 12 месяцев", [
            col("Сегмент"), col("Покупатели", "int"), col("Доля", "pct", bar=True), col("Выручка", "money"),
            col("На клиента", "money"), col("Заказов на клиента", "dec2"),
        ], [[k, v["buyers"], num(v["buyers"]) / tot_year, v["amt"], safe_div(v["amt"], v["buyers"]),
             safe_div(v["orders"], v["buyers"])] for k, v in sorted(year.items(), key=lambda t: -num(t[1]["buyers"]))],
            sortable=False))

    if fr:
        tot_b = sum(num(r["buyers"]) for r in fr) or 1
        tot_a = sum(num(r["amt"]) for r in fr) or 1
        w.append(table("Частота покупок за 12 месяцев", [
            col("Покупок"), col("Клиентов", "int"), col("Доля клиентов", "pct", bar=True),
            col("Выручка", "money"), col("Доля выручки", "pct"), col("На клиента", "money"),
        ], [[r["band"], r["buyers"], num(r["buyers"]) / tot_b, r["amt"], num(r["amt"]) / tot_a,
             safe_div(r["amt"], r["buyers"])] for r in fr], sortable=False))

    if rec:
        names = {1: "до 30 дней", 2: "31–90 дней", 3: "3–6 месяцев", 4: "6–12 месяцев", 5: "1–2 года",
                 6: "больше 2 лет"}
        w.append(chart("Давность последней покупки", [names[int(r["band"])] for r in rec], [
            series("Клиентов", [r["buyers"] for r in rec], fmt="int", color=0),
        ], subtitle="Вся база опознанных покупателей на конец периода"))

    if coh:
        months = sorted({str(r["cm"])[:10] for r in coh})
        size = {}
        grid: dict[str, dict[int, float]] = {}
        for r in coh:
            m, k = str(r["cm"])[:10], int(r["k"])
            if k == 0:
                size[m] = num(r["buyers"])
            grid.setdefault(m, {})[k] = num(r["buyers"])
        max_k = 11
        vals = []
        ylab = []
        for m in months:
            d = date.fromisoformat(m)
            ylab.append(f"{MONTHS_NOM[d.month - 1][:3]} {str(d.year)[2:]} · {int(size.get(m, 0))}")
            row = []
            for k in range(0, max_k + 1):
                if add_months(d, k) > month_start(ctx.cur.end):
                    row.append(None)
                else:
                    row.append(safe_div(grid[m].get(k, 0), size.get(m)) if k else 1.0)
            vals.append(row)
        w.append(heatmap("Когорты: возвращаемость", [f"М{k}" for k in range(0, max_k + 1)], ylab, vals,
                         fmt="pct", subtitle="Доля покупателей когорты первого заказа, купивших снова в месяц k",
                         note="М0 — месяц первой покупки. Все каналы, опознанные клиенты."))

    b_c, b_p = bn["cur"], bn["prev"]
    if b_c:
        w.append(kpis("Бонусные баллы", [
            kpi("Начислено за покупки", b_c.get("earned"), b_p.get("earned"), fmt="int", period=P),
            kpi("Списано в оплату", b_c.get("spent"), b_p.get("spent"), fmt="int", period=P),
            kpi("Промо-начисления", b_c.get("promo"), b_p.get("promo"), fmt="int", better="none", period=P),
            kpi("Сгорело", b_c.get("expired"), b_p.get("expired"), fmt="int", better="none", period=P),
            kpi("Платили баллами", b_c.get("payers"), b_p.get("payers"), fmt="int", period=P,
                hint="Клиентов, списавших баллы"),
            kpi("Сгорает от выданного", safe_div(b_c.get("expired"), num(b_c.get("earned")) + num(b_c.get("promo"))),
                fmt="pct", better="down"),
        ]))

    levels = [("Уровень 0 · 3%", bs.get("l3")), ("Уровень 1 · 5%", bs.get("l5")), ("Уровень 2 · 7%", bs.get("l7")),
              ("Уровни 3–4 · 10%", bs.get("l10")), ("Без уровня", bs.get("l0"))]
    w.append(share("Программа лояльности", levels, fmt="int", subtitle="Клиенты базы по проценту скидки"))

    if ags:
        order = ["до 18", "18–24", "25–34", "35–44", "45+", "Не указан"]
        agg = {}
        for r in ags:
            a = agg.setdefault(r["age_band"], {"Женщины": 0, "Мужчины": 0, "Не указан": 0, "amt": 0})
            a[r["sex"]] += num(r["buyers"])
            a["amt"] += num(r["amt"])
        labels = [o for o in order if o in agg]
        w.append(chart("Покупатели периода: пол и возраст", labels, [
            series("Женщины", [agg[o]["Женщины"] for o in labels], fmt="int", color=4),
            series("Мужчины", [agg[o]["Мужчины"] for o in labels], fmt="int", color=0),
            series("Не указан", [agg[o]["Не указан"] for o in labels], fmt="int", color=6),
        ], stacked=True, subtitle="По анкетам Mindbox"))
    w.append(note("Клиент — unmergedCustomerId Mindbox. Анонимные розничные чеки в клиентские метрики "
                  "не входят. Новый покупатель — первый заказ в истории Mindbox с 2016 года.",
                  title="Методика"))
    return w
