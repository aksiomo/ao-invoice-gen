"""OpenAI 兼容 Chat Completions 客户端（JSON 输出）。"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import APIError, OpenAI

from app.config import settings

_JSON_FENCE_RE = re.compile(r"\{.*\}|\[.*\]", re.S)


class LLMError(RuntimeError):
    pass


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise LLMError("缺少 OPENAI_API_KEY，请在 .env 中配置")
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.llm_timeout,
        )
    return _client


def chat_json(
    system: str,
    user: str,
    *,
    model: str,
    temperature: float | None = None,
) -> Any:
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except APIError:
        resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    return parse_json(content)


def parse_json(content: str) -> Any:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = _JSON_FENCE_RE.search(content)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    if content.startswith("```"):
        inner = content.strip("`").lstrip("json").strip()
        return json.loads(inner)
    raise LLMError(f"无法解析模型返回的 JSON：{content[:200]}")
