"""Периоды отчёта: текущий, предыдущий и год назад, плюс шаг графиков."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

PRESETS: list[tuple[str, str]] = [
    ("yesterday", "День"),
    ("7d", "7 дней"),
    ("30d", "30 дней"),
    ("mtd", "Месяц"),
    ("last_month", "Прошлый месяц"),
    ("qtd", "Квартал"),
    ("90d", "90 дней"),
    ("ytd", "Год"),
]
PRESET_KEYS = [k for k, _ in PRESETS]

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
              "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


@dataclass(frozen=True)
class Window:
    key: str
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def label(self) -> str:
        return range_label(self.start, self.end)


@dataclass
class Period:
    preset: str
    title: str
    cur: Window
    prev: Window
    ly: Window
    bucket: str  # day | week | month
    prev_is_ly: bool = False
    prev_name: str = "к пред. периоду"
    windows: list[Window] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.windows = [self.cur, self.prev, self.ly]

    def as_json(self) -> dict:
        return {
            "preset": self.preset,
            "title": self.title,
            "label": self.cur.label(),
            "from": self.cur.start.isoformat(),
            "to": self.cur.end.isoformat(),
            "prev_label": self.prev.label(),
            "ly_label": self.ly.label(),
            "prev_name": self.prev_name,
            "bucket": self.bucket,
            "days": self.cur.days,
        }


def range_label(a: date, b: date) -> str:
    if a == b:
        return f"{a.day} {MONTHS_GEN[a.month - 1]} {a.year}"
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {MONTHS_GEN[a.month - 1]} {a.year}"
    if a.year == b.year:
        return f"{a.day} {MONTHS_GEN[a.month - 1]} – {b.day} {MONTHS_GEN[b.month - 1]} {b.year}"
    return f"{a.strftime('%d.%m.%Y')} – {b.strftime('%d.%m.%Y')}"


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def minus_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 февраля
        return d.replace(year=d.year - 1, day=28)


def shift(w: Window, days: int, key: str) -> Window:
    return Window(key, w.start - timedelta(days=days), w.end - timedelta(days=days))


def bucket_for(days: int) -> str:
    if days <= 45:
        return "day"
    if days <= 200:
        return "week"
    return "month"


def resolve(preset: str, end: date) -> Period:
    """end — последний завершённый день данных (включительно)."""
    if preset not in PRESET_KEYS:
        raise ValueError(f"unknown period {preset}")
    title = dict(PRESETS)[preset]
    prev_name = "к пред. периоду"
    prev_is_ly = False

    if preset == "yesterday":
        cur = Window("cur", end, end)
        prev = shift(cur, 7, "prev")
        ly = shift(cur, 364, "ly")
        prev_name = "к тому же дню недели"
    elif preset in ("7d", "30d", "90d"):
        n = {"7d": 7, "30d": 30, "90d": 90}[preset]
        cur = Window("cur", end - timedelta(days=n - 1), end)
        prev = shift(cur, n, "prev")
        ly = shift(cur, 364, "ly")
    elif preset == "mtd":
        start = month_start(end)
        cur = Window("cur", start, end)
        p_start = add_months(start, -1)
        p_end = min(p_start + timedelta(days=end.day - 1), month_end(p_start))
        prev = Window("prev", p_start, p_end)
        ly = Window("ly", minus_year(start), minus_year(end))
        prev_name = "к тем же дням прошлого месяца"
        title = MONTHS_NOM[end.month - 1]
    elif preset == "last_month":
        start = add_months(month_start(end), -1)
        cur = Window("cur", start, month_end(start))
        p_start = add_months(start, -1)
        prev = Window("prev", p_start, month_end(p_start))
        ly = Window("ly", minus_year(start), month_end(minus_year(start)))
        title = MONTHS_NOM[start.month - 1]
        prev_name = "к предыдущему месяцу"
    elif preset == "qtd":
        q_start = date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
        cur = Window("cur", q_start, end)
        p_start = add_months(q_start, -3)
        p_end = min(p_start + (end - q_start), add_months(q_start, 0) - timedelta(days=1))
        prev = Window("prev", p_start, p_end)
        ly = Window("ly", minus_year(q_start), minus_year(end))
        title = f"{(end.month - 1) // 3 + 1} квартал"
        prev_name = "к тем же дням прошлого квартала"
    else:  # ytd
        start = date(end.year, 1, 1)
        cur = Window("cur", start, end)
        ly = Window("ly", minus_year(start), minus_year(end))
        prev = Window("prev", ly.start, ly.end)
        prev_is_ly = True
        title = f"{end.year} год"
        prev_name = "к прошлому году"

    return Period(preset=preset, title=title, cur=cur, prev=prev, ly=ly,
                  bucket=bucket_for(cur.days), prev_is_ly=prev_is_ly, prev_name=prev_name)


def bucket_keys(w: Window, bucket: str) -> list[date]:
    """Все ключи шага в окне — чтобы графики не теряли пустые дни."""
    keys: list[date] = []
    d = w.start
    if bucket == "day":
        while d <= w.end:
            keys.append(d)
            d += timedelta(days=1)
    elif bucket == "week":
        d = w.start - timedelta(days=w.start.weekday())
        while d <= w.end:
            keys.append(d)
            d += timedelta(days=7)
    else:
        d = month_start(w.start)
        while d <= w.end:
            keys.append(d)
            d = add_months(d, 1)
    return keys


def bucket_label(d: date, bucket: str) -> str:
    if bucket == "day":
        return d.strftime("%d.%m")
    if bucket == "week":
        return d.strftime("%d.%m")
    return MONTHS_NOM[d.month - 1][:3] + (f" {str(d.year)[2:]}" if d.month == 1 else "")
