"""LLM 客户端：多轮对话、用量统计、可注入 session 便于测试。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.http_client import RetryPolicy, post_json


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
    """维护 messages 历史的多轮对话客户端。"""

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
        if system_prompt:
            self.messages.append(Message("system", system_prompt))

    # ---- 对外 ----
    def send(self, user_text: str) -> ChatResult:
        self.messages.append(Message("user", user_text))
        body = post_json(
            self._url(),
            self._payload(),
            headers=self._headers(),
            policy=RetryPolicy(attempts=3, backoff=0.5, timeout=(5.0, 60.0)),
            session=self.session,
        )
        result = self._parse(body)
        self.messages.append(Message("assistant", result.content))
        self.total_tokens_used += result.total_tokens
        return result

    def reset(self) -> None:
        """清空历史，但保留 system prompt。"""
        self.messages = [m for m in self.messages if m.role == "system"]
        self.total_tokens_used = 0

    # ---- 内部 ----
    def _url(self) -> str:
        return f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _payload(self) -> dict:
        return {
            "model": self.settings.deepseek_model,
            "messages": [m.to_dict() for m in self.messages],
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "stream": False,
        }

    @staticmethod
    def _parse(body: dict) -> ChatResult:
        choice = body["choices"][0]
        usage = body.get("usage", {})
        return ChatResult(
            content=choice["message"]["content"],
            finish_reason=choice.get("finish_reason", ""),
            model=body.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )


def main() -> None:
    client = ChatClient(system_prompt="你是一个简洁的技术助手，回答不超过三句话。")
    print("输入问题，输入 exit 退出。")
    while True:
        try:
            text = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"exit", "quit"}:
            break

        result = client.send(text)
        print(f"AI> {result.content}")
        flag = "  ⚠ 被截断" if result.truncated else ""
        print(
            f"   [finish={result.finish_reason}{flag} "
            f"tokens={result.prompt_tokens}+{result.completion_tokens}"
            f"={result.total_tokens} 累计={client.total_tokens_used}]"
        )
    print("\n会话结束。")


if __name__ == "__main__":
    main()
