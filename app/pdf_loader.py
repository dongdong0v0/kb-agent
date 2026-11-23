"""PDF → 干净文本：核心不是 extract_text，而是知道它什么时候骗你。

实测（data/raw 里 4 篇 arXiv 论文）：
- pdfplumber 默认 x_tolerance=3 会把词粘在一起（"scholarlyworks."），因为 LaTeX PDF 的词间
  空隙被当成同一个词的字符间距；降到 2 才恢复空格。
- 每页都可能带页眉页脚（论文标题、页码、arXiv 编号），它们在正文里制造噪声，必须按"跨页重复"
  自动识别，而不是写死字符串。
- 双栏 PDF 抽出来会串行（左栏末行接右栏首行），这是文本层顺序问题，靠抽文本解决不了，
  只能靠版面分析（W3 后面才碰）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class Page:
    doc: str
    page_no: int          # 从 1 开始
    lines: list[str]

    def text(self) -> str:
        return "\n".join(self.lines)


def _clean_line(raw: str) -> str:
    s = raw.replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    s = re.sub(r"\(cid:\d+\)", "", s)        # 缺字形时 pdfplumber 会吐 (cid:63)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return s.strip()


def parse_pages(path: str | Path, *, x_tolerance: float = 2, y_tolerance: float = 3) -> list[Page]:
    """逐页抽文本。x_tolerance=2 是实测值：默认 3 会粘词。"""
    path = Path(path)
    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages, start=1):
            raw = pg.extract_text(x_tolerance=x_tolerance, y_tolerance=y_tolerance) or ""
            lines = [c for c in (_clean_line(l) for l in raw.split("\n")) if c]
            pages.append(Page(path.stem, i, lines))
    return pages


def _fingerprint(line: str) -> str:
    """把数字抹平，让「第 3 页」「第 12 页」算同一条。"""
    return re.sub(r"\d+", "#", line.strip().lower())


def detect_boilerplate(pages: list[Page], *, max_ratio: float = 0.5) -> set[str]:
    """页眉页脚 = 在多数页的顶部/底部重复出现的行。只看前 3 行和后 3 行。"""
    counter: Counter[str] = Counter()
    for p in pages:
        edge = p.lines[:3] + p.lines[-3:]
        for fp in {_fingerprint(l) for l in edge}:
            counter[fp] += 1
    need = max(2, int(len(pages) * max_ratio))
    return {fp for fp, n in counter.items() if n >= need}


def strip_boilerplate(pages: list[Page]) -> tuple[list[Page], list[str]]:
    """去页眉页脚 + 页码。返回新页列表和被删掉的样本，方便人工核对。

    页码只在前 2 行和后 2 行里删：arXiv 论文正文里单独成行的 "v"、"i"、"c" 常常是公式符号，
    第一版把全页单独成行的 1-4 位字母数字都当页码删，误伤了数学内容。
    """
    boiler = detect_boilerplate(pages)
    removed: list[str] = []
    out: list[Page] = []
    for p in pages:
        n = len(p.lines)
        kept: list[str] = []
        for idx, line in enumerate(p.lines):
            at_edge = idx < 2 or idx >= n - 2
            looks_like_number = bool(re.fullmatch(r"[\divxlcd]{1,4}", line))
            if _fingerprint(line) in boiler or (at_edge and looks_like_number):
                if len(removed) < 20:
                    removed.append(line)
                continue
            kept.append(line)
        out.append(Page(p.doc, p.page_no, kept))
    return out, removed


def join_hyphenation(text: str) -> str:
    """修「跨行断词」：information-\nretrieval → informationretrieval 的坑，补回连字符本身。"""
    return re.sub(r"(?<=[A-Za-z])-\n(?=[a-z])", "-", text)


def load_document(path: str | Path) -> tuple[str, dict]:
    """一条龙：解析 → 去页眉页脚 → 拼全文。返回 (文本, 统计)。"""
    pages = parse_pages(path)
    clean, removed = strip_boilerplate(pages)
    text = "\n\n".join(p.text() for p in clean)
    text = join_hyphenation(text)
    stat = {
        "doc": Path(path).stem,
        "pages": len(pages),
        "raw_lines": sum(len(p.lines) for p in pages),
        "kept_lines": sum(len(p.lines) for p in clean),
        "chars": len(text),
        "removed_samples": removed[:6],
    }
    return text, stat


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:]:
        _, st = load_document(p)
        print(st)