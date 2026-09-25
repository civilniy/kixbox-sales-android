"""Склад и ассортимент сайта: остатки InSales, оборачиваемость, неликвид, размерные сетки."""
from __future__ import annotations

from datetime import timedelta

from ch import lit, num
from context import CATEGORY_EXPR, IS_GOODS, Ctx
from widgets import (col, chart, insight, insights, kpi, kpis, note, safe_div, series, share, table)

ID = "stock"
TITLE = "Склад"
ICON = "box"

VISIBLE = """product_id IN (SELECT id FROM kixbox.in_products FINAL WHERE is_hidden = 0 AND archived = 0)"""


def _stock_cte() -> str:
    return f"""
v AS (
    SELECT id, product_id, barcode, size, price, w3 AS qty
    FROM kixbox.in_variants FINAL
    WHERE {VISIBLE}
),
pr AS (
    SELECT id, upperUTF8(brand) AS brand, tip AS ptype, created_at
    FROM kixbox.in_products FINAL WHERE is_hidden = 0 AND archived = 0
)"""


def _sales30_cte(ctx: Ctx, days: int = 30) -> str:
    a = ctx.end - timedelta(days=days - 1)
    return f"""
s AS (
    SELECT barcode, sum(qty) AS sold, sum(amount) AS sold_amt
    FROM kixbox.c1_items
    WHERE {IS_GOODS} AND {ctx.range_filter('doc_date', a, ctx.end, 'datetime')}
    GROUP BY barcode
)"""


async def totals(ctx: Ctx) -> dict:
    sql = f"""
WITH {_stock_cte()}, {_sales30_cte(ctx)},
per_product AS (
    SELECT product_id, count() AS sizes, countIf(qty > 0) AS sizes_in, sum(qty) AS units
    FROM v GROUP BY product_id HAVING units > 0
)
SELECT
    (SELECT countIf(qty > 0) FROM v) AS skus,
    (SELECT sumIf(qty, qty > 0) FROM v) AS units,
    (SELECT sumIf(price * qty, qty > 0) FROM v) AS value,
    (SELECT count() FROM per_product) AS products,
    (SELECT countIf(sizes_in = sizes) FROM per_product) AS full_grid,
    (SELECT countIf(sizes_in / sizes < 0.5) FROM per_product) AS broken_grid,
    (SELECT sum(sold) FROM s) AS sold30,
    (SELECT sum(sold_amt) FROM s) AS sold30_amt,
    (SELECT sumIf(v.qty, v.qty > 0 AND s.sold = 0) FROM v LEFT JOIN s ON s.barcode = v.barcode) AS idle_units
"""
    rows = await ctx.q(sql)
    return rows[0] if rows else {}


async def by_brand(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {_stock_cte()}, {_sales30_cte(ctx)},
st AS (
    SELECT pr.brand AS brand, sum(v.qty) AS units, sum(v.price * v.qty) AS value,
        uniqExact(v.product_id) AS products
    FROM v INNER JOIN pr ON pr.id = v.product_id
    WHERE v.qty > 0 GROUP BY brand
),
sb AS (
    SELECT upperUTF8(brand) AS brand, sum(qty) AS sold, sum(amount) AS sold_amt
    FROM kixbox.c1_items
    WHERE {IS_GOODS} AND {ctx.range_filter('doc_date', ctx.end - timedelta(days=29), ctx.end, 'datetime')}
    GROUP BY brand
)
SELECT st.brand AS brand, st.units AS units, st.value AS value, st.products AS products,
    sb.sold AS sold, sb.sold_amt AS sold_amt
FROM st LEFT JOIN sb ON sb.brand = st.brand
ORDER BY value DESC LIMIT 80"""
    return await ctx.q(sql)


async def by_category(ctx: Ctx) -> list[dict]:
    cat_stock = CATEGORY_EXPR.replace("ptype", "pr.ptype")
    sql = f"""
WITH {_stock_cte()}, {_sales30_cte(ctx)}
SELECT {cat_stock} AS cat, sum(v.qty) AS units, sum(v.price * v.qty) AS value,
    uniqExact(v.product_id) AS products, sum(s.sold) AS sold
FROM v INNER JOIN pr ON pr.id = v.product_id LEFT JOIN s ON s.barcode = v.barcode
WHERE v.qty > 0
GROUP BY cat ORDER BY value DESC"""
    return await ctx.q(sql)


async def idle(ctx: Ctx) -> list[dict]:
    """Неликвид: остаток есть, продаж за 90 дней нет, карточке больше 90 дней."""
    a = ctx.end - timedelta(days=89)
    sql = f"""
WITH {_stock_cte()},
s90 AS (
    SELECT DISTINCT barcode FROM kixbox.c1_items
    WHERE {IS_GOODS} AND {ctx.range_filter('doc_date', a, ctx.end, 'datetime')}
)
SELECT pr.brand AS brand, sum(v.qty) AS units, sum(v.price * v.qty) AS value, uniqExact(v.product_id) AS products
FROM v INNER JOIN pr ON pr.id = v.product_id
WHERE v.qty > 0 AND v.barcode NOT IN (SELECT barcode FROM s90)
  AND pr.created_at < {lit(a)}
GROUP BY brand ORDER BY value DESC LIMIT 40"""
    return await ctx.q(sql)


async def grids(ctx: Ctx) -> list[dict]:
    sql = f"""
WITH {_stock_cte()}
SELECT multiIf(r = 1, 'Все размеры', r >= 0.75, '75–99%', r >= 0.5, '50–74%', r >= 0.25, '25–49%',
               'меньше 25%') AS band, count() AS products, sum(units) AS units, min(r) AS o
FROM (SELECT product_id, countIf(qty > 0) / count() AS r, sum(qty) AS units FROM v GROUP BY product_id
      HAVING units > 0)
GROUP BY band ORDER BY o DESC"""
    return await ctx.q(sql)


async def arrivals(ctx: Ctx) -> list[dict]:
    """Новые карточки на сайте по неделям создания за последние 16 недель и их остатки."""
    a = ctx.end - timedelta(days=7 * 16)
    sql = f"""
WITH {_stock_cte()}
SELECT toMonday(toDate(pr.created_at)) AS wk, uniqExact(pr.id) AS products, sum(v.qty) AS units_now
FROM pr LEFT JOIN v ON v.product_id = pr.id
WHERE pr.created_at >= {lit(a)} AND pr.created_at <= {lit(ctx.end + timedelta(days=1))}
GROUP BY wk ORDER BY wk"""
    return await ctx.q(sql)


async def build(ctx: Ctx) -> list[dict]:
    tot, br, cat, idl, gr, arr = await ctx.gather(totals(ctx), by_brand(ctx), by_category(ctx), idle(ctx),
                                                  grids(ctx), arrivals(ctx))
    units = num(tot.get("units"))
    daily = num(tot.get("sold30")) / 30
    idle_value = sum(num(r["value"]) for r in idl)
    idle_units = sum(num(r["units"]) for r in idl)
    w: list[dict] = [kpis("Остатки сайта сейчас", [
        kpi("Штук на складе", units, fmt="int"),
        kpi("Стоимость в ценах сайта", tot.get("value"), hint="Текущая цена продажи × остаток"),
        kpi("Карточек в наличии", tot.get("products"), fmt="int"),
        kpi("SKU в наличии", tot.get("skus"), fmt="int", hint="Размеро-цвета с остатком"),
        kpi("Продано за 30 дней", tot.get("sold30"), fmt="int"),
        kpi("Запас в днях", safe_div(units, daily), fmt="int", better="down",
            hint="Остаток при текущем темпе продаж ИМ за 30 дней"),
        kpi("Оборот за 30 дней", safe_div(tot.get("sold30"), units + num(tot.get("sold30"))), fmt="pct",
            hint="Продано / (продано + остаток)"),
        kpi("Полная размерная сетка", safe_div(tot.get("full_grid"), tot.get("products")), fmt="pct",
            hint="Доля карточек, где есть все размеры"),
        kpi("Разбитые сетки", safe_div(tot.get("broken_grid"), tot.get("products")), fmt="pct", better="down",
            hint="Меньше половины размеров в наличии"),
        kpi("Неликвид 90 дней", idle_value, better="down",
            hint=f"{int(idle_units)} шт без продаж 90 дней в карточках старше 90 дней"),
    ])]

    ins = []
    if daily:
        ins.append(insight("info", f"Текущего стока хватит на {units / daily:.0f} дней продаж интернет-магазина."))
    if idle_value and num(tot.get("value")):
        ins.append(insight("warn", f"{idle_value / num(tot['value']) * 100:.0f}% стоимости стока не продавалось "
                                   f"90 дней — кандидаты на уценку или перемещение в розницу."))
    over = [r for r in br if num(r["units"]) >= 50 and safe_div(r["units"], num(r["sold"]) / 30) is not None
            and num(r["units"]) / (num(r["sold"]) / 30) > 365]
    if over:
        ins.append(insight("warn", "Запас больше года: " + ", ".join(r["brand"] for r in over[:5]) + "."))
    hot = [r for r in br if num(r["sold"]) >= 10 and num(r["units"]) / (num(r["sold"]) / 30) < 30]
    if hot:
        ins.append(insight("good", "Быстро распродаются, запас меньше месяца: " +
                           ", ".join(r["brand"] for r in hot[:5]) + "."))
    if ins:
        w.append(insights("Сток", ins))

    total_value = num(tot.get("value")) or 1
    w.append(table("Бренды на складе", [
        col("Бренд"), col("Штук", "int"), col("Стоимость", "money"), col("Доля", "pct", bar=True),
        col("Продано 30 дн", "int"), col("Запас, дн", "int", better="down"), col("Оборот", "pct"),
    ], [[r["brand"], r["units"], r["value"], num(r["value"]) / total_value, r["sold"],
         safe_div(r["units"], num(r["sold"]) / 30) if num(r["sold"]) else None,
         safe_div(r["sold"], num(r["units"]) + num(r["sold"]))] for r in br], collapsed=15,
        subtitle="Остатки InSales, продажи ИМ по 1С за 30 дней"))
    if cat:
        w.append(table("Категории на складе", [
            col("Категория"), col("Штук", "int"), col("Стоимость", "money"), col("Доля", "pct", bar=True),
            col("Продано 30 дн", "int"), col("Запас, дн", "int", better="down"),
        ], [[r["cat"], r["units"], r["value"], num(r["value"]) / total_value, r["sold"],
             safe_div(r["units"], num(r["sold"]) / 30) if num(r["sold"]) else None] for r in cat]))
    if gr:
        w.append(share("Полнота размерной сетки", [(r["band"], r["products"]) for r in gr], fmt="int",
                       subtitle="Карточки в наличии по доле доступных размеров"))
    if idl:
        w.append(table("Неликвид по брендам", [
            col("Бренд"), col("Штук", "int"), col("Стоимость", "money"), col("Карточек", "int"),
        ], [[r["brand"], r["units"], r["value"], r["products"]] for r in idl], collapsed=10,
            subtitle="Нет продаж ИМ 90 дней, карточка создана раньше"))
    if arr:
        w.append(chart("Новые карточки на сайте", [str(r["wk"])[8:10] + "." + str(r["wk"])[5:7] for r in arr], [
            series("Карточек", [r["products"] for r in arr], fmt="int", color=0),
            series("Остаток сейчас, шт", [r["units_now"] for r in arr], fmt="int", style="line", axis="right",
                   color=2),
        ], kind="combo", subtitle="По неделе создания карточки, 16 недель"))
    w.append(note("Остатки — склад w3 InSales на последнюю загрузку, только видимые карточки. Раздел "
                  "показывает текущее состояние и не зависит от выбранного периода, кроме темпа продаж.",
                  title="Методика"))
    return w
