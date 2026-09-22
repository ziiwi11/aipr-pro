from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from atomic_json_io import atomic_write_json
from audit_strict_contact_highwater import build_strict_contact_highwater
from contact_icons_single import run_candidate
from creator_delivery_contract import canonicalize_contact_fields, mark_precontact_qualification
from realtime_creator_flow import RealtimeCreatorFlowStore, has_authorized_plaintext, is_terminal_state
from verify_creator_evidence_cdp import verify_one


VerifyCallable = Callable[..., dict[str, Any]]
RevealCallable = Callable[..., dict[str, Any]]
QualifyCallable = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RealtimeCreatorProcessor:
    def __init__(
        self,
        output_dir: Path,
        strategy: dict[str, Any],
        historical_strategy: dict[str, Any] | None = None,
        verify_candidate: VerifyCallable = verify_one,
        reveal_contact: RevealCallable = run_candidate,
        qualify_candidate: QualifyCallable = mark_precontact_qualification,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.strategy = dict(strategy)
        self.historical_strategy = dict(historical_strategy or {})
        self.verify_candidate = verify_candidate
        self.reveal_contact = reveal_contact
        self.qualify_candidate = qualify_candidate
        self.flow = RealtimeCreatorFlowStore(self.output_dir / "aipr_realtime_creator_flow.json")
        self.strict_path = self.output_dir / "aipr_strict_contact_highwater.json"
        self.evidence_dir = self.output_dir / "evidence"

    @staticmethod
    def _identity(candidate: dict[str, Any]) -> str:
        return str(
            candidate.get("identity")
            or candidate.get("buyin_uid")
            or candidate.get("douyin_id")
            or ""
        ).strip()

    @staticmethod
    def _with_state(row: dict[str, Any], state: str, reason: str = "") -> dict[str, Any]:
        return {
            **row,
            "realtime_flow_state": state,
            "realtime_flow_reason": str(reason or "").strip(),
        }

    def _record(self, identity: str, state: str, row: dict[str, Any], reason: str = "") -> dict[str, Any]:
        current = self._with_state(row, state, reason)
        self.flow.record(identity, state, current, reason=reason)
        return current

    def _strict_payload(self) -> dict[str, Any]:
        candidates = [
            record.get("row")
            for record in self.flow.rows()
            if isinstance(record.get("row"), dict) and has_authorized_plaintext(record["row"])
        ]
        strict = build_strict_contact_highwater(
            {"status": "ready", "candidates": candidates},
            self.strategy,
            self.historical_strategy,
            max(1, int(
                self.strategy.get("deliveryTargetCount")
                or self.strategy.get("targetCount")
                or 1000
            )),
        )
        atomic_write_json(self.strict_path, strict)
        return strict

    def _audit_and_list(self, identity: str, current: dict[str, Any]) -> dict[str, Any]:
        current = self._record(identity, "plaintext_unique", current)
        strict = self._strict_payload()
        selected_identities = {
            self._identity(row)
            for row in strict.get("candidates") or []
            if isinstance(row, dict)
        }
        if identity not in selected_identities:
            return self._record(identity, "duplicate_contact", current, "strict_contact_gate_rejected")
        current = self._record(identity, "listed", current)
        self._strict_payload()
        return current

    def _reveal_and_list(self, page: Any, identity: str, current: dict[str, Any]) -> dict[str, Any]:
        current = self._record(identity, "contact_revealing", current)
        try:
            current = self.reveal_contact(
                page,
                current,
                delay_ms=max(3000, int(self.strategy.get("contactDelayMs") or 3200)),
                output_dir=self.output_dir,
                reveal_interval_ms=max(8000, int(self.strategy.get("contactRevealIntervalMs") or 12000)),
            )
        except Exception as exc:
            return self._record(identity, "error", current, str(exc)[:300])
        current = canonicalize_contact_fields(current)
        if not has_authorized_plaintext(current):
            status = str(current.get("ui_contact_probe_status") or "not_available")
            if status in {"rate_limited", "daily_quota_exhausted"}:
                return self._record(identity, "contact_revealing", current, status)
            if status == "category_not_matched":
                return self._record(identity, "not_authorized", current, status)
            return self._record(identity, "not_available", current, status)
        return self._audit_and_list(identity, current)

    def process(self, context: Any, page: Any, candidate: dict[str, Any]) -> dict[str, Any]:
        identity = self._identity(candidate)
        if not identity:
            return self._with_state(candidate, "error", "missing_creator_identity")
        previous = self.flow.get(identity)
        if previous and is_terminal_state(previous.get("state")):
            return dict(previous.get("row") or candidate)

        if previous and previous.get("state") in {"suitable", "contact_revealing"}:
            return self._reveal_and_list(
                page,
                identity,
                dict(previous.get("row") or candidate),
            )
        if previous and previous.get("state") == "plaintext_unique":
            return self._audit_and_list(
                identity,
                dict(previous.get("row") or candidate),
            )

        current = self._record(identity, "discovered", candidate)
        current = self._record(identity, "identity_unique", current)
        current = self._record(identity, "evidence_reviewing", current)
        try:
            current = self.verify_candidate(
                context,
                current,
                self.evidence_dir,
                [str(item) for item in self.strategy.get("keywords") or []],
                page=page,
            )
        except Exception as exc:
            return self._record(identity, "error", current, str(exc)[:300])

        if current.get("content_evidence_reviewed") is not True:
            reason = str(current.get("evidence_status") or "insufficient_evidence")
            return self._record(identity, "insufficient_evidence", current, reason)

        current = self.qualify_candidate(current, self.strategy)
        if current.get("precontact_qualified") is not True:
            reason = str(current.get("precontact_reason") or "unsuitable")
            return self._record(identity, "unsuitable", current, reason)

        current = self._record(identity, "suitable", current)
        return self._reveal_and_list(page, identity, current)
