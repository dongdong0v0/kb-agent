"""结构化输出成功率评测（G2 阶段门证据，可重复跑）。

用法：
    uv run python scripts/eval_json.py
    uv run python scripts/eval_json.py --min-rate 0.95      # 低于门槛返回退出码 1，可挂 CI
    uv run python scripts/eval_json.py --force-truncation   # 强制 max_tokens=20，专门压测重试路径

设计取舍：
1. 每题新建 ChatClient —— 独立样本，避免历史累积把 prompt_tokens 越滚越大；
2. 失败不吞 —— 记录异常文本，报告里能直接看到是哪类失败（截断 / schema 错）；
3. 结果落盘 JSON —— 证据要可复现、可比对，不能只活在终端里；
4. 退出码表达结论 —— 成功率不达标就返回 1，方便以后接 CI。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

# 允许直接 python scripts/eval_json.py 运行：把项目根加进 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.llm import ChatClient  # noqa: E402
from app.structured import StructuredError, chat_json  # noqa: E402


class Finding(BaseModel):
    """被测 schema：枚举 + 嵌套列表，比纯字符串字段更容易踩坑。"""

    control: str
    severity: Literal["高", "中", "低"]
    evidence: str
    remediation: list[str]


PROMPTS: list[str] = [
    "默认数据库密码仍是 admin/admin",
    "生产日志未集中存储，仅存本机",
    "所有运维人员共用 root 账号",
    "补丁滞后 90 天未更新",
    "核心库无异地备份",
    "SSH 对公网开放且允许密码登录",
    "MySQL 3306 直接暴露在公网",
    "无主机入侵检测，也未接入告警",
    "备份文件未加密就放对象存储",
    "全年无安全培训记录",
    "离职员工账号 30 天未回收",
    "内网横向无隔离，办公网可直达数据库",
    "未做最小权限，开发账号有 DDL 权限",
    "审计日志保留 7 天就覆盖",
    "证书过期未监控，靠用户报错才发现",
    "镜像来源不明，未做漏洞扫描",
    "密钥硬编码在代码仓库里",
    "无变更审批流程，直接改生产",
    "钓鱼演练从未做过",
    "应急响应无预案，出事靠临时拉群",
]


@dataclass
class CaseResult:
    idx: int
    ok: bool
    attempts: int
    latency_ms: int
    tokens: int
    cost: float
    chars: int
    error: str = ""
    prompt: str = ""


def run_case(idx: int, prompt: str, *, attempts: int, max_tokens: int | None) -> CaseResult:
    """跑一题：独立客户端 + 计时 + 记录用量。"""
    client = ChatClient(system_prompt="你是安全评审助手，输出严格按 Schema。")
    started = time.perf_counter()
    try:
        obj, tries = chat_json(client, prompt, Finding, attempts=attempts, max_tokens=max_tokens)
        ok, error, chars = True, "", len(obj.model_dump_json())
    except StructuredError as exc:
        ok, error, chars = False, str(exc)[:200], 0
    latency_ms = int((time.perf_counter() - started) * 1000)
    return CaseResult(
        idx=idx,
        ok=ok,
        attempts=tries if ok else attempts,
        latency_ms=latency_ms,
        tokens=client.total_tokens_used,
        cost=client.total_cost,
        chars=chars,
        error=error,
        prompt=prompt,
    )


def summarize(results: list[CaseResult]) -> dict:
    ok = [r for r in results if r.ok]
    total = len(results)
    return {
        "total": total,
        "success": len(ok),
        "success_rate": round(len(ok) / total, 4) if total else 0.0,
        "avg_attempts": round(sum(r.attempts for r in results) / total, 2) if total else 0.0,
        "avg_latency_ms": int(sum(r.latency_ms for r in results) / total) if total else 0,
        "retried_cases": sum(1 for r in results if r.attempts > 1),
        "total_tokens": sum(r.tokens for r in results),
        "total_cost": round(sum(r.cost for r in results), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="结构化输出成功率评测")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0 = 全部）")
    parser.add_argument("--attempts", type=int, default=3, help="每题最多尝试次数")
    parser.add_argument("--min-rate", type=float, default=0.95, help="成功率门槛，低于则退出码 1")
    parser.add_argument("--force-truncation", action="store_true", help="强制 max_tokens=20 压测重试")
    parser.add_argument("--out-dir", default="data/eval", help="报告输出目录")
    args = parser.parse_args()

    prompts = PROMPTS[: args.limit] if args.limit else PROMPTS
    max_tokens = 20 if args.force_truncation else None
    settings = get_settings()

    print(f"模型 {settings.deepseek_model} · 题目 {len(prompts)} · 每题最多 {args.attempts} 次"
          + (" · 强制截断模式" if max_tokens else ""))
    print(f"{'#':>2}  {'结果':<4} {'尝试':>2} {'耗时':>6} {'chars':>5}  错误摘要")
    print("-" * 78)

    results: list[CaseResult] = []
    for i, prompt in enumerate(prompts, start=1):
        r = run_case(i, prompt, attempts=args.attempts, max_tokens=max_tokens)
        results.append(r)
        flag = "OK" if r.ok else "FAIL"
        print(f"{r.idx:>2}  {flag:<4} {r.attempts:>2} {r.latency_ms:>5}ms {r.chars:>5}  {r.error[:40]}")

    stats = summarize(results)
    print("-" * 78)
    print(
        f"成功率 {stats['success']}/{stats['total']} = {stats['success_rate']:.0%}"
        f" | 平均尝试 {stats['avg_attempts']}"
        f" | 平均耗时 {stats['avg_latency_ms']}ms"
        f" | 重试过的题 {stats['retried_cases']}"
    )
    print(f"总 tokens {stats['total_tokens']} | 总花费 ¥{stats['total_cost']:.6f}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"json_success_{stamp}.json"
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.deepseek_model,
        "attempts_policy": args.attempts,
        "forced_max_tokens": max_tokens,
        "summary": stats,
        "cases": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入 {out_path}")

    if stats["success_rate"] < args.min_rate:
        print(f"未达标：{stats['success_rate']:.0%} < {args.min_rate:.0%}")
        return 1
    print(f"达标：{stats['success_rate']:.0%} ≥ {args.min_rate:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
