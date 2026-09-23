from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from console_io import configure_utf8_stdout
from creator_delivery_contract import build_delivery, select_delivery_candidates


configure_utf8_stdout()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def write_standard_workbook(rows: list[dict[str, Any]], target: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "最终达人名单"
    headers = list(rows[0].keys()) if rows else ["序号", "达人昵称", "推荐结论", "明文联系方式", "微信", "手机号"]
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="167D68")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        values = [str(cell.value or "") for cell in column[:80]]
        width = min(42, max(10, max((len(value) for value in values), default=10) + 2))
        sheet.column_dimensions[column[0].column_letter].width = width
        for cell in column:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    workbook.save(target)


def merge_robot_queue(target: Path, records: list[dict[str, Any]]) -> None:
    existing: list[dict[str, Any]] = []
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    def record_key(row: dict[str, Any]) -> tuple[str, str]:
        return (
            str((row.get("task") or {}).get("id") or row.get("taskId") or ""),
            str((row.get("creator") or {}).get("id") or row.get("creatorId") or ""),
        )

    merged = {record_key(row): row for row in existing}
    for row in records:
        merged[record_key(row)] = row
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merged.values()), encoding="utf-8")


def _manifest_roi(roi: Any) -> dict[str, Any]:
    """从 ROI 报告中提取交接清单需要的摘要字段。"""
    if not isinstance(roi, dict) or roi.get("error"):
        return {"available": False, "reason": (roi or {}).get("error", "not_computed")}
    funnel = roi.get("funnel") or {}
    contacts = roi.get("contacts") or {}
    return {
        "available": True,
        "funnel": {
            "candidates": funnel.get("candidates", 0),
            "verified": funnel.get("verified", 0),
            "qualified": funnel.get("qualified", 0),
            "revealed": funnel.get("revealed", 0),
            "delivered": funnel.get("delivered", 0),
        },
        "rates": funnel.get("rates") or {},
        "contacts": {
            "withContact": contacts.get("with_contact", 0),
            "phone": contacts.get("phone", 0),
            "wechat": contacts.get("wechat", 0),
            "contactRate": contacts.get("contact_rate", "0.0"),
        },
        "risk": roi.get("risk") or {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--task-id", default="brand-task")
    parser.add_argument("--task-name", default="品牌达人任务")
    parser.add_argument("--original-workbook", default="")
    parser.add_argument("--robot-queue", default="")
    parser.add_argument("--contacts-only", action="store_true")
    parser.add_argument("--require-strict-highwater", action="store_true")
    # ROI 看板参数（可选，用于成本与速率估算）
    parser.add_argument("--budget", type=float, default=0, help="任务预算（用于成本估算）")
    parser.add_argument("--cost-per-reveal", type=float, default=0, help="单次联系方式揭示的估算成本")
    parser.add_argument("--elapsed-minutes", type=float, default=0, help="本次采集耗时（用于速率）")
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    rules = {
        **strategy,
        "threshold": strategy.get("threshold", 78),
        "exclusions": strategy.get("exclusions") or [],
    }
    target_count = max(1, int(strategy.get("targetCount") or 1))
    if args.require_strict_highwater:
        audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
        strict_ready = (
            payload.get("status") == "complete"
            and payload.get("contact_dedup_mode") == "strict-any-plaintext-value"
            and int(payload.get("strict_selected_count") or 0) >= target_count
            and audit.get("identity_unique") is True
            and audit.get("contact_values_unique") is True
            and int(audit.get("cross_round_contact_overlap") or 0) == 0
        )
        if not strict_ready:
            emit({
                "status": "delivery_incomplete",
                "message": "严格高水位尚未达到交付条件",
                "qualified_count": int(payload.get("strict_selected_count") or 0),
                "target_count": target_count,
                "strict_audit": audit,
            })
            raise SystemExit(7)
    qualified = select_delivery_candidates(payload.get("candidates") or [], rules, target_count)
    if len(qualified) < target_count:
        emit({
            "status": "delivery_incomplete",
            "message": f"最终合规且有明文联系方式的达人不足：{len(qualified)}/{target_count}",
            "qualified_count": len(qualified),
            "target_count": target_count,
        })
        raise SystemExit(7)
    delivery = build_delivery(qualified, rules, args.task_id)
    delivery["source"] = str(source)
    delivery["strategy"] = strategy
    delivery["strict_selected_count"] = int(payload.get("strict_selected_count") or len(qualified))
    delivery["strict_audit"] = payload.get("audit") or {}
    delivery["delivery_mode"] = "contacts-only" if args.contacts_only else "robot-handoff"

    # ROI 转化看板：对完整候选集（含未入选）计算漏斗，
    # 这样能看到从候选到交付的真实转化率，而不只是最终名单的计数。
    try:
        from roi_dashboard import build_roi
        all_candidates = payload.get("candidates") or []
        elapsed = float(getattr(args, "elapsed_minutes", 0) or 0)
        delivery["roi"] = build_roi(all_candidates, {
            "id": args.task_id,
            "name": args.task_name,
            "budget": float(getattr(args, "budget", 0) or 0),
            "cost_per_reveal": float(getattr(args, "cost_per_reveal", 0) or 0),
            "elapsed_minutes": elapsed,
        })
    except Exception as exc:  # ROI 失败不应阻断交付
        delivery["roi"] = {"error": str(exc)[:200]}

    robot_records = [] if args.contacts_only else list(delivery.get("robot_queue") or [])
    if args.contacts_only:
        delivery["robot_queue"] = []
        delivery["robot_queue_count"] = 0

    output_dir = Path(args.out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    delivery_path = output_dir / f"aipr_final_delivery_{stamp}.json"
    xlsx_path = output_dir / f"{args.task_name}_最终达人名单_{stamp}.xlsx"
    queue_path = None if args.contacts_only else output_dir / f"{args.task_name}_机器人队列_{stamp}.ndjson"
    batch_path = None if args.contacts_only else output_dir / f"{args.task_name}_机器人批量包_{stamp}.json"
    manifest_path = output_dir / f"{args.task_name}_交接清单_{stamp}.json"
    delivery_path.write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding="utf-8")
    write_standard_workbook(delivery["rows"], xlsx_path)
    if queue_path and batch_path:
        queue_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in robot_records), encoding="utf-8")
        batch_path.write_text(json.dumps({
            "schemaVersion": "aipr.robot.batch.v1",
            "contractVersion": delivery["robot_contract_version"],
            "createdAt": delivery["created_at"],
            "task": {"id": args.task_id, "name": args.task_name},
            "dryRunOnly": True,
            "records": robot_records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.robot_queue and not args.contacts_only:
        merge_robot_queue(Path(args.robot_queue).resolve(), robot_records)

    original_xlsx = ""
    original = Path(args.original_workbook).resolve() if args.original_workbook else None
    if original and original.exists():
        before = set(output_dir.glob("*.xlsx"))
        exporter = Path(__file__).with_name("export_original_format_with_contacts.py")
        process = subprocess.run([
            sys.executable, str(exporter),
            "--source", str(original),
            "--delivery", str(delivery_path),
            "--out-dir", str(output_dir),
            "--task-name", args.task_name,
        ], text=True, encoding="utf-8", errors="replace", capture_output=True)
        if process.returncode:
            emit({"status": "original_export_error", "message": process.stderr[-800:]})
        else:
            created = sorted(set(output_dir.glob("*.xlsx")) - before, key=lambda path: path.stat().st_mtime, reverse=True)
            original_xlsx = str(created[0]) if created else ""

    artifacts = {
        "finalJson": str(delivery_path),
        "standardXlsx": str(xlsx_path),
        "originalXlsx": original_xlsx,
        "robotNdjson": str(queue_path) if queue_path else "",
        "robotBatchJson": str(batch_path) if batch_path else "",
        "handoffManifest": str(manifest_path),
    }
    delivery["artifacts"] = artifacts
    delivery_path.write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "schemaVersion": "aipr.delivery.handoff.v1",
        "createdAt": delivery["created_at"],
        "task": {"id": args.task_id, "name": args.task_name},
        "outputDirectory": str(output_dir),
        "summary": {
            "candidateCount": delivery["candidate_count"],
            "recommendedCount": delivery["recommended_count"],
            "plainContactCount": delivery["plain_contact_count"],
            "wechatCount": delivery["wechat_contact_count"],
            "phoneCount": delivery["phone_contact_count"],
            "robotRecordCount": len(robot_records),
        },
        # ROI 摘要：交付方最关心的转化率与成本
        "roi": _manifest_roi(delivery.get("roi")),
        "robot": {
            "contractVersion": delivery["robot_contract_version"],
            "modes": [] if args.contacts_only else ["ndjson", "batch-json", "ipc"],
            "dryRunOnly": True,
            "realMessagesSent": 0,
        },
        "artifacts": artifacts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    emit({
        "status": "delivery_ready",
        "output": str(delivery_path),
        "xlsx": str(xlsx_path),
        "original_xlsx": original_xlsx,
        "robot_queue": str(queue_path) if queue_path else "",
        "robot_batch_json": str(batch_path) if batch_path else "",
        "handoff_manifest": str(manifest_path),
        "candidate_count": delivery["candidate_count"],
        "recommended_count": delivery["recommended_count"],
        "plain_contact_count": delivery["plain_contact_count"],
        "wechat_contact_count": delivery["wechat_contact_count"],
        "phone_contact_count": delivery["phone_contact_count"],
        "robot_queue_count": len(robot_records),
    })


if __name__ == "__main__":
    main()
