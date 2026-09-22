from __future__ import annotations

import argparse
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
        *[str(value).strip() for value in current.get("excludeIdentities") or [] if str(value).strip()],
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
) -> dict[str, Any]:
    rules = merged_audit_rules(current_rules, historical_rules)
    rows = [
        mark_precontact_qualification(canonicalize_contact_fields(row), rules)
        for row in contact_payload.get("candidates") or []
        if isinstance(row, dict)
    ]
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--historical-strategy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-count", type=int, default=1000)
    args = parser.parse_args()

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
