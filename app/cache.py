"""商品分类持久化缓存：以完整商品名（去首尾空白）为键，精确匹配。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.config import settings
from app.schemas import ClassifiedItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS classification_cache (
    name TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    short_name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'llm',
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.cache_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.cache_db))
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def cache_key(name: str) -> str:
    return name.strip()


def lookup_many(names: list[str]) -> dict[str, ClassifiedItem]:
    if not names:
        return {}
    keys = [cache_key(n) for n in names]
    conn = _connect()
    try:
        result: dict[str, ClassifiedItem] = {}
        for i in range(0, len(keys), 400):
            batch = keys[i : i + 400]
            marks = ",".join("?" for _ in batch)
            for row in conn.execute(
                f"SELECT name, code, category_name, short_name FROM classification_cache "
                f"WHERE name IN ({marks})",
                batch,
            ):
                result[row["name"]] = ClassifiedItem(
                    name=row["name"],
                    code=row["code"],
                    category_name=row["category_name"],
                    short_name=row["short_name"] or "",
                    from_cache=True,
                )
        return result
    finally:
        conn.close()


def save_many(items: list[ClassifiedItem], *, model: str = "", source: str = "llm") -> None:
    if not items:
        return
    now = datetime.now(UTC).isoformat()
    conn = _connect()
    try:
        conn.executemany(
            "INSERT INTO classification_cache(name, code, category_name, short_name, source, model, created_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET code=excluded.code, category_name=excluded.category_name, "
            "short_name=excluded.short_name, source=excluded.source, model=excluded.model, created_at=excluded.created_at",
            [
                (
                    cache_key(it.name),
                    it.code,
                    it.category_name,
                    it.short_name,
                    source,
                    model,
                    now,
                )
                for it in items
            ],
        )
        conn.commit()
    finally:
        conn.close()
