"""本地工具：模型只能看到 schema，真正的执行永远在这里发生。

D11 的核心认知：
- 模型返回的 tool_calls 只是「调用意图」（函数名 + 参数 JSON），它没有执行任何东西；
- 执行由你的代码完成，再把结果作为 role="tool" 的消息喂回去；
- 所以「模型能不能调对函数」= schema 写得清不清楚 + 参数有没有校验。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def corpus_list() -> list[dict[str, Any]]:
    """列出语料目录里的 PDF。"""
    return [
        {"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)}
        for p in sorted(RAW_DIR.glob("*.pdf"))
    ]


def file_info(name: str) -> dict[str, Any]:
    """查单个文件的大小与修改时间。"""
    path = RAW_DIR / name
    if not path.is_file():
        return {"error": f"没有这个文件：{name}"}
    st = path.stat()
    return {
        "name": path.name,
        "size_kb": round(st.st_size / 1024, 1),
        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
    }


# 给模型看的说明书：名字、用途、参数类型，三者都不能含糊，否则它调不对
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "corpus_list",
            "description": "列出本地语料目录 data/raw 下所有 PDF 的文件名和大小。当用户问「有几篇文件」「都有哪些资料」时使用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "查询单个文件的精确大小和修改时间。只在已知文件名时使用；文件名要带 .pdf 后缀。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "文件名，例如 1706.03762.pdf"}
                },
                "required": ["name"],
            },
        },
    },
]

HANDLERS: dict[str, Callable[..., Any]] = {"corpus_list": corpus_list, "file_info": file_info}


def execute(name: str, arguments_json: str) -> str:
    """执行一次工具调用，永远返回字符串：模型只吃文本。"""
    if name not in HANDLERS:
        return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)
    try:
        args = json.loads(arguments_json or "{}")
        result = HANDLERS[name](**args)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        # 参数错不能抛给上层崩掉循环，要变成模型能读懂的错误信息
        return json.dumps({"error": f"参数错误：{exc}"}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
