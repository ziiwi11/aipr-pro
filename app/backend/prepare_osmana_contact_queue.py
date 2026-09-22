from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_contact_queue(
    candidates: list[dict[str, Any]],
    threshold: int = 10000,
    require_visual: bool = True,
) -> list[dict[str, Any]]:
    eligible = [
        row for row in candidates
        if row.get("content_evidence_reviewed")
        and (row.get("visual_persona_verified") or not require_visual)
        and int((row.get("osmana_evaluation") or {}).get("underwear_product_sales_low") or 0) > threshold
    ]
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in eligible:
        public = str(row.get("douyin_id") or row.get("douyin_account_id") or row.get("douyin_homepage") or "").strip().lower()
        key = f"douyin:{public}" if public else f"identity:{str(row.get('identity') or row.get('buyin_uid') or '').strip()}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=int, default=10000)
    parser.add_argument("--allow-pending-visual", action="store_true")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidates = build_contact_queue(
        [row for row in payload.get("candidates") or [] if isinstance(row, dict)],
        args.threshold,
        require_visual=not args.allow_pending_visual,
    )
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "status": "ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "candidate_count": len(candidates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
