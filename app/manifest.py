"""扫描 data/raw 下的 PDF，生成一份清单。"""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def human_size(num_bytes: int) -> str:
    """把字节数转成人类可读的大小，如 2.1 MB。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def collect_pdfs(folder: Path) -> list[tuple[Path, int]]:
    """返回 [(路径, 字节数), ...]，按字节数从大到小。"""
    if not folder.exists():
        raise FileNotFoundError(f"目录不存在：{folder}")

    found: list[tuple[Path, int]] = []
    for path in folder.glob("*.pdf"):
        found.append((path, path.stat().st_size))

    found.sort(key=lambda item: item[1], reverse=True)
    return found


def print_manifest(items: list[tuple[Path, int]]) -> None:
    """打印清单表格。"""
    total = sum(size for _, size in items)
    print(f"{'#':<3}{'file':<30}{'size':>10}{'share':>8}")
    print("-" * 51)
    for index, (path, size) in enumerate(items, start=1):
        ratio = size / total * 100 if total else 0.0
        print(f"{index:<3}{path.name:<30}{human_size(size):>10}{ratio:>7.1f}%")
    print("-" * 51)
    print(f"{len(items)} files, {human_size(total)} total")


def main() -> None:
    items = collect_pdfs(DATA_DIR)
    print_manifest(items)


if __name__ == "__main__":
    main()
