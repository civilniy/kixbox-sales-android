"""Клиент ClickHouse поверх HTTP и помощники для SQL.

Все значения в SQL подставляются только из серверных пресетов (даты, фиксированные
справочники), пользовательский ввод в запросы не попадает. Строковые литералы всё равно
экранируются через lit().
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Protocol

import httpx

from config import SETTINGS

log = logging.getLogger("sales.ch")

_NUMERIC = re.compile(r"^(Nullable\()?(LowCardinality\()?(U?Int\d+|Float\d+|Decimal)")


class QueryError(RuntimeError):
    pass


class Client(Protocol):
    async def query(self, sql: str) -> list[dict[str, Any]]: ...


def _coerce(rows: list[dict], meta: list[dict]) -> list[dict]:
    numeric = {m["name"] for m in meta if _NUMERIC.match(m["type"])}
    arrays_num = {m["name"] for m in meta
                  if m["type"].startswith("Array(") and _NUMERIC.match(m["type"][6:])}
    for r in rows:
        for k in numeric:
            v = r.get(k)
            if isinstance(v, str):
                try:
                    r[k] = float(v) if any(c in v for c in ".eE") else int(v)
                except ValueError:
                    r[k] = None
        for k in arrays_num:
            v = r.get(k)
            if isinstance(v, list):
                r[k] = [float(x) if isinstance(x, str) else x for x in v]
    return rows


def parse_json_result(raw: str | bytes) -> list[dict]:
    data = json.loads(raw)
    return _coerce(data.get("data", []), data.get("meta", []))


class HttpClient:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(SETTINGS.max_parallel_queries)
        self._http = httpx.AsyncClient(timeout=SETTINGS.query_timeout_s)

    async def query(self, sql: str) -> list[dict[str, Any]]:
        async with self._sem:
            started = datetime.now()
            resp = await self._http.post(
                SETTINGS.clickhouse_url,
                content=(sql + "\nFORMAT JSON").encode(),
                headers={
                    "X-ClickHouse-User": SETTINGS.clickhouse_user,
                    "X-ClickHouse-Key": SETTINGS.clickhouse_password,
                },
            )
            elapsed = (datetime.now() - started).total_seconds()
            if resp.status_code != 200:
                log.error("query failed in %.1fs: %s\n%s", elapsed, resp.text[:500], sql)
                raise QueryError(resp.text[:300])
            if elapsed > 5:
                log.warning("slow query %.1fs: %s", elapsed, sql[:200].replace("\n", " "))
            return parse_json_result(resp.content)

    async def close(self) -> None:
        await self._http.aclose()


# ---------- литералы ----------

def lit(v: Any) -> str:
    if isinstance(v, datetime):
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(v, date):
        return "'" + v.isoformat() + "'"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + s + "'"


def lits(values: Iterable[Any]) -> str:
    return "(" + ", ".join(lit(v) for v in values) + ")"


def utc_bounds(start: date, end: date) -> tuple[str, str]:
    """Границы московских суток в UTC для полей Mindbox (…Utc)."""
    a = datetime.combine(start, datetime.min.time()) - timedelta(hours=3)
    b = datetime.combine(end + timedelta(days=1), datetime.min.time()) - timedelta(hours=3)
    return lit(a), lit(b)


def dt_bounds(start: date, end: date) -> tuple[str, str]:
    a = datetime.combine(start, datetime.min.time())
    b = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return lit(a), lit(b)


def num(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None
