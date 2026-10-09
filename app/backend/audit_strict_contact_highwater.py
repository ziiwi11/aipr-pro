from __future__ import annotations

import hashlib
import argparse
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from atomic_json_io import atomic_write_json
from console_io import configure_utf8_stdout
from creator_delivery_contract import (
    canonicalize_contact_fields,
    contact_identity_values,
    creator_identity_values,
    mark_precontact_qualification,
    normalize_contact_value,
    select_delivery_candidates,
)


configure_utf8_stdout()


def merged_audit_rules(current: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    rules = dict(current)
    rules["excludeContacts"] = list(dict.fromkeys([
        *[str(value).strip() for value in historical.get("excludeContacts") or [] if str(value).strip()],
        *[str(value).strip() for value in current.get("excludeContacts") or [] if str(value).strip()],
    ]))
    rules["excludeIdentities"] = list(dict.fromkeys([
        *[str(value).strip() for value in historical.get("excludeIdentities") or [] if str(value).strip()],
        *[str(value).strip() for value in current.get("deliveryExcludeIdentities", current.get("excludeIdentities")) or [] if str(value).strip()],
    ]))
    rules["contactDedupMode"] = "strict-any-plaintext-value"
    return rules


def _assert_strict_invariants(selected: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    seen_identities: set[str] = set()
    seen_contacts = {
        normalized
        for value in rules.get("excludeContacts") or []
        if (normalized := normalize_contact_value(value))
    }
    initial_contact_count = len(seen_contacts)
    for index, row in enumerate(selected):
        identities = creator_identity_values(row) or {f"row:{index}"}
        contacts = contact_identity_values(row)
        if identities & seen_identities:
            raise ValueError("strict_identity_duplicate_detected")
        if not contacts:
            raise ValueError("strict_candidate_missing_plain_contact")
        if contacts & seen_contacts:
            raise ValueError("strict_contact_duplicate_detected")
        seen_identities.update(identities)
        seen_contacts.update(contacts)
    return {
        "identity_unique": True,
        "contact_values_unique": True,
        "cross_round_contact_overlap": 0,
        "historical_contact_exclusion_count": initial_contact_count,
        "selected_contact_value_count": len(seen_contacts) - initial_contact_count,
    }


def build_strict_contact_highwater(
    contact_payload: dict[str, Any],
    current_rules: dict[str, Any],
    historical_rules: dict[str, Any],
    target_count: int = 1000,
    progress: Any = None,
) -> dict[str, Any]:
    rules = merged_audit_rules(current_rules, historical_rules)
    from contact_corrections import read_corrections, apply_corrections
    corrections = read_corrections(os.environ.get("AIPR_CONTACT_CORRECTIONS", ""), os.environ.get("AIPR_TASK_ID", ""))
    corrected_rows = apply_corrections(contact_payload.get("candidates") or [], corrections)
    source_rows = [row for row in corrected_rows if isinstance(row, dict)]
    rows = []
    def notify(done: int) -> None:
        if progress:
            progress({"status": "saved_list_audit_progress", "completed": done,
                      "total": len(source_rows),
                      "message": f"正在核对已保存名单及内容判断 {done}/{len(source_rows)}；尚未开始新增采集"})
    notify(0)
    for index, row in enumerate(source_rows, 1):
        rows.append(mark_precontact_qualification(canonicalize_contact_fields(row), rules))
        if index % 25 == 0 or index == len(source_rows):
            notify(index)
    selected = select_delivery_candidates(rows, rules, target_count)
    audit = _assert_strict_invariants(selected, rules)
    rows_with_plaintext = sum(bool(contact_identity_values(row)) for row in rows)
    return {
        "status": "complete" if len(selected) >= target_count else "incomplete",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target_count": target_count,
        "source_candidate_count": len(rows),
        "rows_with_plaintext": rows_with_plaintext,
        "strict_selected_count": len(selected),
        "candidate_count": len(selected),
        "contact_dedup_mode": "strict-any-plaintext-value",
        "audit": audit,
        "strategy": rules,
        "candidates": selected,
    }


def reaudit_saved_task(task_dir: Path, current_rules: dict[str, Any], progress=None, baseline_path: Path | None = None) -> dict[str, Any]:
    """Recheck saved evidence locally; never collect or replace invalid judgments."""
    root = Path(task_dir)
    strict_path = root / "aipr_strict_contact_highwater.json"
    previous = json.loads(strict_path.read_text(encoding="utf-8"))
    if not isinstance(previous, dict) or not isinstance(previous.get("candidates"), list):
        raise ValueError("saved_audit_previous_invalid")
    baseline = None
    baseline_rows = []
    if baseline_path:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        baseline_rows = baseline.get("candidates")
        if not isinstance(baseline_rows, list) or not baseline_rows:
            raise ValueError("saved_audit_baseline_invalid")
        if baseline.get("strategy", {}).get("brief") != current_rules.get("brief"):
            raise ValueError("saved_audit_baseline_brief_changed: 手卡已变更，不能沿用原名单做本次恢复")
    # Accepted historical identities own their contacts before new pool rows.
    # They still pass the full current evidence and admission gates.
    rows = list(baseline_rows) + list(previous["candidates"])
    for name, key in (("aipr_contact_highwater.json", "candidates"),
                      ("aipr_realtime_creator_flow.json", "records")):
        source = root / name
        if not source.exists():
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
            raise ValueError("saved_audit_source_invalid: " + name)
        if key == "records":
            rows.extend(record["row"] for record in payload[key]
                        if isinstance(record, dict) and isinstance(record.get("row"), dict))
        else:
            rows.extend(payload[key])
    saved_only = os.environ.get("AIPR_JEV_SAVED_ONLY")
    os.environ["AIPR_JEV_SAVED_ONLY"] = "1"
    try:
        result = build_strict_contact_highwater(
            {"candidates": rows}, current_rules, {},
            max(1, int(current_rules.get("deliveryTargetCount") or current_rules.get("targetCount") or 1000)), progress)
    finally:
        if saved_only is None:
            os.environ.pop("AIPR_JEV_SAVED_ONLY", None)
        else:
            os.environ["AIPR_JEV_SAVED_ONLY"] = saved_only
    selected_ids = set().union(*(creator_identity_values(row) for row in result.get("candidates") or []))
    removed = sum(not (creator_identity_values(row) & selected_ids) for row in previous["candidates"])
    baseline_missing = sum(not (creator_identity_values(row) & selected_ids) for row in baseline_rows)
    if removed or baseline_missing:
        preview = root / "aipr_saved_list_audit_pending_review.json"
        atomic_write_json(preview, {**result, "removed_previous_count": removed,
            "baseline_missing_count": baseline_missing, "requires_review": True,
            "review_context": {"previous_sha256": hashlib.sha256(strict_path.read_bytes()).hexdigest(),
                "rules_sha256": rules_fingerprint(current_rules),
                "baseline_path": str(baseline_path or ""),
                "baseline_sha256": hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest() if baseline_path else ""}})
        raise ValueError(f"saved_audit_requires_review: {removed} 位原正式达人将被排除；已保存建议名单，原正式名单未替换")
    backup = root / ("aipr_strict_before_saved_audit_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
    atomic_write_json(backup, previous)
    atomic_write_json(strict_path, result)
    result["previous_snapshot"] = str(backup)
    return result


def rules_fingerprint(rules):
    return hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def apply_pending_saved_audit(task_dir: Path, rules: dict[str, Any]):
    root = Path(task_dir)
    strict_path = root / "aipr_strict_contact_highwater.json"
    pending = json.loads((root / "aipr_saved_list_audit_pending_review.json").read_text(encoding="utf-8"))
    context = pending.get("review_context") or {}
    if (context.get("previous_sha256") != hashlib.sha256(strict_path.read_bytes()).hexdigest()
            or context.get("rules_sha256") != rules_fingerprint(rules)):
        raise ValueError("saved_audit_review_expired: 名单或规则已变化，请重新核对")
    if pending.get("baseline_missing_count"):
        raise ValueError("saved_audit_baseline_not_preserved: 原往期名单仍有差异，不能应用")
    baseline_path = context.get("baseline_path")
    if baseline_path and hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest() != context.get("baseline_sha256"):
        raise ValueError("saved_audit_baseline_changed")
    saved_only = os.environ.get("AIPR_JEV_SAVED_ONLY")
    os.environ["AIPR_JEV_SAVED_ONLY"] = "1"
    try:
        checked = build_strict_contact_highwater(pending, rules, {}, max(1, len(pending.get("candidates") or [])))
    finally:
        if saved_only is None: os.environ.pop("AIPR_JEV_SAVED_ONLY", None)
        else: os.environ["AIPR_JEV_SAVED_ONLY"] = saved_only
    if len(checked["candidates"]) != len(pending.get("candidates") or []):
        raise ValueError("saved_audit_judgment_changed: 已保存判断不再有效，原名单未替换")
    if baseline_path:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))["candidates"]
        selected_ids = set().union(*(creator_identity_values(row) for row in checked["candidates"]))
        if any(not creator_identity_values(row) & selected_ids for row in baseline):
            raise ValueError("saved_audit_baseline_not_preserved")
    previous = json.loads(strict_path.read_text(encoding="utf-8"))
    backup = root / ("aipr_strict_before_review_apply_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
    atomic_write_json(backup, previous)
    atomic_write_json(strict_path, checked)
    return {**checked, "previous_snapshot": str(backup)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--saved-task-dir")
    parser.add_argument("--batch-baseline")
    parser.add_argument("--apply-pending", action="store_true")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--historical-strategy")
    parser.add_argument("--output")
    parser.add_argument("--target-count", type=int, default=1000)
    args = parser.parse_args()

    if args.saved_task_dir:
        rules = json.loads(Path(args.strategy).read_text(encoding="utf-8"))
        result = apply_pending_saved_audit(Path(args.saved_task_dir), rules) if args.apply_pending else reaudit_saved_task(
            Path(args.saved_task_dir), rules,
            lambda event: print(json.dumps(event, ensure_ascii=False), flush=True),
            Path(args.batch_baseline) if args.batch_baseline else None)
        print(json.dumps({"status": "saved_list_audit_finished",
            "strict_selected_count": result["strict_selected_count"],
            "previous_snapshot": result["previous_snapshot"],
            "message": "已按当前内容规则核对保存名单，未新增采集、模型调用或发送"}, ensure_ascii=False), flush=True)
        return
    if not all((args.input, args.historical_strategy, args.output)):
        parser.error("--input, --historical-strategy and --output are required for input audit")
    contact_payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    current_rules = json.loads(Path(args.strategy).read_text(encoding="utf-8"))
    historical_rules = json.loads(Path(args.historical_strategy).read_text(encoding="utf-8"))
    result = build_strict_contact_highwater(
        contact_payload,
        current_rules,
        historical_rules,
        max(1, args.target_count),
    )
    output = Path(args.output)
    atomic_write_json(output, result)
    print(json.dumps({
        "status": "strict_contact_audit_finished",
        "output": str(output),
        "target_count": result["target_count"],
        "rows_with_plaintext": result["rows_with_plaintext"],
        "strict_selected_count": result["strict_selected_count"],
        "complete": result["status"] == "complete",
        "audit": result["audit"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
