from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contact_pipeline_contract import merge_contact_candidates


CONTACT_FIELD_NAMES = {
    "contact_visible", "contact_entry", "wechat", "phone", "email",
    "联系方式", "微信", "手机号", "邮箱",
    "buyin_public_intro", "buyin_public_intro_checked",
}


def contact_only_update(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if key == "identity"
        or key in CONTACT_FIELD_NAMES
        or key.startswith(("buyin_contact_", "cart_contact_", "ui_contact_"))
    }


def load_contact_highwater(output_dir: Path, source_payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [item for item in source_payload.get("candidates") or [] if isinstance(item, dict)]
    identities = {str(item.get("identity") or "").strip() for item in candidates}
    stable = output_dir / "aipr_contact_highwater.json"
    sources = [stable] if stable.exists() else sorted(
        output_dir.glob("aipr_creator_contacts_*.json"), key=lambda item: item.stat().st_mtime, reverse=True
    )[:1]
    for path in sources:
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            relevant = [
                contact_only_update(item) for item in previous.get("candidates") or []
                if isinstance(item, dict) and str(item.get("identity") or "").strip() in identities
            ]
            candidates = merge_contact_candidates(candidates, relevant)
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return {**source_payload, "candidate_count": len(candidates), "candidates": candidates}


def save_contact_highwater(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "aipr_contact_highwater.json"
    stable_payload = dict(payload)
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            candidates = merge_contact_candidates(
                [item for item in previous.get("candidates") or [] if isinstance(item, dict)],
                [item for item in payload.get("candidates") or [] if isinstance(item, dict)],
            )
            stable_payload = {**previous, **payload, "candidate_count": len(candidates), "candidates": candidates}
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(stable_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path
