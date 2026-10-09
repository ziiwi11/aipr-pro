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
    "retry_pending",
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
    if wechat and len(wechat) >= 3:
        return True
    email = _unmasked(
        row.get("buyin_contact_email")
        or row.get("cart_contact_email")
        or row.get("email")
        or row.get("邮箱")
    )
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email))


def is_terminal_state(state: str) -> bool:
    return str(state or "").strip() in TERMINAL_STATES


class RealtimeCreatorFlowStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        payload = None
        for source in (self.path, backup):
            if not source.exists():
                continue
            try:
                loaded = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict) or not isinstance(loaded.get("records"), list):
                    raise ValueError("invalid_flow_checkpoint")
                payload = loaded
                break
            except (OSError, ValueError, TypeError):
                continue
        if payload is None:
            if self.path.exists() or backup.exists():
                raise ValueError("flow_checkpoint_and_backup_unreadable: 流程检查点及备份无法读取，原文件已保留")
            return
        migrated = False
        for record in payload.get("records") or []:
            if not isinstance(record, dict):
                continue
            identity = compact(record.get("identity"))
            if identity:
                if (record.get("state") == "unsuitable" and record.get("reason") == "抖音主页或近期内容证据尚未完成复核"):
                    record = {**record, "state": "evidence_reviewing",
                              "row": {**(record.get("row") or {}), "realtime_flow_state": "evidence_reviewing",
                                      "precontact_decision": "待内容复核"}}
                    migrated = True
                row = record.get("row") or {}
                if (record.get("state") == "insufficient_evidence"
                        and row.get("evidence_status") == "error"
                        and "page crashed" in str(row.get("evidence_error", "")).lower()):
                    record = {**record, "state": "retry_pending", "reason": row["evidence_error"],
                              "row": {**row, "realtime_flow_state": "retry_pending",
                                      "realtime_flow_reason": row["evidence_error"]}}
                    migrated = True
                self._records[identity] = dict(record)
        if migrated:
            self._save()

    def _save(self) -> None:
        payload = {
            "status": "ready",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": self.summary(),
            "records": list(self._records.values()),
        }
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        if self.path.exists():
            try:
                previous = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(previous, dict) and isinstance(previous.get("records"), list):
                    atomic_write_json(backup, previous)
            except (OSError, ValueError, TypeError):
                pass
        atomic_write_json(self.path, payload)
        if not backup.exists():
            atomic_write_json(backup, payload)

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
        recover_misclassified_cooldown = (
            previous and previous.get("state") == "error"
            and str(previous.get("reason") or "").startswith("contact_cooldown_active:")
            and state == "contact_revealing" and reason == "rate_limited"
        )
        if (previous and is_terminal_state(previous.get("state"))
                and previous.get("state") != state and not recover_misclassified_cooldown):
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

    def reconcile_strict_selection(self, payload: dict[str, Any], *, finish_contacts: bool = False) -> int:
        """Publish audited bulk-contact results into the per-creator ledger.

        Only a strict delivery selection may supersede an old terminal result;
        ordinary record() transitions retain their terminal-state protection.
        Validate the entire selection before changing any records.
        """
        from audit_strict_contact_highwater import _assert_strict_invariants

        audit = payload.get("audit") or {}
        if (payload.get("contact_dedup_mode") != "strict-any-plaintext-value"
                or audit.get("identity_unique") is not True
                or audit.get("contact_values_unique") is not True):
            raise ValueError("unaudited_flow_reconciliation")
        rows = payload.get("candidates") or []
        if finish_contacts and (not payload.get("target_count")
                or len(rows) < int(payload["target_count"])):
            raise ValueError("cannot_finish_incomplete_contact_stage")
        _assert_strict_invariants(rows, payload.get("strategy") or {})
        selected = []
        for row in rows:
            identity = compact(row.get("identity") or row.get("buyin_uid") or row.get("douyin_id"))
            # The strict contract also accepts authorized email contacts; its
            # invariant check above validates all supported plaintext channels.
            if not identity or row.get("precontact_qualified") is not True:
                raise ValueError("invalid_strict_flow_selection")
            selected.append((identity, row))
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        changed = 0
        for identity, row in selected:
            previous = self._records.get(identity) or {}
            current_row = {**row, "realtime_flow_state": "listed", "realtime_flow_reason": ""}
            if previous.get("state") == "listed" and previous.get("row") == current_row:
                continue
            self._records[identity] = {
                **previous, "identity": identity, "state": "listed", "reason": "",
                "first_seen_at": previous.get("first_seen_at") or now,
                "updated_at": now, "row": current_row,
            }
            changed += 1
        if finish_contacts:
            selected_identities = {identity for identity, _ in selected}
            for identity, previous in self._records.items():
                if identity in selected_identities or previous.get("state") != "contact_revealing":
                    continue
                # The collector has ended. Retain unfinished work as suitable
                # for the next resume, without claiming a contact was obtained.
                reason = "本任务已达到目标，联系方式未完成的候选保留待续"
                self._records[identity] = {
                    **previous, "state": "suitable", "reason": reason, "updated_at": now,
                    "row": {**(previous.get("row") or {}),
                            "realtime_flow_state": "suitable", "realtime_flow_reason": reason},
                }
                changed += 1
        if changed:
            self._save()
        return changed

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
                "precontact_decision", "transient_retry_count",
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
