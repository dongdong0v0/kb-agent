"""结构化输出测试：不联网，用假客户端喂脚本化回答。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm import ChatResult, ChatClient
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
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, dict | None]] = []

    def send(self, user_text: str, *, extra: dict | None = None) -> ChatResult:
        self.calls.append((user_text, extra))
        content = self.replies.pop(0)
        return ChatResult(
            content=content,
            finish_reason="stop",
            model="stub",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


def test_chat_json_parses_first_reply():
    client = FakeClient(['{"title": "RAG", "score": 9}'])

    answer, attempts = chat_json(client, "给个评价", Answer)

    assert attempts == 1
    assert answer.title == "RAG"
    assert answer.score == 9
    text, extra = client.calls[0]
    assert "JSON Schema" in text
    assert extra == {"response_format": {"type": "json_object"}}


def test_chat_json_retries_with_correction():
    client = FakeClient(["不是 JSON，先解释一下", '{"title": "RAG", "score": 8}'])

    answer, attempts = chat_json(client, "给个评价", Answer)

    assert attempts == 2
    assert answer.score == 8
    assert "无法解析" in client.calls[1][0]


def test_chat_json_raises_after_attempts():
    client = FakeClient(["坏", "还是坏", "依然坏"])

    with pytest.raises(StructuredError):
        chat_json(client, "给个评价", Answer, attempts=3)

    assert len(client.calls) == 3


def test_payload_merges_extra_params():
    client = ChatClient(settings=StubSettings(), system_prompt="sys")

    payload = client._payload({"response_format": {"type": "json_object"}})

    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    assert payload["model"] == "deepseek-chat"
