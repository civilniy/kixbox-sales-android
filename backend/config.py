"""Настройки сервиса и справочники, общие для всех разделов."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    clickhouse_url: str = os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123")
    clickhouse_user: str = os.getenv("CLICKHOUSE_USER", "sales_app")
    clickhouse_password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    api_token: str = os.getenv("SALES_API_TOKEN", "")
    cache_minutes: int = int(os.getenv("CACHE_MINUTES", "30"))
    max_parallel_queries: int = int(os.getenv("MAX_PARALLEL_QUERIES", "2"))
    query_timeout_s: int = int(os.getenv("QUERY_TIMEOUT_S", "90"))
    warmup: bool = os.getenv("WARMUP", "1") == "1"
    direct_login: str = os.getenv("DIRECT_LOGIN", "Kixbox-cnx")
    metrika_site: str = os.getenv("METRIKA_SITE", "kixbox.ru")


SETTINGS = Settings()

# Точки контакта Mindbox → (название, тип канала)
POINTS_OF_CONTACT: dict[str, tuple[str, str]] = {
    "15": ("kixbox.ru", "online"),
    "62311c1d-fc3f-4f3d-8576-5dc81abb20f0": ("Цветной", "store"),
    "77922": ("Авиапарк", "store"),
    "35357": ("Атриум", "store"),
    "77631": ("Метрополис", "store"),
    "78290": ("СПб", "store"),
    "2470645b-8962-471b-b484-348feba95c1c": ("Садовая", "store"),
    "e8571087-277d-4783-8a06-d1732e60f860": ("Октябрь", "store"),
    "b2bd16cf-d552-45d4-a399-b182e3cbc395": ("oktyabrskateshop", "other_online"),
    "6f9a9089-3ba4-4955-8697-87dbb2c25aa9": ("Hike", "other_online"),
    "887b9710-9231-457a-a2dd-f67b76cd9abe": ("Яндекс.Кит", "other_online"),
    "23503": ("Сайт ПЛ", "other_online"),
}
STORE_IDS = [k for k, (_, kind) in POINTS_OF_CONTACT.items() if kind == "store"]
ONLINE_ID = "15"

# Статусы позиций Mindbox, которые не считаются продажей: корзина, отмены, возвраты
MB_EXCLUDED_STATUSES = [
    "1", "3214f385-4913-4775-8b09-aac66c775a1e", "33", "37", "4", "40", "41",
    "a0c984fe-0e5c-4e9a-aa33-e0bf9b5b796e",
]

# Цели Метрики для воронки kixbox.ru
FUNNEL_GOALS = [
    ("Корзина", 194384785),
    ("Оформление", 495725731),
    ("Выбор оплаты", 331722040),
    ("Покупка", 3044759623),
]

TRAFFIC_SOURCE_NAMES = {
    "ad": "Реклама", "organic": "Поиск", "direct": "Прямые", "internal": "Внутренние",
    "email": "Рассылки", "referral": "Ссылки", "social": "Соцсети", "messenger": "Мессенджеры",
    "recommend": "Рекомендации", "": "Не определён", "undefined": "Не определён",
    "Ad traffic": "Реклама", "Search engine traffic": "Поиск", "Direct traffic": "Прямые",
    "Internal traffic": "Внутренние", "Mailing traffic": "Рассылки", "Link traffic": "Ссылки",
    "Social network traffic": "Соцсети", "Messenger traffic": "Мессенджеры",
    "Recommendation system traffic": "Рекомендации",
}

DEVICE_NAMES = {"1": "Компьютер", "2": "Смартфон", "3": "Планшет", "4": "ТВ"}
