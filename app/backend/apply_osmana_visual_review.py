from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from osmana_creator_rules import evaluate_osmana_candidate


def compact(value: Any) -> str:
    return str(value or "").strip()


def decision_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        compact(row.get("identity") or row.get("buyin_uid")),
        compact(row.get("shop")),
        compact(row.get("nickname")),
    )


def apply_visual_decisions(
    candidates: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    by_identity = {
        decision_key(row)[0]: row
        for row in decisions
        if decision_key(row)[0]
    }
    by_name = {
        decision_key(row)[1:]: row
        for row in decisions
        if decision_key(row)[2]
    }
    reviewed: list[dict[str, Any]] = []
    for candidate in candidates:
        current = dict(candidate)
        identity, shop, nickname = decision_key(current)
        decision = by_identity.get(identity) or by_name.get((shop, nickname))
        if decision:
            approved = bool(decision.get("visual_persona_verified"))
            current["visual_persona_verified"] = approved
            current["visual_review_status"] = "approved" if approved else "rejected"
            current["visual_review_note"] = compact(decision.get("visual_review_note"))
            current["visual_reviewed_at"] = compact(decision.get("visual_reviewed_at")) or datetime.now().isoformat(timespec="seconds")
            for key in ("content_evidence_reviewed", "content_text_matched", "content_evidence"):
                if key in decision:
                    current[key] = decision[key]
        current["osmana_evaluation"] = evaluate_osmana_candidate(current, strategy)
        reviewed.append(current)
    return reviewed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    decisions_payload = json.loads(Path(args.decisions).resolve().read_text(encoding="utf-8"))
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    candidates = apply_visual_decisions(
        [row for row in payload.get("candidates") or [] if isinstance(row, dict)],
        [row for row in decisions_payload.get("decisions") or [] if isinstance(row, dict)],
        strategy,
    )
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        **payload,
        "status": "visual_review_applied",
        "source": str(source),
        "visual_reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "visual_approved_count": sum(1 for row in candidates if row.get("visual_persona_verified")),
        "visual_rejected_count": sum(1 for row in candidates if row.get("visual_review_status") == "rejected"),
        "strict_qualified_count": sum(1 for row in candidates if (row.get("osmana_evaluation") or {}).get("qualified")),
        "candidates": candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "visual_approved_count": sum(1 for row in candidates if row.get("visual_persona_verified")),
        "visual_rejected_count": sum(1 for row in candidates if row.get("visual_review_status") == "rejected"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
