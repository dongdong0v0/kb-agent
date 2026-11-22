"""结构化输出：让模型返回 JSON，用 pydantic 校验，失败自动重试。"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm import ChatClient

T = TypeVar("T", bound=BaseModel)

# 截断重试时的最小 token 预算：一次给足，避免 20→40→80 连续三次都截断
MIN_RETRY_TOKENS = 256


class StructuredError(RuntimeError):
    """重试耗尽仍未拿到合法 JSON。"""


def chat_json(
    client: ChatClient,
    prompt: str,
    schema: type[T],
    *,
    attempts: int = 3,
    max_tokens: int | None = None,
) -> tuple[T, int]:
    """让模型按 schema 输出 JSON，返回 (解析结果, 实际尝试次数)。

    两类失败分别处理：
    - 被 max_tokens 截断：不是格式错，重发同样预算必然再截断，改为放大预算；
    - JSON/schema 不合规：把校验错误原文回灌，让模型自己改。
    """
    text = (
        f"{prompt}\n\n"
        "只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释。\n"
        f"JSON Schema：{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
    budget = max_tokens
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        extra: dict = {"response_format": {"type": "json_object"}}
        if budget is not None:
            extra["max_tokens"] = budget
        result = client.send(text, extra=extra)

        if result.truncated:
            base = budget or getattr(getattr(client, "settings", None), "max_tokens", 1024)
            budget = max(base * 2, MIN_RETRY_TOKENS)
            last_error = ValueError(
                f"输出被截断（finish_reason=length, max_tokens={base}），下次预算 {budget}"
            )
            text = (
                "你上一次的输出被长度限制截断，JSON 不完整。"
                "请只输出紧凑的 JSON，不要多余空格和换行，文字尽量精简。"
            )
            continue

        try:
            return schema.model_validate_json(result.content), attempt
        except (ValidationError, ValueError) as exc:
            last_error = exc
            text = (
                f"你上一次的输出无法解析：{exc}\n"
                "请重新输出，只给 JSON 对象，字段必须完全符合上面的 Schema。"
            )

    raise StructuredError(f"{attempts} 次尝试均未得到合法 JSON：{last_error}") from last_error
