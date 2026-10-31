"""Agent B：为未命中缓存的商品从候选编码中精选叶子分类。"""

from __future__ import annotations

import json

from app import taxonomy
from app.agents.llm import chat_json
from app.agents.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_USER_TEMPLATE
from app.cache import lookup_many, save_many
from app.config import settings
from app.schemas import ClassifiedItem


class ClassificationError(RuntimeError):
    pass


_CODE_OK = set("0123456789")


def _valid_code(code: object) -> bool:
    return isinstance(code, str) and len(code) == 19 and all(ch in _CODE_OK for ch in code)


def _build_tasks(names: list[str], k: int) -> tuple[list[dict], dict[str, list[taxonomy.Candidate]]]:
    tasks: list[dict] = []
    candidates_map: dict[str, list[taxonomy.Candidate]] = {}
    conn = taxonomy._connect()
    try:
        for name in names:
            candidates = taxonomy.search(name, k, conn=conn)
            candidates_map[name] = candidates
            tasks.append(
                {
                    "name": name,
                    "candidates": [c.brief() for c in candidates],
                }
            )
    finally:
        conn.close()
    return tasks, candidates_map


def _validate_results(
    payload: object, requested: list[str]
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    chosen: dict[str, str] = {}
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ClassificationError("模型未返回 results 数组")
    for row in payload["results"]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", ""))
        code = str(row.get("code", "")).strip()
        if name not in requested:
            errors.append(f"返回了未请求的商品名（可能被改写）：{name!r}")
            continue
        if not _valid_code(code):
            errors.append(f"商品“{name}”编码非法：{code!r}")
            continue
        chosen[name] = code
    missing = [n for n in requested if n not in chosen]
    if missing:
        errors.append("以下商品缺少结果：" + "、".join(missing[:10]))
    return chosen, errors


def _resolve_codes(chosen: dict[str, str]) -> tuple[list[ClassifiedItem], list[str]]:
    items: list[ClassifiedItem] = []
    errors: list[str] = []
    conn = taxonomy._connect()
    try:
        for name, code in chosen.items():
            cand = taxonomy.get_by_code(code, conn)
            if cand is None:
                errors.append(f"商品“{name}”的编码 {code} 在编码库中不存在")
                continue
            if not taxonomy.is_leaf_code(code, conn):
                errors.append(f"商品“{name}”的编码 {code} 不是叶子节点")
                continue
            items.append(
                ClassifiedItem(
                    name=name,
                    code=cand.code,
                    category_name=cand.name,
                    short_name=cand.short_name,
                )
            )
    finally:
        conn.close()
    return items, errors


def _llm_classify(names: list[str]) -> list[ClassifiedItem]:
    if not names:
        return []
    k = max(settings.top_k, 20)
    tasks, _ = _build_tasks(names, k)
    user = CLASSIFIER_USER_TEMPLATE.format(
        tasks=json.dumps(tasks, ensure_ascii=False)
    )
    payload = chat_json(
        CLASSIFIER_SYSTEM, user, model=settings.classifier_model_name
    )
    chosen, errors = _validate_results(payload, names)
    if errors:
        payload = chat_json(
            CLASSIFIER_SYSTEM
            + "\n上次输出有误，请严格修正："
            + "；".join(errors[:10]),
            user,
            model=settings.classifier_model_name,
        )
        chosen, errors = _validate_results(payload, names)
        if errors:
            raise ClassificationError("; ".join(errors[:10]))

    items, errors = _resolve_codes(chosen)
    if errors:
        bad_names = [e.split("“")[1].split("”")[0] for e in errors if "“" in e]
        if bad_names:
            retry_items = _llm_classify_single(bad_names)
            ok_names = {it.name for it in retry_items}
            items = [it for it in items if it.name not in ok_names]
            items.extend(retry_items)
            remaining = [e for e in errors if all(n not in e for n in ok_names)]
            if remaining:
                raise ClassificationError("; ".join(remaining[:10]))
        elif errors:
            raise ClassificationError("; ".join(errors[:10]))
    return items


def _llm_classify_single(names: list[str]) -> list[ClassifiedItem]:
    resolved: list[ClassifiedItem] = []
    for name in names:
        tasks, _ = _build_tasks([name], max(settings.top_k, 30))
        user = CLASSIFIER_USER_TEMPLATE.format(
            tasks=json.dumps(tasks, ensure_ascii=False)
        )
        hint = "\n该商品上次分类失败，请只从候选中选择最有把握的叶子编码；若候选都不合适，给出编码库中真实存在的叶子编码。"
        payload = chat_json(
            CLASSIFIER_SYSTEM + hint, user, model=settings.classifier_model_name
        )
        chosen, errors = _validate_results(payload, [name])
        if not errors:
            items, resolve_errors = _resolve_codes(chosen)
            if not resolve_errors:
                resolved.extend(items)
    return resolved


def classify_names(names: list[str]) -> tuple[list[ClassifiedItem], int]:
    """对商品名分类，返回结果与缓存命中数。结果 name 与输入逐字符一致。"""
    unique_names = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    cached = lookup_many(unique_names)
    result: list[ClassifiedItem] = []
    missing: list[str] = []
    for name in unique_names:
        hit = cached.get(name)
        if hit is not None:
            result.append(hit)
        else:
            missing.append(name)

    fresh: list[ClassifiedItem] = []
    for i in range(0, len(missing), settings.classify_batch_size):
        batch = missing[i : i + settings.classify_batch_size]
        fresh.extend(_llm_classify(batch))

    if fresh:
        save_many(fresh, model=settings.classifier_model_name)
        result.extend(fresh)

    by_name = {it.name: it for it in result}
    ordered = [by_name[n] for n in unique_names if n in by_name]
    return ordered, len(cached)
