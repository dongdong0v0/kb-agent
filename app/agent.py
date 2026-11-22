"""手写 Function Calling 循环：不引入任何 Agent 框架，只看协议本身。

一轮完整的 tools 往返：
1. 请求里带 tools（函数说明书）；
2. 模型不回文本，而是回 assistant.tool_calls（函数名 + arguments 字符串）；
3. 你的代码执行函数，把结果作为 role="tool" + tool_call_id 回填；
4. 模型拿着工具结果给出最终回答。
关键：assistant 那条带 tool_calls 的消息必须原样放回历史，否则下一轮模型对不上 id。
"""

from __future__ import annotations

import json
import sys

import requests

from app.config import get_settings
from app.tools import TOOL_SPECS, execute


class ToolAgent:
    def __init__(self, max_rounds: int = 5) -> None:
        self.max_rounds = max_rounds
        self.settings = get_settings()
        self.messages: list[dict] = []

    def _post(self) -> dict:
        resp = requests.post(
            f"{self.settings.deepseek_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.deepseek_model,
                "messages": self.messages,
                "tools": TOOL_SPECS,
                "tool_choice": "auto",      # 让模型自己决定调不调、调哪个
                "temperature": self.settings.temperature,
            },
            timeout=self.settings.request_timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def run(self, question: str, verbose: bool = True) -> str:
        self.messages.append({"role": "user", "content": question})
        for round_no in range(1, self.max_rounds + 1):
            data = self._post()
            msg = data["choices"][0]["message"]
            self.messages.append(msg)          # 原样回填，含 tool_calls

            calls = msg.get("tool_calls") or []
            if not calls:
                return msg.get("content") or ""

            for call in calls:                 # 一轮可能并行返回多个调用
                fn = call["function"]
                if verbose:
                    print(f"[第 {round_no} 轮] 模型决定调用 {fn['name']}({fn['arguments']})")
                output = execute(fn["name"], fn["arguments"])
                if verbose:
                    print(f"           工具返回 {output[:120]}")
                self.messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": output}
                )
        return "（超过最大轮数仍未收敛）"


def main() -> None:
    question = " ".join(sys.argv[1:]) or "我手上有几篇论文？其中最大的那篇多大、什么时候放进去的？"
    agent = ToolAgent()
    answer = agent.run(question)
    print(f"\n问：{question}\n答：{answer}")


if __name__ == "__main__":
    main()
