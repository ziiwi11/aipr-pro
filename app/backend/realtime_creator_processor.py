from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable

from atomic_json_io import atomic_write_json
from audit_strict_contact_highwater import build_strict_contact_highwater
from contact_icons_single import run_candidate
from creator_delivery_contract import (canonicalize_contact_fields, mark_precontact_qualification,
                                      contact_identity_values, creator_identity_values)
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
        audit_progress: Callable[..., None] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.strategy = dict(strategy)
        self.historical_strategy = dict(historical_strategy or {})
        self.verify_candidate = verify_candidate
        self.reveal_contact = reveal_contact
        self.qualify_candidate = qualify_candidate
        self.audit_progress = audit_progress
        self.flow = RealtimeCreatorFlowStore(self.output_dir / "aipr_realtime_creator_flow.json")
        self.strict_path = self.output_dir / "aipr_strict_contact_highwater.json"
        self.evidence_dir = self.output_dir / "evidence"
        self._last_profile_visit = None
        self._strict_audited_in_process = False
        # Recover only the old misclassified cooldown records. Other errors
        # retain their original state and evidence.
        for record in self.flow.rows():
            if (record.get("state") == "error"
                    and str(record.get("reason") or "").startswith("contact_cooldown_active:")):
                row = {**(record.get("row") or {}), "ui_contact_probe_status": "rate_limited"}
                self._record(record["identity"], "contact_revealing", row, "rate_limited")

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

    @staticmethod
    def _review_pending(row: dict[str, Any]) -> bool:
        return (row.get("precontact_decision") == "待内容复核"
                or (row.get("jev_analysis") or {}).get("route") in ("uncertain", "review_conflict"))

    def _record_exception(self, identity: str, current: dict[str, Any], exc: Exception) -> dict[str, Any]:
        text = str(exc)[:300]
        if text.startswith("contact_cooldown_active:"):
            current = {**current, "ui_contact_probe_status": "rate_limited"}
            return self._record(identity, "contact_revealing", current, "rate_limited")
        retryable = isinstance(exc, (TimeoutError, ConnectionError)) or any(
            token in text.lower() for token in ("timed out", "timeout", "net::err_", "connection closed",
                "connection reset", "target closed", "browser has been closed", "econnreset", "page crashed"))
        attempts = int(current.get("transient_retry_count") or 0) + 1
        current = {**current, "transient_retry_count": attempts}
        return self._record(identity, "retry_pending" if retryable and attempts <= 3 else "error", current, text)

    def delivery_target_reached(self) -> bool:
        """Only the audited formal shortlist can end discovery, never raw contacts."""
        import json
        target = int(self.strategy.get("deliveryTargetCount") or self.strategy.get("targetCount") or 0)
        if target <= 0 or not self.strict_path.exists():
            return False
        try:
            payload = json.loads(self.strict_path.read_text(encoding="utf-8"))
            return (payload.get("status") == "complete"
                    and int(payload.get("strict_selected_count") or 0) >= target
                    and len(payload.get("candidates") or []) >= target)
        except (OSError, ValueError, TypeError):
            return False

    def _strict_payload(self) -> dict[str, Any]:
        # Retain the last audited judgment across batches. creator_jev validates
        # its evidence/policy fingerprint before reuse; all hard gates run again.
        previous_rows = {}
        if self.strict_path.exists():
            try:
                import json
                previous = json.loads(self.strict_path.read_text(encoding="utf-8"))
                previous_rows = {self._identity(row): row for row in previous.get("candidates") or []
                                 if isinstance(row, dict)}
            except (OSError, ValueError, TypeError):
                pass
        candidates = [
            {**record["row"], **({"jev_analysis": previous_rows[self._identity(record["row"])]["jev_analysis"]}
                if previous_rows.get(self._identity(record["row"]), {}).get("jev_analysis") else {})}
            for record in self.flow.rows()
            if isinstance(record.get("row"), dict) and has_authorized_plaintext(record["row"])
        ]
        # The flow ledger may lag delivery finalization; preserve audited rows
        # and revalidate their full evidence instead of keeping only judgments.
        contact_rows = []
        contact_path = self.output_dir / "aipr_contact_highwater.json"
        if contact_path.exists():
            try:
                import json
                payload = json.loads(contact_path.read_text(encoding="utf-8"))
                contact_rows = [row for row in payload.get("candidates") or []
                                if isinstance(row, dict) and has_authorized_plaintext(row)]
            except (OSError, ValueError, TypeError):
                pass
        candidates = list(previous_rows.values()) + candidates + contact_rows
        strict = build_strict_contact_highwater(
            {"status": "ready", "candidates": candidates},
            self.strategy,
            self.historical_strategy,
            max(1, int(
                self.strategy.get("deliveryTargetCount")
                or self.strategy.get("targetCount")
                or 1000
            )),
            **({"progress": self.audit_progress} if self.audit_progress else {}),
        )
        atomic_write_json(self.strict_path, strict)
        self._strict_audited_in_process = True
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
            qualified = self.qualify_candidate(current, self.strategy)
            if not qualified.get("precontact_qualified"):
                judgment = qualified.get("jev_analysis") or {}
                if self._review_pending(qualified):
                    return self._record(identity, "evidence_reviewing", qualified,
                                        qualified.get("precontact_reason") or "strict_content_review_pending")
                return self._record(identity, "unsuitable", qualified,
                                    qualified.get("precontact_reason") or "strict_qualification_rejected")
            return self._record(identity, "duplicate_contact", current, "strict_contact_gate_rejected")
        audited_row = next(row for row in strict.get("candidates") or []
                           if isinstance(row, dict) and self._identity(row) == identity)
        current = self._record(identity, "listed", {**current, **audited_row})
        self._strict_payload()
        return current

    def _known_contact_duplicate(self, candidate: dict[str, Any]) -> bool:
        """Conservative shortcut; the full strict audit still decides admission."""
        import json
        import os
        from contact_corrections import read_corrections, apply_corrections
        # A previous run may have used different qualification rules. Wait for
        # this process's full audit before treating that snapshot as authoritative.
        if not self._strict_audited_in_process:
            return False
        try:
            payload = json.loads(self.strict_path.read_text(encoding="utf-8"))
            rows = payload["candidates"]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                return False
            corrections = read_corrections(os.environ.get("AIPR_CONTACT_CORRECTIONS", ""),
                                           os.environ.get("AIPR_TASK_ID", ""))
            corrected = apply_corrections([candidate] + rows, corrections)
            current = corrected[0]
            identities = creator_identity_values(current)
            contacts = contact_identity_values(current)
            if not identities or not contacts:
                return False
            return any(isinstance(row, dict) and creator_identity_values(row)
                       and not identities.intersection(creator_identity_values(row))
                       and bool(contacts.intersection(contact_identity_values(row)))
                       for row in corrected[1:])
        except (OSError, ValueError, TypeError, KeyError):
            return False

    def _reveal_and_list(self, page: Any, identity: str, current: dict[str, Any]) -> dict[str, Any]:
        current = self._record(identity, "contact_revealing", current)
        try:
            current = self.reveal_contact(
                page,
                current,
                delay_ms=max(3000, int(self.strategy.get("contactDelayMs") or 3200)),
                output_dir=self.output_dir,
                reveal_interval_ms=max(60000, int(self.strategy.get("contactRevealIntervalMs") or 60000)),
                **({"stop_if_duplicate": self._known_contact_duplicate,
                    "primary_contact_only": self.strategy.get("contactCollectionMode") == "primary_wechat"}
                   if self.reveal_contact is run_candidate else {}),
            )
        except Exception as exc:
            return self._record_exception(identity, current, exc)
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

        current = {**candidate, **(previous.get("row") or {})} if previous else dict(candidate)
        # Retry only the failed cloud judgment against already observed evidence.
        # Genuine model uncertainty still needs fresh evidence/manual review.
        if (previous and previous.get("state") == "evidence_reviewing"
                and (current.get("jev_analysis") or {}).get("error_type")
                and current.get("content_evidence_reviewed") is True):
            current = self.qualify_candidate(current, self.strategy)
            if current.get("precontact_qualified") is not True:
                return self._record(identity, "evidence_reviewing", current,
                                    str(current.get("precontact_reason") or "cloud_review_pending"))
            if has_authorized_plaintext(current):
                return self._audit_and_list(identity, current)
            return self._reveal_and_list(page, identity, self._record(identity, "suitable", current))
        current = self._record(identity, "discovered", current)
        current = self._record(identity, "identity_unique", current)
        current = self._record(identity, "evidence_reviewing", current)
        try:
            interval = max(30000, int(self.strategy.get("profileVisitIntervalMs") or 30000))
            if page is not None and self._last_profile_visit is not None:
                remaining = interval - (time.monotonic() - self._last_profile_visit) * 1000
                if remaining > 0:
                    page.wait_for_timeout(int(remaining))
            self._last_profile_visit = time.monotonic()
            current = self.verify_candidate(
                context,
                current,
                self.evidence_dir,
                [str(item) for item in self.strategy.get("keywords") or []],
                page=page,
            )
        except Exception as exc:
            return self._record_exception(identity, current, exc)

        if current.get("content_evidence_reviewed") is not True:
            reason = str(current.get("evidence_status") or "insufficient_evidence")
            if reason == "error":
                return self._record_exception(identity, current,
                    RuntimeError(str(current.get("evidence_error") or "evidence_verification_error")))
            if reason == "rate_limited":
                return self._record(identity, "evidence_reviewing", current, reason)
            return self._record(identity, "insufficient_evidence", current, reason)

        current = self.qualify_candidate(current, self.strategy)
        if current.get("precontact_qualified") is not True:
            reason = str(current.get("precontact_reason") or "unsuitable")
            analysis = current.get("jev_analysis") or {}
            if self._review_pending(current):
                return self._record(identity, "evidence_reviewing", current, reason)
            return self._record(identity, "unsuitable", current, reason)

        current = self._record(identity, "suitable", current)
        return self._reveal_and_list(page, identity, current)
