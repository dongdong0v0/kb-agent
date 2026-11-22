"""结构化输出：让模型返回 JSON，用 pydantic 校验，失败自动重试。"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm import ChatClient

T = TypeVar("T", bound=BaseModel)


class StructuredError(RuntimeError):
    """重试耗尽仍未拿到合法 JSON。"""


def chat_json(
    client: ChatClient,
    prompt: str,
    schema: type[T],
    *,
    attempts: int = 3,
) -> tuple[T, int]:
    """让模型按 schema 输出 JSON，返回 (解析结果, 实际尝试次数)。"""
    text = (
        f"{prompt}\n\n"
        "只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释。\n"
        f"JSON Schema：{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        result = client.send(text, extra={"response_format": {"type": "json_object"}})
        try:
            return schema.model_validate_json(result.content), attempt
        except (ValidationError, ValueError) as exc:
            last_error = exc
            text = (
                f"你上一次的输出无法解析：{exc}\n"
                "请重新输出，只给 JSON 对象，字段必须完全符合上面的 Schema。"
            )
    raise StructuredError(f"{attempts} 次尝试均未得到合法 JSON：{last_error}") from last_error
