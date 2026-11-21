"""一个最小但健壮的 HTTP 客户端：超时、重试、错误分类。"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass

import requests


def should_retry(status: int) -> bool:
    """只有限流和服务器端错误值得重试；其他 4xx 都是我们自己的问题，重试无意义。"""
    return status == 429 or 500 <= status < 600

class HttpError(RuntimeError):
    """请求最终失败。status 为 None 表示连响应都没拿到。"""

    def __init__(self, status: int | None, url: str, detail: str) -> None:
        super().__init__(f"HTTP {status or 'ERR'} {url} -> {detail[:200]}")
        self.status = status
        self.url = url
        self.detail = detail


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff: float = 0.5
    timeout: tuple[float, float] = (3.0, 10.0)


def _parse_json(resp: requests.Response, url: str) -> dict:
    try:
        return resp.json()
    except ValueError as exc:  # 不是 JSON，常见于被劫持返回 HTML
        raise HttpError(resp.status_code, url, f"返回不是 JSON：{resp.text[:200]}") from exc


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    policy: RetryPolicy | None = None,
    headers: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> dict:
    """所有请求的唯一入口：超时、重试、错误分类都在这。"""
    policy = policy or RetryPolicy()
    sess = session or requests.Session()
    reason = "未知错误"

    for attempt in range(1, policy.attempts + 1):
        try:
            resp = sess.request(
                method, url, json=payload, headers=headers or {}, timeout=policy.timeout
            )
        except requests.Timeout:
            reason = "超时"
        except requests.ConnectionError:
            reason = "连接失败"
        else:
            if resp.status_code < 400:
                return _parse_json(resp, url)
            if not should_retry(resp.status_code):
                raise HttpError(resp.status_code, url, resp.text)
            reason = f"HTTP {resp.status_code}"

        if attempt < policy.attempts:
            delay = policy.backoff * 2 ** (attempt - 1) + random.uniform(0, 0.1)
            print(f"[retry {attempt}/{policy.attempts}] {reason}，{delay:.1f}s 后重试")
            time.sleep(delay)

    raise HttpError(None, url, f"重试 {policy.attempts} 次仍失败：{reason}")


def get_json(url: str, **kwargs) -> dict:
    return _request_json("GET", url, **kwargs)


def post_json(url: str, payload: dict, **kwargs) -> dict:
    return _request_json("POST", url, payload=payload, **kwargs)

       

def main() -> None:
    print("① 公共接口 httpbin（无需 key）")
    data = get_json("https://httpbin.org/get")
    print("   返回字段：", sorted(data)[:6])

    print("② DeepSeek /models（不带 key，预期 401 且不重试）")
    try:
        get_json("https://api.deepseek.com/models")
    except HttpError as exc:
        print("   被拒绝：", exc.status, "-", exc.detail[:80])

    print("③ 打一个不存在的地址（预期连接超时 + 重试）")
    try:
        get_json(
            "http://10.255.255.1/",
            policy=RetryPolicy(attempts=2, backoff=0.3, timeout=(1.0, 1.0)),
        )
    except HttpError as exc:
        print("   按预期失败：", str(exc)[:100])


if __name__ == "__main__":
    main()
