"""Сводка: план месяца, главные показатели всех контуров и автоматические выводы."""
from __future__ import annotations

import calendar

from ch import lit, num
from context import (C1_ROWS, IS_GOODS, IS_RET, Ctx)
from periods import MONTHS_GEN, MONTHS_NOM, month_start
from sections import common
from widgets import (bucket_caption, chart, fill_buckets, fmt_money_short, fmt_pct, fmt_pp,
                     hero, insight, insights, kpi, kpis, rel_delta, safe_div, series, share)

ID = "overview"
TITLE = "Сводка"
ICON = "dashboard"


async def plan_rows(ctx: Ctx) -> list[dict]:
    m = month_start(ctx.end)
    sql = f"""
SELECT date, day_num, net_day, net_cum, net_cum_ly, plan_low_cum, plan_high_cum, forecast_cum,
    forecast_month, rate_7d, need_per_day_low, days_left, plan_low, plan_high, single_plan,
    mtd_sales, mtd_returns, mtd_net, mtd_returns_pct
FROM kixbox.plan_fact
WHERE month = {lit(m)} AND site = 'Kixbox'
ORDER BY date"""
    return await ctx.q(sql)


async def brand_moves(ctx: Ctx) -> list[dict]:
    sql = f"""
SELECT brand,
    sumIf(multiIf({IS_GOODS}, amount, {IS_RET}, -amount, 0), {ctx.cur_filter('doc_date', 'datetime')}) AS cur,
    sumIf(multiIf({IS_GOODS}, amount, {IS_RET}, -amount, 0), NOT {ctx.cur_filter('doc_date', 'datetime')}) AS prev
FROM kixbox.c1_items
WHERE {C1_ROWS} AND {ctx.wfilter('doc_date', 'datetime', ('cur', 'prev'))} AND brand != ''
GROUP BY brand
HAVING cur > 0 OR prev > 0"""
    return await ctx.q(sql)


def _plan_widgets(ctx: Ctx, rows: list[dict]) -> list[dict]:
    rows = [r for r in rows if r.get("date")]
    if not rows:
        return []
    fact = [r for r in rows if r.get("net_cum") is not None]
    last = fact[-1] if fact else rows[0]
    plan = num(last.get("plan_low"))
    plan_high = num(last.get("plan_high"))
    net = num(last.get("net_cum"))
    day = int(num(last.get("day_num"), 0))
    first = rows[0]["date"]
    y, mth = int(str(first)[:4]), int(str(first)[5:7])
    days_in_month = calendar.monthrange(y, mth)[1]
    forecast = num(last.get("forecast_month"))
    ly_same_day = num(last.get("net_cum_ly"))
    ly_month = num(rows[-1].get("net_cum_ly"))
    plan_to_date = num(last.get("plan_low_cum"))

    items = [
        {"label": "Прогноз на месяц", "value": forecast, "format": "money"},
        {"label": "Нужно в день до плана", "value": last.get("need_per_day_low"), "format": "money"},
        {"label": "Темп за 7 дней", "value": last.get("rate_7d"), "format": "money", "suffix": "/день"},
        {"label": "План к этой дате", "value": plan_to_date, "format": "money"},
        {"label": "Год назад к этой дате", "value": ly_same_day, "format": "money"},
        {"label": "Возвраты месяца", "value": num(last.get("mtd_returns_pct")) / 100, "format": "pct"},
    ]
    fc_ratio = safe_div(forecast, plan)
    badge = None
    if fc_ratio is not None:
        tone = "good" if fc_ratio >= 1 else ("warn" if fc_ratio >= 0.9 else "bad")
        badge = {"text": f"Прогноз {fmt_pct(fc_ratio)} плана", "tone": tone}
    subtitle = f"из {fmt_money_short(plan)} плана"
    if plan_high and plan_high != plan:
        subtitle = f"из {fmt_money_short(plan)} – {fmt_money_short(plan_high)} плана"
    ly_d = rel_delta(net, ly_same_day)
    if ly_d is not None:
        subtitle += f" · {fmt_pct(ly_d, signed=True)} к прошлому году"
    widgets = [hero(
        title=f"План {MONTHS_GEN[mth - 1]} · день {day} из {days_in_month}",
        value=net, subtitle=subtitle,
        progress=safe_div(net, plan), marker=day / days_in_month, items=items, badge=badge)]

    x = [str(r["date"])[8:10] for r in rows]
    widgets.append(chart(
        "Выполнение плана накопительно",
        x,
        [
            series("Факт", [r.get("net_cum") for r in rows], style="bar", color=0),
            series("План", [r.get("plan_low_cum") for r in rows], style="line", color=3),
            series("Прогноз", [r.get("forecast_cum") for r in rows], style="line", color=2),
            series("Год назад", [r.get("net_cum_ly") for r in rows], style="line", color=1),
        ],
        subtitle=f"{MONTHS_NOM[mth - 1]}, чистая выручка ИМ, ₽ · год назад {fmt_money_short(ly_month)} за месяц",
        kind="combo"))
    return widgets


def _insights(ctx: Ctx, c1, ym, dr, net, plan, moves) -> list[dict]:
    out: list[dict] = []
    cur, prev, ly = c1["cur"], c1["prev"], c1["ly"]
    pname = ctx.period.prev_name
    d = rel_delta(cur.get("net"), prev.get("net"))
    if d is not None:
        tone = "good" if d > 0.03 else ("bad" if d < -0.03 else "info")
        out.append(insight(tone, f"Чистая выручка ИМ {fmt_money_short(num(cur.get('net')))} — "
                                 f"{fmt_pct(d, True)} {pname}."))
    d_ly = rel_delta(cur.get("net"), ly.get("net"))
    if d_ly is not None and not ctx.period.prev_is_ly:
        tone = "good" if d_ly > 0.03 else ("bad" if d_ly < -0.03 else "info")
        out.append(insight(tone, f"К прошлому году выручка {fmt_pct(d_ly, True)}."))
    # драйверы: заказы, чек, возвраты
    do = rel_delta(cur.get("orders"), prev.get("orders"))
    da = rel_delta(cur.get("aov"), prev.get("aov"))
    if do is not None and da is not None:
        driver = "количество заказов" if abs(do) >= abs(da) else "средний чек"
        out.append(insight("info", f"Главный драйвер — {driver}: заказы {fmt_pct(do, True)}, "
                                   f"чек {fmt_pct(da, True)}."))
    rr, rr_p = cur.get("ret_rate"), prev.get("ret_rate")
    if rr is not None and rr_p is not None and abs(rr - rr_p) >= 0.03:
        tone = "bad" if rr > rr_p else "good"
        out.append(insight(tone, f"Возвраты {fmt_pct(rr)} от отгрузок ({fmt_pp(rr - rr_p)})."))
    # трафик и конверсия
    yc, yp = ym["cur"], ym["prev"]
    cr = safe_div(cur.get("orders"), yc.get("visits"))
    crp = safe_div(prev.get("orders"), yp.get("visits"))
    if cr is not None and crp:
        dv = rel_delta(yc.get("visits"), yp.get("visits"))
        out.append(insight("good" if cr >= crp else "warn",
                           f"Конверсия визит → заказ {fmt_pct(cr)} ({fmt_pp(cr - crp)}), "
                           f"визиты {fmt_pct(dv, True)}."))
    drr = safe_div(dr["cur"].get("cost"), cur.get("net"))
    drr_p = safe_div(dr["prev"].get("cost"), prev.get("net"))
    if drr is not None:
        tone = "bad" if drr > 0.15 else ("warn" if drr > 0.1 else "good")
        extra = f" ({fmt_pp(drr - drr_p)})" if drr_p is not None else ""
        out.append(insight(tone, f"ДРР Директа {fmt_pct(drr)} от чистой выручки{extra}."))
    # сеть
    nc, np_ = net["cur"], net["prev"]
    if nc.get("total"):
        ds = rel_delta(nc.get("stores"), np_.get("stores"))
        out.append(insight("info", f"Розница {fmt_money_short(num(nc.get('stores')))} "
                                   f"({fmt_pct(ds, True)}), доля в сети {fmt_pct(nc.get('retail_share'))}."))
    # бренды
    movers = sorted(((num(r["cur"]) - num(r["prev"]), r["brand"]) for r in moves), reverse=True)
    if movers:
        up = [m for m in movers[:2] if m[0] > 0]
        down = [m for m in movers[-2:][::-1] if m[0] < 0]
        if up:
            out.append(insight("good", "Растут: " + ", ".join(
                f"{b} +{fmt_money_short(v)}" for v, b in up) + "."))
        if down:
            out.append(insight("bad", "Проседают: " + ", ".join(
                f"{b} −{fmt_money_short(-v)}" for v, b in down) + "."))
    # план
    fact = [r for r in plan if r.get("net_cum") is not None]
    if fact:
        last = fact[-1]
        fc = safe_div(last.get("forecast_month"), last.get("plan_low"))
        if fc is not None:
            need = num(last.get("need_per_day_low"))
            rate = num(last.get("rate_7d"))
            tone = "good" if fc >= 1 else "bad"
            txt = f"Прогноз месяца {fmt_pct(fc)} плана"
            if fc < 1 and rate:
                txt += f": нужно {fmt_money_short(need)} в день при темпе {fmt_money_short(rate)}"
            out.append(insight(tone, txt + "."))
    return out


async def build(ctx: Ctx) -> list[dict]:
    c1, ser, ser_ly, ym, dr, net, plan, moves, buyers = await ctx.gather(
        common.c1_kpis(ctx), common.c1_series(ctx), common.c1_net_ly_series(ctx),
        common.metrika_kpis(ctx), common.direct_kpis(ctx), common.mb_network(ctx),
        plan_rows(ctx), brand_moves(ctx), common.mb_new_customers(ctx))
    P = ctx.period
    cur, prev, ly = c1["cur"], c1["prev"], c1["ly"]
    x, s = fill_buckets(P, ser, "b", ["net", "sales", "returns", "orders", "demand"])
    _, s_ly = fill_buckets(P, ser_ly, "b", ["net", "orders"])

    w: list[dict] = []
    w.extend(_plan_widgets(ctx, plan))
    w.append(insights("Главное за период", _insights(ctx, c1, ym, dr, net, plan, moves)))

    w.append(kpis("Интернет-магазин", [
        kpi("Чистая выручка", cur.get("net"), prev.get("net"), ly.get("net"), spark=s["net"], period=P,
            hint="Отгрузки и доставка минус возвраты, склады 400 и 401, по датам документов"),
        kpi("Отгрузки", cur.get("sales"), prev.get("sales"), ly.get("sales"), period=P),
        kpi("Возвраты", cur.get("returns"), prev.get("returns"), ly.get("returns"), better="down", period=P),
        kpi("Доля возвратов", cur.get("ret_rate"), prev.get("ret_rate"), ly.get("ret_rate"), fmt="pct",
            better="down", period=P),
        kpi("Заказы", cur.get("orders"), prev.get("orders"), ly.get("orders"), fmt="int",
            spark=s["orders"], period=P),
        kpi("Сумма заказов", cur.get("demand"), prev.get("demand"), ly.get("demand"), period=P,
            hint="Спрос: всё оформленное, включая будущие отмены"),
        kpi("Средний чек", cur.get("aov"), prev.get("aov"), ly.get("aov"), period=P),
        kpi("Товаров в заказе", cur.get("upt"), prev.get("upt"), ly.get("upt"), fmt="dec2", period=P),
        kpi("Средняя скидка", cur.get("discount"), prev.get("discount"), ly.get("discount"), fmt="pct",
            better="down", period=P, hint="От базовой цены по отгрузкам"),
        kpi("Продано штук", cur.get("units"), prev.get("units"), ly.get("units"), fmt="int", period=P),
    ]))

    yc, yp, yl = ym["cur"], ym["prev"], ym["ly"]
    dc, dp, dl = dr["cur"], dr["prev"], dr["ly"]
    _, mser = fill_buckets(P, await common.metrika_series(ctx), "b", ["visits"])
    w.append(kpis("Трафик и реклама", [
        kpi("Визиты", yc.get("visits"), yp.get("visits"), yl.get("visits"), fmt="int",
            spark=mser["visits"], period=P),
        kpi("Конверсия в заказ", safe_div(cur.get("orders"), yc.get("visits")),
            safe_div(prev.get("orders"), yp.get("visits")), safe_div(ly.get("orders"), yl.get("visits")),
            fmt="pct", period=P, hint="Заказы 1С на визит Метрики"),
        kpi("Расход Директа", dc.get("cost"), dp.get("cost"), dl.get("cost"), better="down", period=P),
        kpi("ДРР", safe_div(dc.get("cost"), cur.get("net")), safe_div(dp.get("cost"), prev.get("net")),
            safe_div(dl.get("cost"), ly.get("net")), fmt="pct", better="down", period=P,
            hint="Расход Директа к чистой выручке ИМ"),
        kpi("Стоимость заказа", safe_div(dc.get("cost"), cur.get("orders")),
            safe_div(dp.get("cost"), prev.get("orders")), safe_div(dl.get("cost"), ly.get("orders")),
            better="down", period=P, hint="Расход Директа на заказ ИМ"),
        kpi("Отказы", yc.get("bounce_rate"), yp.get("bounce_rate"), yl.get("bounce_rate"), fmt="pct",
            better="down", period=P),
    ]))

    nc, np_, nl = net["cur"], net["prev"], net["ly"]
    bc, bp, bl = buyers["cur"], buyers["prev"], buyers["ly"]
    w.append(kpis("Вся сеть · Mindbox", [
        kpi("Выручка сети", nc.get("total"), np_.get("total"), nl.get("total"), period=P,
            hint="Все каналы по Mindbox, позиции без отмен и возвратов"),
        kpi("Розничные магазины", nc.get("stores"), np_.get("stores"), nl.get("stores"), period=P),
        kpi("Онлайн kixbox.ru", nc.get("online"), np_.get("online"), nl.get("online"), period=P),
        kpi("Доля розницы", nc.get("retail_share"), np_.get("retail_share"), nl.get("retail_share"),
            fmt="pct", better="none", period=P),
        kpi("Покупатели", bc.get("buyers"), bp.get("buyers"), bl.get("buyers"), fmt="int", period=P,
            hint="Идентифицированные клиенты с покупкой в любом канале"),
        kpi("Новые покупатели", bc.get("new_buyers"), bp.get("new_buyers"), bl.get("new_buyers"),
            fmt="int", period=P, hint="Первая покупка в истории Mindbox пришлась на период"),
    ]))

    w.append(chart(
        f"Чистая выручка {bucket_caption(P)}", x,
        [series("Период", s["net"], color=0), series("Год назад", s_ly["net"], style="line", color=1)],
        subtitle="ИМ, ₽ · возвраты вычитаются в день проведения", kind="combo"))
    w.append(chart(
        f"Отгрузки и возвраты {bucket_caption(P)}", x,
        [series("Отгрузки", s["sales"], color=0), series("Возвраты", s["returns"], color=4)],
        subtitle="ИМ, ₽"))

    stores = await _store_split(ctx)
    if stores:
        w.append(share("Выручка сети по каналам", stores,
                       subtitle="Mindbox, текущий период"))
    return w


async def _store_split(ctx: Ctx) -> list[tuple[str, float]]:
    from config import POINTS_OF_CONTACT
    sql = f"""
WITH {common.mb_orders_cte(ctx, ('cur',))}
SELECT poc, sum(amt) AS amt FROM op GROUP BY poc ORDER BY amt DESC"""
    rows = await ctx.q(sql)
    agg: dict[str, float] = {}
    for r in rows:
        name = POINTS_OF_CONTACT.get(r.get("poc") or "", ("Прочее", "other"))[0]
        if POINTS_OF_CONTACT.get(r.get("poc") or "", ("", "other"))[1] == "other_online":
            name = "Другие сайты"
        agg[name] = agg.get(name, 0) + num(r["amt"])
    return sorted(agg.items(), key=lambda t: -t[1])
