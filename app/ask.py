"""最小 LLM 调用：读配置，问一句，打印回答与用量。"""

from __future__ import annotations

import sys

import requests

from app.config import get_settings


def ask(question: str) -> tuple[str, dict]:
    """调一次 DeepSeek，返回 (回答文本, 用量字典)。"""
    s = get_settings()
    url = f"{s.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {s.deepseek_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": s.deepseek_model,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": s.max_tokens,
        "temperature": s.temperature,
        "stream": False,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=s.request_timeout)
    resp.raise_for_status()
    body = resp.json()
    return body["choices"][0]["message"]["content"], body["usage"]


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "用一句话解释什么是 RAG"
    print(f"问：{question}")
    answer, usage = ask(question)
    print(f"答：{answer}")
    print(
        "用量："
        f"prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')}"
    )


if __name__ == "__main__":
    main()
