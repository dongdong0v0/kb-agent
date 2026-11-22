"""工具层的测试：不碰网络，只测「schema 与本地执行」这一层。"""

from __future__ import annotations

import json

from app.tools import TOOL_SPECS, corpus_list, execute, file_info


def test_corpus_list_returns_rows() -> None:
    rows = corpus_list()
    assert rows and all({"name", "size_kb"} <= set(r) for r in rows)


def test_file_info_missing_file_returns_error() -> None:
    assert "error" in file_info("不存在.pdf")


def test_execute_unknown_tool() -> None:
    assert "未知工具" in execute("rm_rf", "{}")


def test_execute_bad_arguments() -> None:
    assert "参数错误" in execute("file_info", "{not json")


def test_execute_file_info_ok() -> None:
    name = corpus_list()[0]["name"]
    payload = json.loads(execute("file_info", json.dumps({"name": name})))
    assert payload["name"] == name and payload["size_kb"] > 0


def test_tool_specs_shape() -> None:
    for spec in TOOL_SPECS:
        assert spec["type"] == "function"
        assert spec["function"]["description"]
        assert "parameters" in spec["function"]
