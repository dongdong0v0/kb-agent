"""Prompt 迭代评测：同一批题，换 system prompt 版本，比成功率 / 尝试数 / 成本 / 输出质量。

用法：
    uv run python scripts/eval_prompt.py                 # 默认跑 v1 v2 v3 全对比
    uv run python scripts/eval_prompt.py --versions v1,v2
    uv run python scripts/eval_prompt.py --limit 10

为什么还要「质量」三项：
首轮实测三版成功率都是 100%、空字段都是 0，成功率根本分不出高下 —— 题目太简单、
schema 又强制了字段。于是补三个不依赖人工标注的代理指标：
- 引用忠实度：evidence 是不是原文子串（防止模型自己改写、编造证据）；
- 空话率：remediation 里有多少条是「加强管理」这类没法执行的废话；
- 措施条数：少于 1 条等于没给修复方案。
更严格的判定（severity 是否判对）需要人工 gold label，那是 W5 评测体系的事。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.llm import ChatClient  # noqa: E402
from app.prompts import PROMPTS, get as get_prompt  # noqa: E402
from app.structured import StructuredError, chat_json  # noqa: E402
from eval_json import PROMPTS as CASES, Finding  # noqa: E402

# 「正确但没用」的整改话术：命中即算空话，不算可执行措施
EMPTY_TALK = ("加强管理", "提高意识", "完善制度", "加强培训", "高度重视", "落实责任", "建立健全")


def judge(obj: Finding, prompt: str) -> dict:
    """三个不需要人工标注的质量代理指标。"""
    ev = re.sub(r"\s+", "", obj.evidence or "")
    src = re.sub(r"\s+", "", prompt)
    empty_talk = sum(1 for r in obj.remediation if any(w in r for w in EMPTY_TALK))
    return {
        "evidence_verbatim": bool(ev) and ev in src,
        "empty_talk": empty_talk,
        "remediation_count": len(obj.remediation),
        "empty_fields": sum(1 for v in obj.model_dump().values() if v in ("", [], None)),
    }


def run_case(version: str, prompt: str, *, attempts: int) -> dict:
    client = ChatClient(system_prompt=get_prompt(version))
    started = time.perf_counter()
    row = {"version": version, "prompt": prompt, "ok": False, "attempts": attempts,
           "latency_ms": 0, "tokens": 0, "cost": 0.0, "error": "",
           "evidence_verbatim": False, "empty_talk": 0, "remediation_count": 0, "empty_fields": 0}
    try:
        obj, tries = chat_json(client, prompt, Finding, attempts=attempts)
        row.update(ok=True, attempts=tries, **judge(obj, prompt))
    except StructuredError as exc:
        row["error"] = str(exc)[:160]
    row["latency_ms"] = int((time.perf_counter() - started) * 1000)
    row["tokens"] = client.total_tokens_used
    row["cost"] = round(client.total_cost, 6)
    return row


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    ok = [r for r in rows if r["ok"]]
    m = len(ok)
    return {
        "cases": n,
        "success": m,
        "success_rate": round(m / n, 4) if n else 0.0,
        "avg_attempts": round(sum(r["attempts"] for r in rows) / n, 2) if n else 0.0,
        "avg_latency_ms": int(sum(r["latency_ms"] for r in rows) / n) if n else 0,
        "total_tokens": sum(r["tokens"] for r in rows),
        "total_cost": round(sum(r["cost"] for r in rows), 6),
        "evidence_verbatim_rate": round(sum(r["evidence_verbatim"] for r in ok) / m, 4) if m else 0.0,
        "cases_with_empty_talk": sum(1 for r in ok if r["empty_talk"] > 0),
        "avg_remediations": round(sum(r["remediation_count"] for r in ok) / m, 2) if m else 0.0,
        "cases_with_empty_field": sum(1 for r in ok if r["empty_fields"] > 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Prompt 版本对比评测")
    ap.add_argument("--versions", default=",".join(PROMPTS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--out-dir", default="data/eval")
    args = ap.parse_args()

    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    cases = CASES[: args.limit] if args.limit else CASES
    settings = get_settings()
    print(f"模型 {settings.deepseek_model} · {len(versions)} 个版本 × {len(cases)} 题")

    all_rows, report = [], {}
    for version in versions:
        print(f"\n[{version}] {get_prompt(version)[:40].replace(chr(10), ' ')}…")
        rows = []
        for i, prompt in enumerate(cases, start=1):
            row = run_case(version, prompt, attempts=args.attempts)
            rows.append(row)
            all_rows.append(row)
            print(f"  {i:>2} {'OK' if row['ok'] else 'FAIL'} 尝试{row['attempts']} "
                  f"{row['latency_ms']:>4}ms 引用{int(row['evidence_verbatim'])} "
                  f"空话{row['empty_talk']} 措施{row['remediation_count']} {row['error'][:30]}")
        report[version] = summarize(rows)

    print("\n版本  成功率   尝试  耗时    引用忠实  含空话题  平均措施  tokens   花费")
    print("-" * 82)
    for version, s in report.items():
        print(f"{version:<5} {s['success']}/{s['cases']}={s['success_rate']:.0%}"
              f"  {s['avg_attempts']:>4}  {s['avg_latency_ms']:>5}ms"
              f"  {s['evidence_verbatim_rate']:>7.0%}  {s['cases_with_empty_talk']:>7}"
              f"  {s['avg_remediations']:>8}  {s['total_tokens']:>6}  ¥{s['total_cost']:.5f}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"prompt_compare_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.deepseek_model,
        "summary": report,
        "cases": all_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
