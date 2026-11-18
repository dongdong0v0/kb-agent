"""manifest 模块的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.manifest import collect_pdfs, human_size


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (int(2.2 * 1024 * 1024), "2.2 MB"),
    ],
)
def test_human_size(num_bytes: int, expected: str) -> None:
    assert human_size(num_bytes) == expected


def test_collect_pdfs_sorted_desc(tmp_path: Path) -> None:
    (tmp_path / "small.pdf").write_bytes(b"x" * 100)
    (tmp_path / "big.pdf").write_bytes(b"x" * 300)
    (tmp_path / "ignore.txt").write_text("not a pdf")

    items = collect_pdfs(tmp_path)

    assert [p.name for p, _ in items] == ["big.pdf", "small.pdf"]
    assert [size for _, size in items] == [300, 100]


def test_collect_pdfs_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        collect_pdfs(tmp_path / "nope")
