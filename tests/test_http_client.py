"""http_client 的单元测试：用假 session，不打真实网络。"""

from __future__ import annotations

import pytest

from app.http_client import HttpError, RetryPolicy, get_json


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or ("" if payload is None else str(payload))

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """按顺序返回预设结果；遇到 Exception 实例就抛出。"""

    def __init__(self, results: list) -> None:
        self.results = list(results)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


NO_SLEEP = RetryPolicy(attempts=3, backoff=0.0, timeout=(1.0, 1.0))


def test_success_returns_json_and_calls_once() -> None:
    session = FakeSession([FakeResponse(200, {"ok": True})])
    assert get_json("http://x", policy=NO_SLEEP, session=session) == {"ok": True}
    assert session.calls == 1


def test_retries_on_503_then_succeeds() -> None:
    session = FakeSession([FakeResponse(503), FakeResponse(200, {"ok": 1})])
    assert get_json("http://x", policy=NO_SLEEP, session=session) == {"ok": 1}
    assert session.calls == 2


def test_401_fails_fast_without_retry() -> None:
    session = FakeSession([FakeResponse(401, text="unauthorized")])
    with pytest.raises(HttpError) as excinfo:
        get_json("http://x", policy=NO_SLEEP, session=session)
    assert excinfo.value.status == 401
    assert session.calls == 1


def test_html_body_raises_clear_error() -> None:
    session = FakeSession([FakeResponse(200, None, text="<html>login</html>")])
    with pytest.raises(HttpError) as excinfo:
        get_json("http://x", policy=NO_SLEEP, session=session)
    assert "不是 JSON" in str(excinfo.value)


def test_all_attempts_exhausted_raises() -> None:
    session = FakeSession([FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    with pytest.raises(HttpError):
        get_json("http://x", policy=NO_SLEEP, session=session)
    assert session.calls == 3

def test_408_fails_fast_under_new_policy() -> None:
    """408 是客户端发得太慢，重试同一个慢客户端没意义，应立即失败。"""
    session = FakeSession([FakeResponse(408, text="timeout")])
    with pytest.raises(HttpError):
        get_json("http://x", policy=NO_SLEEP, session=session)
    assert session.calls == 1

def test_503_still_retries() -> None:
    """新策略没有误伤 5xx，服务器端错误仍然重试。"""
    session = FakeSession([FakeResponse(503), FakeResponse(200, {"ok": 1})])
    assert get_json("http://x", policy=NO_SLEEP, session=session) == {"ok": 1}
    assert session.calls == 2
