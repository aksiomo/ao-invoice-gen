"""开发期内存任务表：单进程足够；记录阶段进度与结果。"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.schemas import FinalRow, PurchaseItem


def _default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return format(obj, "f")
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"不可序列化类型：{type(obj)}")


@dataclass
class Job:
    id: str
    filename: str
    stage: str = "queued"
    message: str = ""
    total_items: int = 0
    unique_names: int = 0
    cache_hits: int = 0
    warnings: list[str] = field(default_factory=list)
    rows: list[FinalRow] = field(default_factory=list)
    items: list[PurchaseItem] = field(default_factory=list)
    output_path: Path | None = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def public(self) -> dict[str, Any]:
        done = self.stage == "done"
        return {
            "id": self.id,
            "filename": self.filename,
            "stage": self.stage,
            "message": self.message,
            "total_items": self.total_items,
            "unique_names": self.unique_names,
            "cache_hits": self.cache_hits,
            "warnings": self.warnings,
            "error": self.error,
            "download_url": f"/api/jobs/{self.id}/download" if done else None,
            "rows": [
                {
                    "name": r.name,
                    "code": r.code,
                    "category_name": r.category_name,
                    "unit": r.unit,
                    "quantity": _default(r.quantity) if r.quantity is not None else "",
                    "unit_price": _default(r.unit_price) if r.unit_price is not None else "",
                    "amount": _default(r.amount) if r.amount is not None else "",
                    "tax_rate": _default(r.tax_rate),
                    "from_cache": r.from_cache,
                    "amount_warning": r.amount_warning,
                }
                for r in self.rows
            ],
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, filename: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


registry = JobRegistry()
