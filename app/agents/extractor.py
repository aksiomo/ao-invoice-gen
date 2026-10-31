"""Agent A：把不确定格式的采购表格矩阵规范化为明细 JSON。"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from app.agents.llm import chat_json
from app.agents.prompts import (
    EXTRACTOR_RETRY_TEMPLATE,
    EXTRACTOR_SYSTEM,
    EXTRACTOR_USER_TEMPLATE,
)
from app.config import settings
from app.schemas import PurchaseItem


class ExtractionError(RuntimeError):
    pass


def _clean_number(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _as_text_cell_set(matrix: list[list[str]]) -> set[str]:
    cells: set[str] = set()
    for row in matrix:
        for cell in row:
            cell = cell.strip()
            if cell:
                cells.add(cell)
    return cells


def _chunk_matrix(matrix: list[list[str]], max_rows: int) -> list[list[list[str]]]:
    if len(matrix) <= max_rows:
        return [matrix]
    chunks: list[list[list[str]]] = []
    for start in range(0, len(matrix), max_rows):
        chunks.append(matrix[start : start + max_rows])
    return chunks


def _parse_items(payload: object, known_cells: set[str]) -> tuple[list[PurchaseItem], list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict) or "items" not in payload:
        raise ExtractionError("模型未返回 items 对象")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ExtractionError("items 不是数组")

    items: list[PurchaseItem] = []
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            errors.append(f"第 {idx + 1} 行不是对象")
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            errors.append(f"第 {idx + 1} 行缺少 name")
            continue
        if name not in known_cells:
            errors.append(f"第 {idx + 1} 行商品名“{name}”在原表中逐字符不存在，疑似被改写")
            continue
        try:
            item = PurchaseItem(
                receipt_no=str(raw.get("receipt_no", "")).strip(),
                receipt_date=str(raw.get("receipt_date", "")).strip(),
                supplier=str(raw.get("supplier", "")).strip(),
                item_code=str(raw.get("item_code", "")).strip(),
                name=name,
                spec_input=str(raw.get("spec_input", "")).strip(),
                unit=str(raw.get("unit", "")).strip(),
                quantity=_clean_number(raw.get("quantity")),
                unit_price=_clean_number(raw.get("unit_price")),
                amount=_clean_number(raw.get("amount")),
            )
        except (ValueError, TypeError) as exc:  # pragma: no cover - 防御性
            errors.append(f"第 {idx + 1} 行解析失败：{exc}")
            continue
        items.append(item)
    return items, errors


def _extract_chunk(
    matrix: list[list[str]], known_cells: set[str]
) -> list[PurchaseItem]:
    user = EXTRACTOR_USER_TEMPLATE.format(matrix=json.dumps(matrix, ensure_ascii=False))
    payload = chat_json(
        EXTRACTOR_SYSTEM, user, model=settings.extractor_model_name
    )
    items, errors = _parse_items(payload, known_cells)
    if errors:
        retry_user = EXTRACTOR_RETRY_TEMPLATE.format(
            errors="\n".join(f"- {e}" for e in errors[:20]),
            matrix=json.dumps(matrix, ensure_ascii=False),
            previous=json.dumps(payload, ensure_ascii=False)[:4000],
        )
        payload = chat_json(
            EXTRACTOR_SYSTEM, retry_user, model=settings.extractor_model_name
        )
        items, errors = _parse_items(payload, known_cells)
        if errors:
            raise ExtractionError("; ".join(errors[:10]))
    return items


def extract_items(matrix: list[list[str]]) -> list[PurchaseItem]:
    known_cells = _as_text_cell_set(matrix)
    items: list[PurchaseItem] = []
    for chunk in _chunk_matrix(matrix, settings.extract_chunk_rows):
        items.extend(_extract_chunk(chunk, known_cells))
    if not items:
        raise ExtractionError("未从文件中提取到任何商品明细行")
    return items
