from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from realtime_creator_flow import RealtimeCreatorFlowStore, compact, is_terminal_state


def candidate_identity(row: dict[str, Any]) -> str:
    return compact(
        row.get("identity")
        or row.get("buyin_uid")
        or row.get("douyin_id")
        or row.get("主页身份ID")
    )


def migrate_candidate_rows(
    rows: Iterable[dict[str, Any]], flow_path: Path
) -> dict[str, int]:
    store = RealtimeCreatorFlowStore(Path(flow_path))
    migrated = 0
    skipped = 0
    invalid = 0
    for source in rows:
        if not isinstance(source, dict):
            invalid += 1
            continue
        identity = candidate_identity(source)
        if not identity:
            invalid += 1
            continue
        previous = store.get(identity)
        if previous:
            skipped += 1
            continue
        row = {
            **source,
            "identity": identity,
            "realtime_flow_state": "discovered",
            "realtime_flow_reason": "migrated_candidate_pending_review",
        }
        store.record(
            identity,
            "discovered",
            row,
            reason="migrated_candidate_pending_review",
        )
        migrated += 1
    return {
        "migrated_count": migrated,
        "skipped_count": skipped,
        "invalid_count": invalid,
        **store.summary(),
    }


def candidate_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("candidates", "rows", "records"):
        values = payload.get(key)
        if isinstance(values, list):
            if key == "records":
                return [
                    dict(record.get("row"))
                    for record in values
                    if isinstance(record, dict) and isinstance(record.get("row"), dict)
                ]
            return [row for row in values if isinstance(row, dict)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate a candidate pool into the per-creator realtime flow without treating contact visibility as plaintext."
    )
    parser.add_argument("source")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    source = Path(args.source).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    output_dir = Path(args.out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = migrate_candidate_rows(
        candidate_rows(payload), output_dir / "aipr_realtime_creator_flow.json"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
