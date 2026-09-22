from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from atomic_json_io import atomic_write_json


PROCESSING_STATES = (
    "discovered",
    "identity_unique",
    "evidence_reviewing",
    "suitable",
    "contact_revealing",
    "plaintext_unique",
    "listed",
)
TERMINAL_STATES = {
    "listed",
    "duplicate_identity",
    "unsuitable",
    "insufficient_evidence",
    "not_authorized",
    "not_available",
    "duplicate_contact",
    "error",
}


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _unmasked(value: Any) -> str:
    text = compact(value)
    if not text or "*" in text or "•" in text or "隐藏" in text or "未授权" in text:
        return ""
    return text


def has_authorized_plaintext(row: dict[str, Any]) -> bool:
    phone = _unmasked(
        row.get("buyin_contact_phone")
        or row.get("cart_contact_phone")
        or row.get("phone")
        or row.get("手机号")
    )
    if phone:
        digits = re.sub(r"\D", "", phone)
        if 7 <= len(digits) <= 15:
            return True
    wechat = _unmasked(
        row.get("buyin_contact_wechat")
        or row.get("cart_contact_wechat")
        or row.get("wechat")
        or row.get("微信")
    )
    return bool(wechat and len(wechat) >= 3)


def is_terminal_state(state: str) -> bool:
    return str(state or "").strip() in TERMINAL_STATES


class RealtimeCreatorFlowStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return
        for record in payload.get("records") or []:
            if not isinstance(record, dict):
                continue
            identity = compact(record.get("identity"))
            if identity:
                self._records[identity] = dict(record)

    def _save(self) -> None:
        payload = {
            "status": "ready",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": self.summary(),
            "records": list(self._records.values()),
        }
        atomic_write_json(self.path, payload)

    def record(
        self,
        identity: str,
        state: str,
        row: dict[str, Any],
        reason: str = "",
    ) -> dict[str, Any]:
        identity = compact(identity)
        state = compact(state)
        if not identity:
            raise ValueError("missing_creator_identity")
        if state not in set(PROCESSING_STATES) | TERMINAL_STATES:
            raise ValueError(f"unknown_creator_state:{state}")
        previous = self._records.get(identity)
        if previous and is_terminal_state(previous.get("state")) and previous.get("state") != state:
            raise ValueError("terminal_state_transition")
        first_seen = (previous or {}).get("first_seen_at") or datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            **(previous or {}),
            "identity": identity,
            "state": state,
            "reason": str(reason or "").strip(),
            "first_seen_at": first_seen,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "row": dict(row),
        }
        self._records[identity] = record
        self._save()
        return dict(record)

    def get(self, identity: str) -> dict[str, Any] | None:
        record = self._records.get(compact(identity))
        return dict(record) if record else None

    def rows(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records.values()]

    def reset_for_retry(self, identities: list[str], reason: str) -> int:
        reset = 0
        for raw_identity in identities:
            identity = compact(raw_identity)
            previous = self._records.get(identity)
            if not previous:
                continue
            row = dict(previous.get("row") or {})
            for key in (
                "content_evidence_reviewed", "content_evidence", "evidence_status",
                "evidence_error", "evidence_gate", "evidence_contract_version",
                "realtime_flow_state", "realtime_flow_reason", "precontact_qualified",
                "precontact_reason",
            ):
                row.pop(key, None)
            row.update({
                "identity": identity,
                "realtime_flow_state": "discovered",
                "realtime_flow_reason": str(reason or "").strip(),
            })
            self._records[identity] = {
                **previous,
                "state": "discovered",
                "reason": str(reason or "").strip(),
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "row": row,
            }
            reset += 1
        if reset:
            self._save()
        return reset

    def summary(self) -> dict[str, int]:
        records = list(self._records.values())
        states = [str(record.get("state") or "") for record in records]
        suitable_states = {"suitable", "contact_revealing", "plaintext_unique", "listed"}
        plaintext_states = {"plaintext_unique", "listed"}
        return {
            "discovered_count": len(records),
            "suitable_count": sum(state in suitable_states for state in states),
            "contact_revealing_count": sum(state == "contact_revealing" for state in states),
            "plaintext_count": sum(state in plaintext_states for state in states),
            "listed_count": sum(state == "listed" for state in states),
            "terminal_count": sum(is_terminal_state(state) for state in states),
        }
