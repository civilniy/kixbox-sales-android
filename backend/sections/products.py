"""Товары и бренды: лидеры, движение к прошлому периоду, возвраты, размеры, категории."""
from __future__ import annotations

from ch import num
from context import (C1_ROWS, CATEGORY_EXPR, IS_GOODS, IS_RET, Ctx)
from widgets import (chart, col, fmt_money_short, insight, insights, rel_delta, safe_div, series,
                     share, table)

ID = "products"
TITLE = "Товары"
ICON = "tag"


def _agg(ctx: Ctx, key: str, extra: str = "", having: str = "cur_sales > 0 OR prev_net != 0",
         limit: int = 200, order: str = "cur_net DESC") -> str:
    cur = ctx.cur_filter("doc_date", "datetime")
    return f"""
SELECT {key} AS k {extra},
    sumIf(amount, {IS_GOODS} AND {cur}) AS cur_sales,
    sumIf(amount, {IS_RET} AND {cur}) AS cur_ret,
    sumIf(amount, {IS_GOODS} AND {cur}) - sumIf(amount, {IS_RET} AND {cur}) AS cur_net,
    sumIf(qty, {IS_GOODS} AND {cur}) AS cur_units,
    sumIf(qty, {IS_RET} AND {cur}) AS cur_units_ret,
    sumIf(price * qty, {IS_GOODS} AND {cur}) AS cur_full,
    sumIf(amount, {IS_GOODS} AND NOT {cur}) - sumIf(amount, {IS_RET} AND NOT {cur}) AS prev_net,
    sumIf(qty, {IS_GOODS} AND NOT {cur}) AS prev_units
FROM kixbox.c1_items
WHERE row_type IN ('Товар', 'Возврат') AND {ctx.wfilter('doc_date', 'datetime', ('cur', 'prev'))}
GROUP BY k
HAVING {having}
ORDER BY {order}
LIMIT {limit}"""


async def by_brand(ctx: Ctx):
    return await ctx.q(_agg(ctx, "if(brand = '', 'Без бренда', brand)"))


async def by_category(ctx: Ctx):
    return await ctx.q(_agg(ctx, CATEGORY_EXPR))


async def by_ptype(ctx: Ctx):
    return await ctx.q(_agg(ctx, "if(ptype = '', 'Не указан', ptype)", limit=60))


async def by_product(ctx: Ctx):
    return await ctx.q(_agg(ctx, "article", extra=", any(product) AS name, any(brand) AS brand",
                            having="cur_sales > 0", limit=60))


async def by_product_units(ctx: Ctx):
    return await ctx.q(_agg(ctx, "article", extra=", any(product) AS name, any(brand) AS brand",
                            having="cur_units > 0", order="cur_units DESC", limit=30))


async def returns_leaders(ctx: Ctx):
    return await ctx.q(_agg(ctx, "article", extra=", any(product) AS name, any(brand) AS brand",
                            having="cur_units >= 3 AND cur_units_ret > 0",
                            order="cur_units_ret / cur_units DESC, cur_units_ret DESC", limit=30))


async def sizes(ctx: Ctx):
    sql = f"""
SELECT upperUTF8(trimBoth(splitByChar(',', variant)[1])) AS size,
    {CATEGORY_EXPR} AS cat,
    sumIf(qty, {IS_GOODS}) AS units, sumIf(qty, {IS_RET}) AS units_ret
FROM kixbox.c1_items
WHERE row_type IN ('Товар', 'Возврат') AND {ctx.cur_filter('doc_date', 'datetime')}
GROUP BY size, cat
HAVING units > 0"""
    return await ctx.q(sql)


async def new_vs_old(ctx: Ctx):
    """Новинки: артикулы, которых не было в отгрузках до начала периода."""
    sql = f"""
WITH firsts AS (
    SELECT article, min(doc_date) AS first_sale
    FROM kixbox.c1_items WHERE {IS_GOODS} AND article != ''
    GROUP BY article
)
SELECT if(toDate(f.first_sale) >= {ctx_start(ctx)}, 'Новые артикулы', 'Продавались раньше') AS kind,
    sum(i.amount) AS sales, sum(i.qty) AS units, uniqExact(i.article) AS articles,
    sum(i.price * i.qty) AS full
FROM kixbox.c1_items AS i INNER JOIN firsts AS f ON f.article = i.article
WHERE {IS_GOODS.replace('row_type', 'i.row_type').replace('warehouse', 'i.warehouse').replace('site', 'i.site')}
  AND {ctx.cur_filter('i.doc_date', 'datetime')}
GROUP BY kind"""
    return await ctx.q(sql)


def ctx_start(ctx: Ctx) -> str:
    return f"'{ctx.cur.start.isoformat()}'"


def _rows(items: list[dict], total_net: float, with_units: bool = True):
    out = []
    for r in items:
        disc = (1 - num(r["cur_sales"]) / num(r["cur_full"])) if num(r.get("cur_full")) else None
        ret = safe_div(r["cur_ret"], r["cur_sales"])
        row = [r["k"], r["cur_net"], safe_div(r["cur_net"], total_net),
               rel_delta(r["cur_net"], r["prev_net"])]
        if with_units:
            row.append(r["cur_units"])
        row += [disc, ret]
        out.append(row)
    return out


async def build(ctx: Ctx) -> list[dict]:
    brands, cats, ptypes, prods, prods_u, rets, sz, nvo = await ctx.gather(
        by_brand(ctx), by_category(ctx), by_ptype(ctx), by_product(ctx), by_product_units(ctx),
        returns_leaders(ctx), sizes(ctx), new_vs_old(ctx))
    total_net = sum(num(r["cur_net"]) for r in brands) or 1
    w: list[dict] = []

    # выводы
    ins = []
    if brands:
        top = sorted(brands, key=lambda r: -num(r["cur_net"]))
        top3 = sum(num(r["cur_net"]) for r in top[:3])
        ins.append(insight("info", f"Топ-3 бренда дают {top3 / total_net * 100:.0f}% чистой выручки: "
                           + ", ".join(r["k"] for r in top[:3]) + "."))
        moves = sorted(brands, key=lambda r: num(r["cur_net"]) - num(r["prev_net"]))
        gain = [r for r in moves[::-1][:3] if num(r["cur_net"]) - num(r["prev_net"]) > 0]
        loss = [r for r in moves[:3] if num(r["cur_net"]) - num(r["prev_net"]) < 0]
        if gain:
            ins.append(insight("good", "Больше всего прибавили: " + ", ".join(
                f"{r['k']} +{fmt_money_short(num(r['cur_net']) - num(r['prev_net']))}" for r in gain) + "."))
        if loss:
            ins.append(insight("bad", "Больше всего потеряли: " + ", ".join(
                f"{r['k']} −{fmt_money_short(num(r['prev_net']) - num(r['cur_net']))}" for r in loss) + "."))
        new_brands = [r["k"] for r in brands if num(r["prev_units"]) == 0 and num(r["cur_units"]) > 0]
        if new_brands:
            ins.append(insight("info", f"Продажи без истории в прошлом периоде: {', '.join(new_brands[:6])}."))
    if nvo:
        by = {r["kind"]: r for r in nvo}
        n = by.get("Новые артикулы")
        tot = sum(num(r["sales"]) for r in nvo) or 1
        if n:
            ins.append(insight("info", f"Новые артикулы периода: {int(num(n['articles']))} шт., "
                                       f"{num(n['sales']) / tot * 100:.0f}% отгрузок."))
    if ins:
        w.append(insights("Ассортимент в цифрах", ins))

    cols = [col("Бренд"), col("Чистая", "money"), col("Доля", "pct", bar=True),
            col("Динамика", "pct", delta=True, better="up"), col("Штук", "int"),
            col("Скидка", "pct"), col("% возвр.", "pct", better="down")]
    w.append(table("Бренды", cols, _rows(brands, total_net), collapsed=15,
                   subtitle="Чистая выручка = отгрузки минус возвраты периода"))

    movers = sorted(brands, key=lambda r: -(num(r["cur_net"]) - num(r["prev_net"])))
    mv = [r for r in movers if num(r["cur_net"]) - num(r["prev_net"]) != 0]
    top_moves = mv[:8] + [r for r in mv[-8:] if r not in mv[:8]]
    if top_moves:
        w.append(chart("Кто двигает выручку", [r["k"][:14] for r in top_moves], [
            series("Изменение, ₽", [num(r["cur_net"]) - num(r["prev_net"]) for r in top_moves], color=0),
        ], subtitle=f"Прирост и падение чистой выручки брендов {ctx.period.prev_name}"))

    w.append(table("Категории", [c if i else col("Категория") for i, c in enumerate(cols)],
                   _rows(cats, total_net), collapsed=10))
    w.append(table("Типы товаров", [c if i else col("Тип") for i, c in enumerate(cols)],
                   _rows(ptypes, total_net), collapsed=12))

    prod_cols = [col("Товар", width=2.2), col("Бренд"), col("Чистая", "money"), col("Штук", "int"),
                 col("Цена", "money"), col("Скидка", "pct"), col("Динамика", "pct", delta=True)]

    def prow(r):
        name = str(r.get("name") or r["k"])
        brand = str(r.get("brand") or "")
        short = name.replace(str(r["k"]), "").strip()
        return [short or name, brand, r["cur_net"], r["cur_units"], safe_div(r["cur_sales"], r["cur_units"]),
                (1 - num(r["cur_sales"]) / num(r["cur_full"])) if num(r.get("cur_full")) else None,
                rel_delta(r["cur_net"], r["prev_net"])]

    w.append(table("Топ товаров по выручке", prod_cols, [prow(r) for r in prods], collapsed=15,
                   subtitle="Артикул, все цвета и размеры"))
    w.append(table("Топ товаров по штукам", prod_cols, [prow(r) for r in prods_u], collapsed=10))
    if rets:
        w.append(table("Чаще всего возвращают", [
            col("Товар", width=2.2), col("Бренд"), col("Продано", "int"), col("Возвращено", "int"),
            col("% возвр.", "pct", better="down"), col("Возвраты", "money")],
            [[str(r.get("name") or r["k"]).replace(str(r["k"]), "").strip(), r.get("brand"), r["cur_units"],
              r["cur_units_ret"], safe_div(r["cur_units_ret"], r["cur_units"]), r["cur_ret"]] for r in rets],
            subtitle="Минимум 3 продажи за период; возвраты по дате возврата", collapsed=10))

    # размеры одежды
    apparel_order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL", "XXXL"]
    app = {}
    for r in sz:
        if r["cat"] in ("Верх", "Худи и трикотаж", "Верхняя одежда", "Низ") and r["size"] in apparel_order:
            key = "XXL" if r["size"] == "2XL" else ("XXXL" if r["size"] == "3XL" else r["size"])
            a = app.setdefault(key, [0.0, 0.0])
            a[0] += num(r["units"])
            a[1] += num(r["units_ret"])
    labels = [s for s in apparel_order if s in app]
    if labels:
        w.append(chart("Размеры одежды", labels, [
            series("Продано, шт", [app[s][0] for s in labels], fmt="int", color=0),
            series("% возвратов", [safe_div(app[s][1], app[s][0]) for s in labels], fmt="pct",
                   style="line", axis="right", color=4),
        ], subtitle="Буквенные размеры: одежда без обуви и аксессуаров", kind="combo"))
    shoes = {}
    for r in sz:
        if r["cat"] == "Обувь":
            try:
                v = float(r["size"].replace(",", ".").split()[0])
            except (ValueError, IndexError):
                continue
            if 34 <= v <= 48:
                shoes[v] = shoes.get(v, 0.0) + num(r["units"])
    if shoes:
        keys = sorted(shoes)
        w.append(chart("Размеры обуви", [f"{k:g}" for k in keys],
                       [series("Продано, шт", [shoes[k] for k in keys], fmt="int", color=0)]))
    if nvo:
        w.append(share("Новые и продававшиеся артикулы", [(r["kind"], r["sales"]) for r in nvo],
                       subtitle="Новые — первая отгрузка в истории пришлась на период"))
    return w
