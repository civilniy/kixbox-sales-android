"""Конструкторы виджетов. Приложение рисует разделы по этому описанию,
поэтому новые метрики добавляются на сервере без пересборки APK.

Форматы значений: money, int, pct (доля 0..1), dec1, dec2, days, sec, text.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Sequence

from ch import num
from periods import Period, bucket_keys, bucket_label

PCT_FORMATS = {"pct"}


def rel_delta(cur: Any, base: Any) -> float | None:
    c, b = num(cur, None), num(base, None)  # type: ignore[arg-type]
    if c is None or b is None or b == 0:
        return None
    return (c - b) / abs(b)


def delta(cur: Any, base: Any, fmt: str) -> float | None:
    if fmt in PCT_FORMATS:
        c, b = num(cur, None), num(base, None)  # type: ignore[arg-type]
        if c is None or b is None:
            return None
        return c - b
    return rel_delta(cur, base)


def safe_div(a: Any, b: Any) -> float | None:
    a, b = num(a, None), num(b, None)  # type: ignore[assignment]
    if a is None or not b:
        return None
    return a / b


def kpi(label: str, cur: Any, prev: Any = None, ly: Any = None, fmt: str = "money",
        better: str = "up", hint: str | None = None, spark: Sequence[float] | None = None,
        period: Period | None = None) -> dict:
    item = {
        "label": label,
        "value": cur,
        "format": fmt,
        "delta": delta(cur, prev, fmt) if prev is not None else None,
        "delta_ly": delta(cur, ly, fmt) if ly is not None else None,
        "delta_kind": "pp" if fmt in PCT_FORMATS else "rel",
        "better": better,
    }
    if period is not None and period.prev_is_ly:
        item["delta_ly"] = None
    if hint:
        item["hint"] = hint
    if spark:
        item["spark"] = [round(num(x), 2) for x in spark]
    return item


def kpis(title: str | None, items: list[dict], subtitle: str | None = None,
         columns: int = 2) -> dict:
    return {"type": "kpis", "title": title, "subtitle": subtitle, "items": items,
            "columns": columns}


def hero(title: str, value: Any, fmt: str = "money", subtitle: str | None = None,
         progress: float | None = None, items: list[dict] | None = None,
         badge: dict | None = None, marker: float | None = None) -> dict:
    return {"type": "hero", "title": title, "value": value, "format": fmt,
            "subtitle": subtitle, "progress": progress, "marker": marker,
            "items": items or [], "badge": badge}


def series(name: str, values: Sequence[Any], fmt: str = "money", style: str = "bar",
           axis: str = "left", color: int | None = None) -> dict:
    s = {"name": name, "values": [None if v is None else round(num(v), 2) for v in values],
         "format": fmt, "style": style, "axis": axis}
    if color is not None:
        s["color"] = color
    return s


def chart(title: str, x: list[str], series_list: list[dict], subtitle: str | None = None,
          kind: str = "bar", stacked: bool = False, note: str | None = None) -> dict:
    return {"type": "chart", "title": title, "subtitle": subtitle, "kind": kind,
            "stacked": stacked, "x": x, "series": series_list, "note": note}


def col(title: str, fmt: str = "text", *, bar: bool = False, better: str | None = None,
        delta: bool = False, align: str | None = None, width: float | None = None) -> dict:
    c: dict[str, Any] = {"title": title, "format": fmt}
    if bar:
        c["bar"] = True
    if better:
        c["better"] = better
    if delta:
        c["delta"] = True
    c["align"] = align or ("start" if fmt == "text" else "end")
    if width:
        c["width"] = width
    return c


def table(title: str, columns: list[dict], rows: list[list[Any]], subtitle: str | None = None,
          collapsed: int = 10, sortable: bool = True, note: str | None = None,
          total: list[Any] | None = None) -> dict:
    return {"type": "table", "title": title, "subtitle": subtitle, "columns": columns,
            "rows": rows, "collapsed": collapsed, "sortable": sortable, "note": note,
            "total": total}


def share(title: str, items: list[tuple[str, Any]], fmt: str = "money",
          subtitle: str | None = None) -> dict:
    total = sum(num(v) for _, v in items)
    return {"type": "share", "title": title, "subtitle": subtitle, "format": fmt,
            "total": total,
            "items": [{"label": l, "value": v, "share": (num(v) / total) if total else 0}
                      for l, v in items if num(v) > 0]}


def heatmap(title: str, x: list[str], y: list[str], values: list[list[Any]],
            fmt: str = "int", subtitle: str | None = None, note: str | None = None) -> dict:
    return {"type": "heatmap", "title": title, "subtitle": subtitle, "x": x, "y": y,
            "values": values, "format": fmt, "note": note}


def funnel(title: str, steps: list[tuple[str, Any]], subtitle: str | None = None,
           note: str | None = None) -> dict:
    return {"type": "funnel", "title": title, "subtitle": subtitle, "note": note,
            "steps": [{"label": l, "value": v} for l, v in steps]}


def insights(title: str, items: list[dict]) -> dict:
    return {"type": "insights", "title": title, "items": items}


def insight(tone: str, text: str) -> dict:
    return {"tone": tone, "text": text}


def note(text: str, title: str | None = None) -> dict:
    return {"type": "note", "title": title, "text": text}


def header(title: str, subtitle: str | None = None) -> dict:
    return {"type": "header", "title": title, "subtitle": subtitle}


# ---------- ряды по шагам периода ----------

def fill_buckets(period: Period, rows: Iterable[dict], key: str,
                 fields: Sequence[str]) -> tuple[list[str], dict[str, list[float]]]:
    keys = bucket_keys(period.cur, period.bucket)
    idx = {k: i for i, k in enumerate(keys)}
    out = {f: [0.0] * len(keys) for f in fields}
    for r in rows:
        d = r.get(key)
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        if d in idx:
            for f in fields:
                out[f][idx[d]] += num(r.get(f))
    return [bucket_label(k, period.bucket) for k in keys], out


def bucket_caption(period: Period) -> str:
    return {"day": "по дням", "week": "по неделям", "month": "по месяцам"}[period.bucket]


def pct(a: Any, b: Any) -> float | None:
    return safe_div(a, b)


def fmt_money_short(v: float) -> str:
    v = num(v)
    a = abs(v)
    if a >= 1e6:
        s = f"{v / 1e6:.1f}".replace(".", ",") + " млн ₽"
    elif a >= 1e3:
        s = f"{v / 1e3:.0f} тыс ₽"
    else:
        s = f"{v:.0f} ₽"
    return s


def fmt_pct(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "—"
    x = v * 100
    digits = 2 if 0 < abs(x) < 1 else 1
    s = f"{x:+.{digits}f}" if signed else f"{x:.{digits}f}"
    return s.replace(".", ",").replace("-", "−") + "%"


def fmt_pp(v: float | None) -> str:
    if v is None:
        return "—"
    x = v * 100
    s = f"{x:+.2f}" if abs(x) < 0.1 else f"{x:+.1f}"
    return s.replace(".", ",").replace("-", "−") + " п.п."
