"""结构化输出测试：不联网，用假客户端喂脚本化回答。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm import ChatClient, ChatResult
from app.structured import StructuredError, chat_json


class Answer(BaseModel):
    title: str
    score: int


class _FakeKey:
    def get_secret_value(self) -> str:
        return "sk-test"


class StubSettings:
    deepseek_base_url = "https://api.example.com/v1"
    deepseek_api_key = _FakeKey()
    deepseek_model = "deepseek-chat"
    max_tokens = 128
    temperature = 0.0
    price_input_per_mtok = 2.0
    price_output_per_mtok = 8.0


class FakeClient:
    """按脚本返回 (content, finish_reason)，并记录每次请求参数。"""

    def __init__(self, replies: list[tuple[str, str]]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, dict | None]] = []
        self.settings = StubSettings()

    def send(self, user_text: str, *, extra: dict | None = None) -> ChatResult:
        self.calls.append((user_text, extra))
        content, finish_reason = self.replies.pop(0)
        return ChatResult(
            content=content,
            finish_reason=finish_reason,
            model="stub",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


def test_chat_json_parses_first_reply():
    client = FakeClient([('{"title": "RAG", "score": 9}', "stop")])

    answer, attempts = chat_json(client, "给个评价", Answer)

    assert attempts == 1
    assert answer.title == "RAG"
    assert answer.score == 9
    text, extra = client.calls[0]
    assert "JSON Schema" in text
    assert extra == {"response_format": {"type": "json_object"}}


def test_chat_json_retries_with_correction():
    client = FakeClient([
        ("不是 JSON，先解释一下", "stop"),
        ('{"title": "RAG", "score": 8}', "stop"),
    ])

    answer, attempts = chat_json(client, "给个评价", Answer)

    assert attempts == 2
    assert answer.score == 8
    assert "无法解析" in client.calls[1][0]
    assert "max_tokens" not in client.calls[1][1]


def test_chat_json_raises_after_attempts():
    client = FakeClient([("坏", "stop"), ("还是坏", "stop"), ("依然坏", "stop")])

    with pytest.raises(StructuredError):
        chat_json(client, "给个评价", Answer, attempts=3)

    assert len(client.calls) == 3


def test_truncated_output_raises_budget_instead_of_repeating():
    client = FakeClient([
        ('{"title": "RAG", "sco', "length"),
        ('{"title": "RAG", "score": 7}', "stop"),
    ])

    answer, attempts = chat_json(client, "给个评价", Answer, attempts=3, max_tokens=20)

    assert attempts == 2
    assert answer.score == 7
    assert client.calls[0][1]["max_tokens"] == 20
    assert client.calls[1][1]["max_tokens"] >= 256
    assert "截断" in client.calls[1][0]


def test_truncated_every_time_raises_structured_error():
    client = FakeClient([('{"a"', "length"), ('{"a"', "length")])

    with pytest.raises(StructuredError) as err:
        chat_json(client, "给个评价", Answer, attempts=2, max_tokens=20)

    assert "截断" in str(err.value)


def test_payload_merges_extra_params():
    client = ChatClient(settings=StubSettings(), system_prompt="sys")

    payload = client._payload({"response_format": {"type": "json_object"}, "max_tokens": 999})

    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 999
    assert payload["stream"] is False
    assert payload["model"] == "deepseek-chat"
