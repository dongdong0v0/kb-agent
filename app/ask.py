"""最小 LLM 调用：验证 API key 可用，观察返回结构。"""

from __future__ import annotations

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
API_URL = "https://api.deepseek.com/chat/completions"


def load_env(path: Path) -> dict[str, str]:
    """读 .env，返回键值对。只支持 KEY=VALUE 形式。"""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def ask(question: str, api_key: str) -> tuple[str, dict]:
    """问一句，返回 (回答文本, 用量信息)。"""
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": question}],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return body["choices"][0]["message"]["content"], body["usage"]


def main() -> None:
    env = load_env(ENV_FILE)
    api_key = env.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY，请在 .env 里配置")

    answer, usage = ask("用一句话解释什么是 RAG，不要超过 40 字",api_key)
    print("回答：", answer)
    print("用量：", usage)


if __name__ == "__main__":
    main()
