from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from contact_pipeline_contract import contact_totals, merge_contact_candidates
from osmana_creator_rules import evaluate_osmana_candidate


def compact(value: Any) -> str:
    return str(value or "").strip()


def stable_creator_key(row: dict[str, Any]) -> str:
    public = compact(row.get("douyin_id") or row.get("douyin_account_id") or row.get("douyin_homepage")).lower()
    if public:
        return f"douyin:{public}"
    return f"identity:{compact(row.get('identity') or row.get('buyin_uid'))}"


def merge_nonempty(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in incoming.items() if value not in (None, "", [], {})}
    return {**current, **clean}


def build_final_pool(
    payloads: list[dict[str, Any]],
    strategy: dict[str, Any],
    target_count: int,
) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    for payload in payloads:
        merged = merge_contact_candidates(
            merged,
            [row for row in payload.get("candidates") or [] if isinstance(row, dict)],
        )
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in merged:
        key = stable_creator_key(row)
        if key not in deduped:
            order.append(key)
            deduped[key] = {}
        deduped[key] = merge_nonempty(deduped[key], row)
    merged = [deduped[key] for key in order]
    evaluated = [
        {**row, "osmana_evaluation": evaluate_osmana_candidate(row, strategy)}
        for row in merged
    ]
    qualified = [row for row in evaluated if row["osmana_evaluation"].get("qualified")]
    qualified.sort(key=lambda row: (
        -int((row.get("osmana_evaluation") or {}).get("underwear_product_sales_low") or 0),
        -int((row.get("osmana_evaluation") or {}).get("level") or 0),
        str(row.get("nickname") or ""),
    ))
    selected = qualified[:target_count]
    totals = contact_totals(selected)
    return {
        "status": "complete" if len(selected) >= target_count else "incomplete",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_count": target_count,
        "unique_candidate_count": len(merged),
        "qualified_count": len(qualified),
        "selected_count": len(selected),
        "remaining_count": max(0, target_count - len(selected)),
        "plain_contact_count": totals["plain"],
        "wechat_contact_count": totals["wechat"],
        "phone_contact_count": totals["phone"],
        "candidates": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--target", type=int, default=500)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payloads = [json.loads(Path(path).resolve().read_text(encoding="utf-8")) for path in args.source]
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    result = build_final_pool(payloads, strategy, args.target)
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "target_count", "unique_candidate_count", "qualified_count",
        "selected_count", "remaining_count", "plain_contact_count", "wechat_contact_count", "phone_contact_count",
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
