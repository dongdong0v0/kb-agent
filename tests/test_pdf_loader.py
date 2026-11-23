"""pdf_loader 的测试：合成页面测规则，真 PDF 测端到端（文件不在就跳过）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pdf_loader import (
    Page,
    _clean_line,
    detect_boilerplate,
    join_hyphenation,
    load_document,
    parse_pages,
    strip_boilerplate,
)

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
SAMPLE = RAW / "1706.03762.pdf"


def _fake_pages(n: int = 4) -> list[Page]:
    """12 行一页：第 0 行页眉、第 11 行页码，中间是正文（其中第 5 行是单独的数学符号 v）。"""
    pages = []
    for i in range(1, n + 1):
        lines = ["某某会议 2023"] + [f"正文第 {j} 行" for j in range(1, 5)]
        lines.append("v")
        lines += [f"正文第 {j} 行" for j in range(6, 11)]
        lines.append(str(i))
        pages.append(Page("d", i, lines))
    return pages


def test_clean_line_strips_cid_and_collapses_space() -> None:
    assert _clean_line("hello   (cid:63)world\u00a0 ") == "hello world"


def test_join_hyphenation_keeps_word() -> None:
    assert join_hyphenation("informa-\ntion retrieval") == "informa-tion retrieval"


def test_detect_boilerplate_finds_repeated_header() -> None:
    assert "某某会议 #" in detect_boilerplate(_fake_pages())


def test_strip_removes_header_and_page_number_keeps_body() -> None:
    clean, removed = strip_boilerplate(_fake_pages())
    for p in clean:
        assert "某某会议 2023" not in p.lines      # 页眉删掉
        assert p.lines[-1] != str(p.page_no)       # 页码删掉
        assert "v" in p.lines                      # 正文里的单字母公式符号留着
    assert removed


@pytest.mark.skipif(not SAMPLE.exists(), reason="语料不在")
def test_parse_real_pdf_has_spaces() -> None:
    pages = parse_pages(SAMPLE)
    assert len(pages) > 5
    text = " ".join(" ".join(p.lines) for p in pages)
    assert "scholarly works" in text                 # 默认 x_tolerance=3 会粘成 scholarlyworks
    assert "attribution is provided" in text


@pytest.mark.skipif(not SAMPLE.exists(), reason="语料不在")
def test_load_document_reports_stats() -> None:
    text, stat = load_document(SAMPLE)
    assert stat["pages"] == 15 and stat["chars"] > 10000
    assert stat["kept_lines"] <= stat["raw_lines"]
    assert text.count("\n\n") >= 10