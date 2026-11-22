"""LLM 客户端：多轮对话、流式输出、用量与成本统计。"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from app.config import Settings, get_settings
from app.http_client import RetryPolicy, post_json


def _setup_stdio() -> None:
    """把标准输入输出强制成 UTF-8，避免 LANG=C 下中文输入解码失败。"""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass



@dataclass
class Message:
    role: str          # system / user / assistant
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResult:
    content: str
    finish_reason: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @property
    def truncated(self) -> bool:
        """回答是否被 max_tokens 截断。"""
        return self.finish_reason == "length"


class ChatClient:
    """维护 messages 历史的对话客户端，支持流式与非流式。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        system_prompt: str | None = None,
        session=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session = session
        self.messages: list[Message] = []
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.last_usage: dict = {}
        if system_prompt:
            self.messages.append(Message("system", system_prompt))

    # ---------------- 非流式 ----------------
    def send(self, user_text: str, *, extra: dict | None = None) -> ChatResult:
        self.messages.append(Message("user", user_text))
        body = post_json(
            self._url(),
            self._payload(extra),
            headers=self._headers(),
            policy=RetryPolicy(attempts=3, backoff=0.5, timeout=(5.0, 60.0)),
            session=self.session,
        )
        result = self._parse(body)
        self.messages.append(Message("assistant", result.content))

        usage = body.get("usage", {}) or {}
        self.last_usage = usage
        self.total_tokens_used += result.total_tokens
        self.total_cost += self._cost(usage)
        return result

    # ---------------- 流式 ----------------
    def stream(self, user_text: str) -> Iterator[str]:
        """逐段 yield 文本；结束时把完整回答写入历史并结算用量。"""
        self.messages.append(Message("user", user_text))
        payload = self._payload() | {
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        pieces: list[str] = []
        usage: dict = {}

        with requests.post(
            self._url(),
            json=payload,
            headers=self._headers(),
            timeout=(5.0, 120.0),
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data: "):
                    continue
                data = raw[len("data: "):]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                piece = (choices[0].get("delta") or {}).get("content") or ""
                if piece:
                    pieces.append(piece)
                    yield piece

        text = "".join(pieces)
        self.messages.append(Message("assistant", text))
        self.last_usage = usage
        self.total_tokens_used += usage.get("total_tokens", 0)
        self.total_cost += self._cost(usage)

    # ---------------- 会话管理 ----------------
    def reset(self) -> None:
        """清空历史，但保留 system prompt。"""
        self.messages = [m for m in self.messages if m.role == "system"]
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.last_usage = {}

    def cost_summary(self) -> str:
        usage = self.last_usage or {}
        this_cost = self._cost(usage)
        return (
            f"本次 tokens={usage.get('total_tokens', 0)} 花费≈¥{this_cost:.6f}｜"
            f"会话累计 tokens={self.total_tokens_used} 花费≈¥{self.total_cost:.6f}"
        )

    # ---------------- 内部 ----------------
    def _url(self) -> str:
        return f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _payload(self, extra: dict | None = None) -> dict:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [m.to_dict() for m in self.messages],
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "stream": False,
        }
        if extra:
            payload.update(extra)
        return payload

    def _cost(self, usage: dict) -> float:
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        return (
            prompt / 1_000_000 * self.settings.price_input_per_mtok
            + completion / 1_000_000 * self.settings.price_output_per_mtok
        )

    @staticmethod
    def _parse(body: dict) -> ChatResult:
        choice = body["choices"][0]
        usage = body.get("usage", {}) or {}
        return ChatResult(
            content=choice["message"]["content"],
            finish_reason=choice.get("finish_reason", ""),
            model=body.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )


# ---------------- 命令行入口 ----------------
def main() -> None:
    _setup_stdio()
    client = ChatClient(system_prompt="你是一个简洁的技术助手，回答不超过三句话。")
    print("输入问题，输入 exit 退出。")
    while True:
        try:
            text = input("\n你> ").strip()
        except UnicodeDecodeError:
            print("  [输入编码异常] 终端送来的字节不是 UTF-8，检查终端编码或重新输入。")
            continue
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"exit", "quit"}:
            break
        result = client.send(text)
        print(f"AI> {result.content}")
        flag = "  ⚠ 被截断" if result.truncated else ""
        print(f"   [finish={result.finish_reason}{flag}] {client.cost_summary()}")


def main_stream() -> None:
    _setup_stdio()
    client = ChatClient(system_prompt="你是一个简洁的技术助手。")
    print("流式对话，输入 exit 退出。")
    while True:
        try:
            text = input("\n你> ").strip()
        except UnicodeDecodeError:
            print("  [输入编码异常] 终端送来的字节不是 UTF-8，检查终端编码或重新输入。")
            continue
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"exit", "quit"}:
            break
        print("AI> ", end="", flush=True)
        for piece in client.stream(text):
            print(piece, end="", flush=True)
        print()
        print(f"   {client.cost_summary()}")


if __name__ == "__main__":
    main()
