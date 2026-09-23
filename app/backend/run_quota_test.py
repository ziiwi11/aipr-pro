#!/usr/bin/env python3
"""风控额度测试：连续揭示联系方式，记录每次结果

调用现有的 scrape_buyin_profile_contact_icons_cdp.py，
每轮揭示后分析结果，直到：
  - 连续 N 个失败（判定触发风控）
  - 或候选耗尽

产出：额度曲线、成功率、风控信号、时间间隔。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
PY = sys.executable

FAIL_STREAK_STOP = 3          # 连续失败阈值
ROUND_SIZE = 10               # 每轮揭示数量
DELAY_MS = 5000               # 揭示间隔


def emit(p: dict) -> None:
    print(json.dumps(p, ensure_ascii=False), flush=True)


def latest(pattern: str, d: Path) -> Path | None:
    files = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def read_candidates(path: Path) -> list[dict]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d.get("candidates") or []
    except Exception:
        return []


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True, help="测试目录")
    ap.add_argument("--rounds", type=int, default=6)
    args = ap.parse_args()

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    verified = latest("aipr_verified_creators_*.json", work)
    if not verified:
        emit({"status": "error", "message": "no verified creators file"})
        return 1

    timeline: list[dict] = []
    fail_streak = 0
    total_revealed = 0

    for rnd in range(1, args.rounds + 1):
        if fail_streak >= FAIL_STREAK_STOP:
            emit({"status": "stopped_by_fail_streak", "streak": fail_streak, "round": rnd})
            break

        src = latest("aipr_creator_contacts_*.json", work) or verified
        before = read_candidates(src)
        revealed_before = sum(1 for c in before if c.get("ui_contact_probe_status") == "revealed")

        started = datetime.now()
        cmd = [
            PY, str(BACKEND / "scrape_buyin_profile_contact_icons_cdp.py"),
            "--input", str(src),
            "--out-dir", str(work),
            "--shop-b", "http://127.0.0.1:9222?shop=B",
            "--limit", str(ROUND_SIZE),
            "--delay-ms", str(DELAY_MS),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        finished = datetime.now()

        out_file = latest("aipr_creator_contacts_*.json", work)
        after = read_candidates(out_file) if out_file else []
        revealed_after = sum(1 for c in after if c.get("ui_contact_probe_status") == "revealed")
        gained = revealed_after - revealed_before

        # 本轮失败者
        failed = [
            c for c in after
            if c.get("ui_contact_probe_status") in
            ("clicked_not_revealed", "rate_limited", "timeout", "exception")
        ]

        entry = {
            "round": rnd,
            "started": started.isoformat(timespec="seconds"),
            "finished": finished.isoformat(timespec="seconds"),
            "duration_sec": round((finished - started).total_seconds(), 1),
            "revealed_before": revealed_before,
            "revealed_after": revealed_after,
            "gained": gained,
            "fail_count": len(failed),
        }
        timeline.append(entry)

        if gained > 0:
            fail_streak = 0
            total_revealed = revealed_after
        else:
            fail_streak += 1

        emit({"status": "round_done", **entry, "fail_streak": fail_streak})

        # 检查额度信号
        if "次数已达上限" in (proc.stdout or ""):
            emit({"status": "quota_exhausted", "round": rnd})
            break
        for marker in ("请求过于频繁", "稍后再试", "访问频繁", "安全验证"):
            if marker in (proc.stdout or ""):
                emit({"status": "rate_limited", "marker": marker, "round": rnd})
                break

    report = {
        "tested_at": datetime.now().isoformat(timespec="seconds"),
        "work_dir": str(work),
        "rounds_run": len(timeline),
        "total_revealed": total_revealed,
        "final_fail_streak": fail_streak,
        "timeline": timeline,
    }
    out = work / "quota-test-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit({"status": "test_finished", "report": str(out), "total_revealed": total_revealed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
