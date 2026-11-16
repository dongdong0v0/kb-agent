"""第一个模块：验证环境能跑通。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def describe_environment() -> dict[str, str]:
    import platform
    import sys

    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "project_root": str(PROJECT_ROOT),
        "cwd": str(Path.cwd()),
    }


def main() -> None:
    info = describe_environment()
    print("环境自检")
    print("-" * 40)
    for key, value in info.items():
        print(f"{key:<14}{value}")


if __name__ == "__main__":
    main()
