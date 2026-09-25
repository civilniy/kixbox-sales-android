"""Локальная копия схемы ClickHouse на chdb с синтетическими данными.

Нужна, чтобы проверить каждый SQL-запрос тем же движком (ClickHouse 26.x), что и на сервере,
без доступа к боевой базе. Значения случайные, структура и типы — как в kixbox.
"""
from __future__ import annotations

import json
import tempfile

from ch import parse_json_result

DDL = r"""
CREATE DATABASE IF NOT EXISTS kixbox;
CREATE DATABASE IF NOT EXISTS brandshop;
CREATE DATABASE IF NOT EXISTS nuwstore;
CREATE DATABASE IF NOT EXISTS studioslow;
CREATE DATABASE IF NOT EXISTS leform;

CREATE TABLE kixbox.c1_items (
    row_type String, doc_number String, doc_date DateTime, org String, warehouse String, deal String,
    order_number String, site String, status String, delivery String, payment String, pickup String,
    address String, responsible String, counterparty String, phone String, email String, comment String,
    site_id String, barcode String, article String, product String, brand String, season String,
    gender String, ptype String, variant String, qty Decimal(15, 3), price Decimal(15, 2),
    discount_pct Decimal(6, 2), amount Decimal(15, 2), _loaded_at DateTime
) ENGINE = MergeTree ORDER BY (doc_date, row_type, doc_number);

CREATE TABLE kixbox.plan_fact (
    month Date, site String, date Date, day_num UInt8, net_day Nullable(Int64), sales_day Nullable(Int64),
    returns_day Nullable(Int64), net_cum Nullable(Int64), net_cum_ly Int64, plan_low_cum Int64,
    plan_high_cum Nullable(Int64), single_plan UInt8, forecast_cum Nullable(Int64), mtd_sales Int64,
    mtd_returns Int64, mtd_net Int64, mtd_returns_pct Float64, forecast_month Int64, rate_7d Int64,
    need_per_day_low Int64, days_left Int64, plan_low Int64, plan_high Int64
) ENGINE = MergeTree ORDER BY date;

CREATE TABLE kixbox.ya_metrika (
    date Date, counter_id UInt32, site String, source String, medium String, campaign String,
    traffic_source String, visits UInt32, users UInt32, bounces UInt32, page_depth Decimal(8, 2),
    purchases UInt32, revenue Decimal(15, 2), _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY (date, counter_id, source, medium, campaign, traffic_source);

CREATE TABLE kixbox.ya_direct (
    date Date, client_login String, campaign_id String, campaign_name String, impressions UInt64,
    clicks UInt64, cost Decimal(15, 2), conversions UInt32, _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY (date, client_login, campaign_id);

CREATE TABLE kixbox.ym_visits (
    date Date, date_time DateTime, visit_id UInt64, client_id String, traffic_source String,
    device_category String, region_city String, start_url String, is_new_user UInt8, visit_duration UInt32,
    page_views UInt32, bounce UInt8, goals_id String, purchase_id String, utm_source String,
    utm_campaign String, _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY (date, visit_id);

CREATE TABLE kixbox.mb_ProcessingOrders_Orders (
    id String, unmergedCustomerId Nullable(Int64), firstBrandInternalId Nullable(String),
    pointOfContactInternalId Nullable(String), firstDateTimeUtc Nullable(DateTime64(3)),
    priceWithDiscounts Nullable(Decimal(25, 5)), _isDeleted Nullable(Bool), _rowversion_ts DateTime64(3)
) ENGINE = ReplacingMergeTree(_rowversion_ts) ORDER BY id;

CREATE TABLE kixbox.mb_ProcessingOrders_Purchases (
    orderId String, pricePerItem Nullable(Decimal(25, 5)), priceOfLine Nullable(Decimal(25, 5)),
    quantity Nullable(Decimal(25, 5)), lineId String, statusInternalId Nullable(String),
    productInternalId Nullable(String), _rowversion_ts DateTime64(3)
) ENGINE = ReplacingMergeTree(_rowversion_ts) ORDER BY (orderId, lineId);

CREATE TABLE kixbox.mb_customers (
    mindbox_id String, email String, email_invalid UInt8, phone String, phone_invalid UInt8,
    birth_date String, sex String, custom_fields String, _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY mindbox_id;

CREATE TABLE kixbox.mb_ProcessingOrders_BonusPointChanges_v3 (
    id String, kindSystemName Nullable(String), changeAmount Nullable(Decimal(25, 5)),
    dateTimeUtc Nullable(DateTime64(3)), unmergedCustomerId Nullable(Int64), _isDeleted Nullable(Bool),
    _rowversion_ts DateTime64(3)
) ENGINE = ReplacingMergeTree(_rowversion_ts) ORDER BY id;

CREATE TABLE kixbox.mb_Mailings_CustomerMessagesStatuses (
    messageId Int64, mailingStatusSystemName Nullable(String), dateTimeUtc Nullable(DateTime64(3)),
    unmergedCustomerId Nullable(Int64), mailingInternalId Nullable(String), _isDeleted Nullable(Bool)
) ENGINE = MergeTree ORDER BY messageId;

CREATE TABLE kixbox.mb_Mailings_Mailings (
    id String, name Nullable(String), type Nullable(String), channel Nullable(String), _rowversion_ts DateTime64(3)
) ENGINE = ReplacingMergeTree(_rowversion_ts) ORDER BY id;

CREATE TABLE kixbox.deliveries (
    carrier String, orderno String, createdate Date, town String, paytype String,
    delivery_price Decimal(15, 2), items_total Decimal(15, 2), receipt_summ Decimal(15, 2), status String,
    status_title String, delivered_date Nullable(Date), cod Decimal(15, 2), items_count UInt16
) ENGINE = MergeTree ORDER BY createdate;

CREATE TABLE kixbox.in_products (
    id UInt64, brand String, tip String, tip2 String, tip3 String, is_hidden UInt8, archived UInt8,
    created_at DateTime, sezon String, gender String, _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY id;

CREATE TABLE kixbox.in_variants (
    id UInt64, product_id UInt64, barcode String, size String, price Decimal(15, 2), w3 Int32,
    quantity Int32, _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY id;

CREATE TABLE brandshop.flows (
    flow LowCardinality(String), window_date Date, variant_key String, product_id String,
    product_name String, brand LowCardinality(String), category String, qty Int32,
    price_current Decimal(12, 2), price_regular Decimal(12, 2), amount Decimal(14, 2),
    amount_regular Decimal(14, 2), _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY (flow, window_date, variant_key);
"""

OTHER_FLOWS = """
CREATE TABLE {db}.flows (
    window_date Date, window_hours Float32, variant_key String, product_id String, article String,
    brand String, category String, model String, flow String, qty Int32, price Decimal(12, 2),
    regular_price Decimal(12, 2), _loaded_at DateTime
) ENGINE = ReplacingMergeTree(_loaded_at) ORDER BY (flow, window_date, variant_key);
"""

DATA = r"""
INSERT INTO kixbox.c1_items
SELECT
    ['Заказ', 'Товар', 'Товар', 'Возврат', 'Услуга'][n % 5 + 1] AS row_type,
    concat('KB', toString(70000 + intDiv(n, 3))) AS doc_number,
    toDateTime('2025-01-01 00:00:00') + (n * 7919) % (630 * 86400) AS doc_date,
    if(n % 17 = 0, 'ООО "КРИМ"', 'ООО "Спейс Джем"') AS org,
    if(n % 5 = 0, '', ['400 Склад интернет магазина Киксбокс', '401 Склад Самовывоз ИМ', '206 Склад выездных акций'][n % 3 + 1]),
    '', concat('KB', toString(70000 + intDiv(n, 3))),
    if(n % 17 = 0, 'Hike', 'Копия kixbox'),
    ['[F] Выполнен', '[CN] Отменён', '[DW] В пути', '[FB] Возврат', '1/0/1'][n % 5 + 1],
    ['Dalli', 'Самовывоз', 'CDEK', 'Яндекс Доставка'][n % 4 + 1],
    ['Оплата при получении', 'Картой на сайте', 'Yandex split'][n % 3 + 1],
    '', ['г Москва, ул Тверская, д 1', 'г Санкт-Петербург, пр Невский, 5', 'Казань г, ул Баумана', ''][n % 4 + 1],
    '', '', '', '', '', '',
    concat('27000', toString(n % 400)), concat('ART', toString(n % 250)),
    concat('ART', toString(n % 250), ' Футболка тест'),
    ['CARHARTT WIP', 'OBEY', 'FRED PERRY', 'C.P. COMPANY', ''][n % 5 + 1],
    ['AW-26', 'SS-26', 'AW-25', ''][n % 4 + 1], ['Муж', 'Жен', 'Унисекс'][n % 3 + 1],
    ['Футболка кор. рукав', 'Джинсы (Loose fit)', 'Кроссовки низкие из кожи', 'Кепка', 'Куртка', 'Толстовка с капюшоном'][n % 6 + 1],
    [ 'S, BLACK', 'M, WHITE', 'XL, NAVY', '42, BLACK', 'ONE SIZE, RED'][n % 5 + 1],
    toDecimal64(1 + n % 2, 3), toDecimal64(9990, 2), toDecimal64(30, 2),
    toDecimal64(4990 + (n % 7) * 1000, 2), now()
FROM (SELECT number AS n FROM numbers(40000));

INSERT INTO kixbox.plan_fact
SELECT toDate('2026-09-01'), 'Kixbox', toDate('2026-09-01') + number, number + 1,
    if(number < 23, 500000, NULL), if(number < 23, 600000, NULL), if(number < 23, 100000, NULL),
    if(number < 23, 500000 * (number + 1), NULL), 400000 * (number + 1), 566667 * (number + 1), NULL, 1,
    if(number >= 22, 500000 * (number + 1), NULL), 13000000, 4000000, 9000000, 30.5, 14000000, 400000,
    600000, 7, 17000000, 17000000
FROM numbers(30);

INSERT INTO kixbox.ya_metrika
SELECT toDate('2025-01-01') + number % 630, 44759623, 'kixbox.ru', '', '', '',
    ['Ad traffic', 'Search engine traffic', 'Direct traffic'][number % 3 + 1],
    1000 + number % 300, 800, 300, 3.5, 10, 100000, now()
FROM numbers(1890);

INSERT INTO kixbox.ya_direct
SELECT toDate('2025-01-01') + number % 630, 'Kixbox-cnx', toString(707116994 + number % 6),
    ['Товарная Kixbox', 'Мастер Кампаний Октябрь', 'Поиск Бренд', 'Смарт РСЯ', 'МК Carhartt', 'Retarget'][number % 6 + 1],
    10000, 300, toDecimal64(9000 + number % 100, 2), 10, now()
FROM numbers(3780);

INSERT INTO kixbox.ym_visits
SELECT toDate('2025-01-01') + number % 630, toDateTime('2025-01-01 10:00:00') + number * 1000, number,
    toString(number % 5000), ['ad', 'organic', 'direct', 'email', 'social'][number % 5 + 1],
    toString(number % 3 + 1), ['Moscow', 'Saint Petersburg', ''][number % 3 + 1],
    ['https://kixbox.ru/', 'https://kixbox.ru/product/x?variant_id=1', 'https://kixbox.ru/collection/new'][number % 3 + 1],
    number % 2, 120, 4, number % 4 = 0,
    if(number % 10 = 0, '[194384785,495725731]', '[]'),
    if(number % 50 = 0, concat('[''', toString(70000 + number % 13000), ''']'), '[]'),
    if(number % 5 = 0, 'yandex', ''), if(number % 5 = 0, 'Y_Kixbox_Tovarnaya|707116994', ''), now()
FROM numbers(60000);

INSERT INTO kixbox.mb_ProcessingOrders_Orders
SELECT toString(generateUUIDv4(number)), if(number % 7 = 0, NULL, number % 9000),
    'KixBox', ['15', '77922', '35357', '62311c1d-fc3f-4f3d-8576-5dc81abb20f0', '6f9a9089-3ba4-4955-8697-87dbb2c25aa9', NULL][number % 6 + 1],
    toDateTime64('2024-06-01 00:00:00', 3) + (number * 3137) % (840 * 86400), NULL, NULL, now64(3)
FROM numbers(30000);

INSERT INTO kixbox.mb_ProcessingOrders_Purchases
SELECT o.id, 5000, 4990 + cityHash64(o.id) % 5000, 1 + cityHash64(o.id) % 2, '1',
    ['36', '36', '36', '40'][cityHash64(o.id) % 4 + 1], '1', now64(3)
FROM kixbox.mb_ProcessingOrders_Orders AS o;

INSERT INTO kixbox.mb_customers
SELECT toString(number), 'a@b.ru', 0, '79990000000', 0, if(number % 3 = 0, '', '1990-05-01'),
    ['female', 'male', ''][number % 3 + 1],
    concat('{"bPRProcentskidki": "', ['3', '5', '7', '10', ''][number % 5 + 1], '"}'), now()
FROM numbers(9000);

INSERT INTO kixbox.mb_ProcessingOrders_BonusPointChanges_v3
SELECT toString(number), ['RetailOrderBonus', 'RetailOrderPayment', 'Custom', 'Expired'][number % 4 + 1],
    if(number % 4 IN (1, 3), -100, 150), toDateTime64('2025-01-01 00:00:00', 3) + number * 3000, number % 9000,
    false, now64(3)
FROM numbers(20000);

INSERT INTO kixbox.mb_Mailings_Mailings VALUES
    ('m1', 'Двойные баллы', 'trigger', 'Email', now64(3)), ('m2', 'Распродажа', 'bulk', 'Email', now64(3)),
    ('m3', 'SMS акция', 'bulk', 'Sms', now64(3));

INSERT INTO kixbox.mb_Mailings_CustomerMessagesStatuses
SELECT number, ['Sent', 'Sent', 'Opened', 'Clicked', 'Unsubscribe', 'NotDelivered', 'InQueue'][number % 7 + 1],
    toDateTime64('2025-01-01 00:00:00', 3) + number * 300, number % 9000, ['m1', 'm2', 'm3'][number % 3 + 1], false
FROM numbers(200000);

INSERT INTO kixbox.deliveries
SELECT ['Dalli', 'Алгоритм'][number % 2 + 1], toString(number), toDate('2025-01-01') + number % 630,
    ['Москва город', 'Санкт-Петербург город', 'Казань'][number % 3 + 1], ['NO', 'CARD', 'CASH'][number % 3 + 1],
    450, 10000, if(number % 3 = 0, 0, 6000),
    ['COMPLETE', 'PARTLYRETURNED', 'RETURNED', 'ACCEPTED', 'CANCELED'][number % 5 + 1], 'Доставлен',
    if(number % 5 IN (0, 1), toDate('2025-01-01') + number % 630 + 3, NULL), 0, 1
FROM numbers(8000);

INSERT INTO kixbox.in_products
SELECT number, ['Carhartt WIP', 'OBEY', 'FRED PERRY'][number % 3 + 1],
    ['Футболка кор. рукав', 'Кроссовки низкие', 'Кепка'][number % 3 + 1], 'Прочее', 'Одежда',
    number % 10 = 0, 0, toDateTime('2025-01-01 00:00:00') + number * 20000, 'AW-26', 'Муж', now()
FROM numbers(1500);

INSERT INTO kixbox.in_variants
SELECT number, number % 1500, concat('27000', toString(number % 400)), ['S', 'M', 'L'][number % 3 + 1],
    7990, number % 4, number % 4, now()
FROM numbers(4500);
"""

BS_DATA = """
INSERT INTO brandshop.flows
SELECT ['sale', 'sale', 'delivery', 'return', 'new_size'][number % 5 + 1], toDate('2026-09-01') + number % 25,
    toString(number), toString(number % 300), 'Куртка тест', ['Stone Island', 'Nike', 'Carhartt WIP'][number % 3 + 1],
    'Куртки', 1, 20000, 25000, 20000, 25000, now()
FROM numbers(3000);
"""

OTHER_DATA = """
INSERT INTO {db}.flows
SELECT toDate('2026-09-22') + number % 3, 24, toString(number), toString(number % 50), 'A1',
    ['Puma', 'Premiata'][number % 2 + 1], 'Обувь', 'Кроссовки тест', ['sale', 'delivery'][number % 2 + 1], 1,
    15000, 18000, now()
FROM numbers(200);
"""


_SHARED: "ChdbClient | None" = None


class ChdbClient:
    """В процессе может быть только одна сессия chdb, поэтому клиент общий."""

    def __new__(cls):
        global _SHARED
        if _SHARED is None:
            _SHARED = super().__new__(cls)
            _SHARED._init()
        return _SHARED

    def _init(self) -> None:
        from chdb import session
        self._dir = tempfile.mkdtemp(prefix="kix_chdb_")
        self.s = session.Session(self._dir)
        self.queries: list[str] = []
        for stmt in _split(DDL):
            self.s.query(stmt)
        for db in ("nuwstore", "studioslow", "leform"):
            self.s.query(OTHER_FLOWS.format(db=db))
        for stmt in _split(DATA + BS_DATA):
            self.s.query(stmt)
        for db in ("nuwstore", "studioslow", "leform"):
            self.s.query(OTHER_DATA.format(db=db))

    async def query(self, sql: str):
        self.queries.append(sql)
        res = self.s.query(sql, "JSON")
        raw = res.bytes() if hasattr(res, "bytes") else bytes(str(res), "utf-8")
        if not raw.strip():
            return []
        return parse_json_result(raw)


def _split(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";\n") if s.strip()]


if __name__ == "__main__":
    import asyncio
    c = ChdbClient()
    print(json.dumps(asyncio.run(c.query("SELECT count() AS n FROM kixbox.c1_items"))))
