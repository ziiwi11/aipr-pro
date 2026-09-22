from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def compact(value: Any) -> str:
    return str(value or "").strip()


def creator_key(row: dict[str, Any]) -> str:
    public = compact(row.get("douyin_id") or row.get("unique_id") or row.get("buyin_account_id")).lower()
    if public and not public.startswith("v2_"):
        return f"douyin:{public}"
    identity = compact(row.get("identity") or row.get("buyin_uid"))
    return f"identity:{identity}" if identity else ""


def merge_row(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    merged["source_keywords"] = list(dict.fromkeys([
        *(compact(item) for item in current.get("source_keywords") or [] if compact(item)),
        *(compact(item) for item in incoming.get("source_keywords") or [] if compact(item)),
    ]))
    for key, value in incoming.items():
        if key == "source_keywords":
            continue
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    return merged


def build_pending_queue(
    pools: list[dict[str, Any]],
    completed_payloads: list[dict[str, Any]],
    prior_delivery_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for payload in pools:
        for row in payload.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            identity = creator_key(row)
            if not identity:
                continue
            merged[identity] = merge_row(merged[identity], row) if identity in merged else dict(row)

    completed: set[str] = set()
    for payload in completed_payloads:
        for row in payload.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            if not row.get("buyin_product_evidence_reviewed") and not row.get("osmana_evidence_status"):
                continue
            identity = creator_key(row)
            if identity:
                completed.add(identity)

    prior_deliveries: set[str] = set()
    for payload in prior_delivery_payloads or []:
        for row in payload.get("candidates") or payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            identity = creator_key(row)
            if identity:
                prior_deliveries.add(identity)

    excluded = completed | prior_deliveries
    candidates = [row for identity, row in merged.items() if identity not in excluded]
    candidates.sort(key=lambda row: (compact(row.get("shop")), -int(row.get("video_sales_low") or 0), compact(row.get("nickname"))))
    return {
        "status": "ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "source_unique_count": len(merged),
        "completed_excluded_count": len(set(merged) & completed),
        "prior_delivery_excluded_count": len(set(merged) & prior_deliveries),
        "candidates": candidates,
    }


def load_payloads(paths: list[str]) -> list[dict[str, Any]]:
    return [json.loads(Path(path).resolve().read_text(encoding="utf-8")) for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", action="append", default=[], required=True)
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = build_pending_queue(
        load_payloads(args.pool),
        load_payloads(args.completed),
        load_payloads(args.exclude),
    )
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: result[key]
        for key in (
            "candidate_count",
            "source_unique_count",
            "completed_excluded_count",
            "prior_delivery_excluded_count",
        )
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
