"""KIXBOX Pulse API — закрытый сервис аналитики для Android-приложения."""
from __future__ import annotations

import asyncio
import hmac
import logging
import time
import traceback
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from ch import Client, HttpClient, to_date
from config import SETTINGS
from context import Ctx
from periods import PRESETS, PRESET_KEYS, resolve
from sections import BY_ID, SECTIONS

log = logging.getLogger("sales")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
MSK = ZoneInfo("Europe/Moscow")
API_VERSION = 1


class Service:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.cache: dict[tuple, tuple[float, dict]] = {}
        self.locks: dict[tuple, asyncio.Lock] = {}
        self.fresh: tuple[float, dict] | None = None

    # ----- свежесть данных -----
    async def freshness(self, force: bool = False) -> dict:
        if not force and self.fresh and time.time() - self.fresh[0] < 600:
            return self.fresh[1]
        q = self.client.query
        today = datetime.now(MSK).date()
        since = today - timedelta(days=60)
        checks = {
            "c1": f"""SELECT max(toDate(doc_date)) AS last,
                      maxIf(toDate(doc_date), toHour(doc_date) >= 19) AS full
                      FROM kixbox.c1_items WHERE doc_date >= '{since}' AND row_type = 'Товар'""",
            "metrika": f"SELECT max(date) AS last FROM kixbox.ya_metrika WHERE date >= '{since}'",
            "visits": f"SELECT max(date) AS last FROM kixbox.ym_visits WHERE date >= '{since}'",
            "direct": f"SELECT max(date) AS last FROM kixbox.ya_direct WHERE date >= '{since}'",
            "mindbox": f"""SELECT toDate(max(firstDateTimeUtc) + INTERVAL 3 HOUR) AS last
                           FROM kixbox.mb_ProcessingOrders_Orders WHERE firstDateTimeUtc >= '{since}'""",
            "mailings": f"""SELECT toDate(max(dateTimeUtc) + INTERVAL 3 HOUR) AS last
                            FROM kixbox.mb_Mailings_CustomerMessagesStatuses WHERE dateTimeUtc >= '{since}'""",
            "delivery": f"SELECT max(createdate) AS last FROM kixbox.deliveries WHERE createdate >= '{since}'",
            "stock": "SELECT toDate(max(_loaded_at)) AS last FROM kixbox.in_variants",
            "competitors": f"SELECT max(window_date) - 1 AS last FROM brandshop.flows WHERE window_date >= '{since}'",
        }
        names = {"c1": "1С", "metrika": "Метрика", "visits": "Визиты", "direct": "Директ", "mindbox": "Mindbox",
                 "mailings": "Рассылки", "delivery": "Доставка", "stock": "Остатки", "competitors": "Конкуренты"}
        results = await asyncio.gather(*(q(sql) for sql in checks.values()), return_exceptions=True)
        out: dict[str, Any] = {"sources": []}
        c1_end = None
        for key, res in zip(checks, results):
            last = None
            if not isinstance(res, Exception) and res:
                last = to_date(res[0].get("last"))
                if key == "c1":
                    full = to_date(res[0].get("full"))
                    if last:
                        c1_end = last if full == last else last - timedelta(days=1)
            out["sources"].append({"id": key, "name": names[key],
                                   "last": last.isoformat() if last and last.year > 2000 else None,
                                   "ok": not isinstance(res, Exception)})
        yesterday = today - timedelta(days=1)
        end = min(yesterday, c1_end) if c1_end else yesterday
        out["end"] = end.isoformat()
        out["c1_complete"] = c1_end.isoformat() if c1_end else None
        out["checked_at"] = datetime.now(MSK).isoformat(timespec="seconds")
        self.fresh = (time.time(), out)
        return out

    # ----- разделы -----
    async def section(self, sid: str, preset: str, force: bool = False) -> dict:
        fresh = await self.freshness()
        end = date.fromisoformat(fresh["end"])
        key = (sid, preset, end)
        cached = self.cache.get(key)
        if cached and not force and time.time() - cached[0] < SETTINGS.cache_minutes * 60:
            return cached[1]
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.cache.get(key)
            if cached and not force and time.time() - cached[0] < SETTINGS.cache_minutes * 60:
                return cached[1]
            payload = await self._build(sid, preset, end, fresh)
            if not payload.get("error"):
                self.cache[key] = (time.time(), payload)
            return payload

    async def _build(self, sid: str, preset: str, end: date, fresh: dict) -> dict:
        mod = BY_ID[sid]
        period = resolve(preset, end)
        ctx = Ctx(period=period, client=self.client, end=end, freshness=fresh)
        started = time.time()
        error = None
        try:
            widgets = await mod.build(ctx)
        except Exception as e:  # noqa: BLE001
            log.error("section %s/%s failed: %s\n%s", sid, preset, e, traceback.format_exc())
            error = str(e)[:300]
            widgets = [{"type": "note", "title": "Раздел не собрался",
                        "text": "Сервер не смог выполнить запросы к ClickHouse. Подробности в журнале сервиса."}]
        took = time.time() - started
        log.info("section %s/%s built in %.1fs", sid, preset, took)
        return {
            "id": sid, "title": mod.TITLE, "period": period.as_json(), "widgets": widgets,
            "generated_at": datetime.now(MSK).isoformat(timespec="seconds"),
            "data_end": end.isoformat(), "build_seconds": round(took, 1), "error": error,
            "api_version": API_VERSION,
        }

    async def warmup_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                await self.freshness(force=True)
                for preset in ("mtd", "7d"):
                    for s in SECTIONS:
                        await self.section(s.ID, preset, force=True)
            except Exception as e:  # noqa: BLE001
                log.warning("warmup failed: %s", e)
            await asyncio.sleep(max(SETTINGS.cache_minutes - 2, 5) * 60)


service: Service | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    client = HttpClient()
    service = Service(client)
    task = asyncio.create_task(service.warmup_loop()) if SETTINGS.warmup else None
    yield
    if task:
        task.cancel()
    await client.close()


app = FastAPI(title="KIXBOX Pulse API", version="1.0", lifespan=lifespan, docs_url=None, redoc_url=None)


def auth(authorization: str = Header(default="")) -> None:
    token = SETTINGS.api_token
    if not token:
        raise HTTPException(503, "SALES_API_TOKEN не задан на сервере")
    got = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(got, token):
        raise HTTPException(401, "Неверный токен")


@app.get("/api/v1/health")
async def health() -> dict:
    return {"ok": True, "version": API_VERSION}


@app.get("/api/v1/meta", dependencies=[Depends(auth)])
async def meta(refresh: bool = False) -> dict:
    assert service
    fresh = await service.freshness(force=refresh)
    return {
        "sections": [{"id": s.ID, "title": s.TITLE, "icon": s.ICON} for s in SECTIONS],
        "periods": [{"id": k, "title": t} for k, t in PRESETS],
        "freshness": fresh,
        "api_version": API_VERSION,
    }


@app.get("/api/v1/section/{sid}", dependencies=[Depends(auth)])
async def section(sid: str, period: str = Query("mtd"), refresh: bool = False) -> dict:
    assert service
    if sid not in BY_ID:
        raise HTTPException(404, "Нет такого раздела")
    if period not in PRESET_KEYS:
        raise HTTPException(400, "Неизвестный период")
    return await service.section(sid, period, force=refresh)
