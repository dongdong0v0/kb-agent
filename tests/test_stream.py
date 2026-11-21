"""流式接口测试：用假响应跑，不打网络。"""

from __future__ import annotations

import json

import pytest

from app.llm import ChatClient


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


def _chunk(text: str) -> str:
    body = {"choices": [{"delta": {"content": text}}]}
    return "data: " + json.dumps(body, ensure_ascii=False)


def _usage(prompt: int, completion: int) -> str:
    body = {
        "choices": [],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }
    return "data: " + json.dumps(body)


class FakeResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = True):
        return iter(self._lines)


def _patch_post(monkeypatch, lines: list[str]) -> dict:
    """把 requests.post 换成假实现，返回捕获到的请求参数。"""
    captured: dict = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        captured["stream"] = kwargs.get("stream")
        return FakeResponse(lines)

    monkeypatch.setattr("app.llm.requests.post", fake_post)
    return captured


def test_stream_concatenates_and_records(monkeypatch):
    lines = [
        "",
        ": keep-alive",
        _chunk("你"),
        _chunk("好"),
        _usage(1000, 500),
        "data: [DONE]",
    ]
    captured = _patch_post(monkeypatch, lines)
    client = ChatClient(settings=StubSettings(), system_prompt="你是助手")

    pieces = list(client.stream("hi"))

    assert pieces == ["你", "好"]
    assert client.messages[-2].role == "user"
    assert client.messages[-2].content == "hi"
    assert client.messages[-1].role == "assistant"
    assert client.messages[-1].content == "你好"
    assert client.total_tokens_used == 1500
    assert client.total_cost == pytest.approx(0.006)
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert captured["stream"] is True


def test_stream_ignores_non_data_lines_and_stops_at_done(monkeypatch):
    lines = [
        "event: ping",
        "",
        "data: [DONE]",
        _chunk("不该出现"),
    ]
    _patch_post(monkeypatch, lines)
    client = ChatClient(settings=StubSettings())

    pieces = list(client.stream("hi"))

    assert pieces == []
    assert client.messages[-1].content == ""


def test_stream_cost_accumulates_and_reset_clears(monkeypatch):
    _patch_post(monkeypatch, [_chunk("a"), _usage(100, 100), "data: [DONE]"])
    client = ChatClient(settings=StubSettings(), system_prompt="sys")

    list(client.stream("第一问"))
    assert client.total_tokens_used == 200
    first = client.total_cost

    list(client.stream("第二问"))
    assert client.total_tokens_used == 400
    assert client.total_cost == pytest.approx(first * 2)
    assert "¥" in client.cost_summary()

    client.reset()
    assert client.total_tokens_used == 0
    assert client.total_cost == 0.0
    assert [m.role for m in client.messages] == ["system"]
