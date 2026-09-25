"""Конкуренты: оценка продаж Brandshop, NUW, Studio Slow и Leform по срезам остатков."""
from __future__ import annotations

from datetime import timedelta

from ch import lit, num
from context import IS_GOODS, IS_RET, Ctx
from widgets import (bucket_caption, chart, col, fill_buckets, fmt_money_short, insight, insights, kpi,
                     kpis, note, rel_delta, safe_div, series, share, table)

ID = "competitors"
TITLE = "Конкуренты"
ICON = "radar"

# Продажи дня D лежат в окне window_date = D + 1
SHOPS = [
    ("Brandshop", "brandshop", "f.amount", "f.amount_regular", "product_name", "product_name"),
    ("NUW", "nuwstore", "f.price * f.qty", "f.regular_price * f.qty", "model", "toString(product_id)"),
    ("Studio Slow", "studioslow", "f.price * f.qty", "f.regular_price * f.qty", "model", "toString(product_id)"),
    ("Leform", "leform", "f.price * f.qty", "f.regular_price * f.qty", "model", "toString(product_id)"),
]


def _union(ctx: Ctx, select: str, flows: str = "'sale'", keys=("cur", "prev")) -> str:
    parts = []
    for name, db, amt, reg, pname, pid in SHOPS:
        sel = (select.replace("{amt}", amt).replace("{reg}", reg).replace("{name}", pname)
               .replace("{id}", pid).replace("{shop}", lit(name)))
        parts.append(f"""SELECT {sel}
FROM {db}.flows AS f FINAL
WHERE flow IN ({flows}) AND {ctx.wfilter('window_date - 1', 'date', keys)}
  AND NOT ({pname} ILIKE '%сертификат%')""")
    return "\nUNION ALL\n".join(parts)


async def totals(ctx: Ctx) -> list[dict]:
    sel = """{shop} AS shop, flow, {w} AS w, sum(f.qty) AS qty, sum({amt}) AS amt, sum({reg}) AS reg,
    min(window_date) - 1 AS first_day, max(window_date) - 1 AS last_day"""
    sel = sel.replace("{w}", ctx.wexpr("window_date - 1", ("cur", "prev")))
    sql = _union(ctx, sel, "'sale', 'delivery', 'return', 'new_size'")
    sql = "\nUNION ALL\n".join(p + "\nGROUP BY shop, flow, w" for p in sql.split("\nUNION ALL\n"))
    return await ctx.q(sql)


async def daily(ctx: Ctx) -> list[dict]:
    sel = "{shop} AS shop, " + ctx.bexpr("window_date - 1") + " AS b, sum({amt}) AS amt"
    sql = _union(ctx, sel, keys=("cur",))
    sql = "\nUNION ALL\n".join(p + "\nGROUP BY shop, b" for p in sql.split("\nUNION ALL\n"))
    return await ctx.q(sql)


async def brands(ctx: Ctx) -> list[dict]:
    sel = "{shop} AS shop, upperUTF8(brand) AS brand, sum(f.qty) AS qty, sum({amt}) AS amt, sum({reg}) AS reg"
    sql = _union(ctx, sel, keys=("cur",))
    sql = "\nUNION ALL\n".join(p + "\nGROUP BY shop, brand" for p in sql.split("\nUNION ALL\n"))
    return await ctx.q(sql)


async def models(ctx: Ctx) -> list[dict]:
    sel = ("{shop} AS shop, {id} AS product_id, any({name}) AS name, any(brand) AS brand, any(category) AS cat, "
           "sum(f.qty) AS qty, sum({amt}) AS amt, sum({reg}) AS reg")
    sql = _union(ctx, sel, keys=("cur",))
    sql = "\nUNION ALL\n".join(p + "\nGROUP BY shop, product_id" for p in sql.split("\nUNION ALL\n"))
    sql = f"SELECT * FROM ({sql}) ORDER BY amt DESC LIMIT 40"
    return await ctx.q(sql)


async def kix_brands(ctx: Ctx) -> list[dict]:
    cur = ctx.cur_filter("doc_date", "datetime")
    sql = f"""
SELECT upperUTF8(brand) AS brand,
    sumIf(amount, {IS_GOODS}) AS sales, sumIf(qty, {IS_GOODS}) AS qty
FROM kixbox.c1_items
WHERE row_type = 'Товар' AND {cur}
GROUP BY brand"""
    return await ctx.q(sql)


async def build(ctx: Ctx) -> list[dict]:
    P = ctx.period
    tot, dly, br, mdl, kb = await ctx.gather(totals(ctx), daily(ctx), brands(ctx), models(ctx), kix_brands(ctx))
    shops: dict[str, dict] = {}
    for r in tot:
        s = shops.setdefault(r["shop"], {"cur": {}, "prev": {}, "first": None, "last": None})
        d = s[r["w"]].setdefault(r["flow"], {"qty": 0, "amt": 0, "reg": 0})
        d["qty"] += num(r["qty"]); d["amt"] += num(r["amt"]); d["reg"] += num(r["reg"])
        if r["w"] == "cur":
            s["first"] = min(filter(None, [s["first"], str(r["first_day"])[:10]]))
            s["last"] = max(filter(None, [s["last"], str(r["last_day"])[:10]]))

    items = []
    ins = []
    for name, *_ in SHOPS:
        s = shops.get(name)
        if not s or not s["cur"].get("sale"):
            continue
        sc, sp = s["cur"]["sale"], s["prev"].get("sale", {})
        items.append(kpi(f"{name} · продажи", sc["amt"], sp.get("amt") if sp.get("amt") else None,
                         hint=f"Данные с {s['first']} по {s['last']}"))
        full = safe_div(sc["amt"], sc["reg"])
        items.append(kpi(f"{name} · штук", sc["qty"], sp.get("qty") if sp.get("qty") else None, fmt="int"))
        if full is not None:
            ins.append(insight("info", f"{name}: {fmt_money_short(sc['amt'])}, средняя цена "
                                       f"{fmt_money_short(safe_div(sc['amt'], sc['qty']) or 0)}, скидка "
                                       f"{(1 - full) * 100:.0f}% от полной цены."))
    if items:
        w: list[dict] = [kpis("Оценка продаж по срезам остатков", items)]
    else:
        w = []
    if ins:
        w.append(insights("Конкуренты", ins))

    x, _ = fill_buckets(P, [], "b", [])
    ser = []
    for i, (name, *_rest) in enumerate(SHOPS):
        pts = [r for r in dly if r["shop"] == name]
        if pts:
            _, v = fill_buckets(P, pts, "b", ["amt"])
            ser.append(series(name, v["amt"], color=i))
    if ser:
        w.append(chart(f"Продажи конкурентов {bucket_caption(P)}", x, ser, subtitle="Оценка, ₽ по текущей цене"))

    # поставки и возвраты
    flow_rows = []
    for name, *_ in SHOPS:
        s = shops.get(name)
        if not s:
            continue
        c = s["cur"]
        flow_rows.append([name, c.get("sale", {}).get("qty"), c.get("return", {}).get("qty"),
                          safe_div(c.get("return", {}).get("qty"), c.get("sale", {}).get("qty")),
                          c.get("delivery", {}).get("qty"), c.get("new_size", {}).get("qty"),
                          c.get("delivery", {}).get("amt")])
    if flow_rows:
        w.append(table("Движение стока", [
            col("Магазин"), col("Продано", "int"), col("Возвраты", "int"), col("% возвр.", "pct"),
            col("Поставки, шт", "int"), col("Новые размеры", "int"), col("Поставки, ₽", "money"),
        ], flow_rows, sortable=False, subtitle="Потоки между соседними срезами остатков"))

    kix = {r["brand"]: r for r in kb}
    comp: dict[str, dict] = {}
    for r in br:
        c = comp.setdefault(r["brand"], {"amt": 0, "qty": 0, "reg": 0, "by": {}})
        c["amt"] += num(r["amt"]); c["qty"] += num(r["qty"]); c["reg"] += num(r["reg"])
        c["by"][r["shop"]] = num(r["amt"])
    top = sorted(comp.items(), key=lambda t: -t[1]["amt"])[:40]
    w.append(table("Бренды: конкуренты и Kixbox", [
        col("Бренд"), col("Конкуренты", "money"), col("Brandshop", "money"), col("Другие", "money"),
        col("Скидка у них", "pct"), col("Kixbox отгрузки", "money"), col("Доля Kixbox", "pct", bar=True),
    ], [[b, c["amt"], c["by"].get("Brandshop", 0), c["amt"] - c["by"].get("Brandshop", 0),
         (1 - c["amt"] / c["reg"]) if c["reg"] else None, num(kix.get(b, {}).get("sales")),
         safe_div(num(kix.get(b, {}).get("sales")), c["amt"] + num(kix.get(b, {}).get("sales")))]
        for b, c in top], collapsed=15,
        subtitle="Доля Kixbox — отгрузки ИМ к сумме с продажами конкурентов по бренду"))

    overlap = [(b, c) for b, c in top if kix.get(b)]
    if overlap:
        miss = [b for b, c in top[:15] if not kix.get(b) or num(kix[b].get("sales")) == 0]
        if miss:
            w.insert(2 if len(w) > 1 else len(w),
                     insights("Чего нет у нас", [insight("info", "Крупные бренды конкурентов без продаж Kixbox "
                                                                 "в периоде: " + ", ".join(miss[:8]) + ".")]))

    if mdl:
        w.append(table("Самые продаваемые модели", [
            col("Модель", width=2.2), col("Магазин"), col("Бренд"), col("Штук", "int"), col("Сумма", "money"),
            col("Скидка", "pct"),
        ], [[r["name"], r["shop"], r["brand"], r["qty"], r["amt"],
             (1 - num(r["amt"]) / num(r["reg"])) if num(r["reg"]) else None] for r in mdl], collapsed=15))
    w.append(note("Продажа — уменьшение остатка размера между соседними срезами сайта конкурента, "
                  "по цене на начало окна. Продажи дня D приходят в окне следующего дня. Подарочные "
                  "сертификаты исключены. Это оценка: резерв и перемещения тоже уменьшают остаток.",
                  title="Методика"))
    return w
