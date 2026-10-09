from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from realtime_creator_flow import RealtimeCreatorFlowStore
from realtime_creator_processor import RealtimeCreatorProcessor


def rules() -> dict:
    return {
        "targetCount": 1000,
        "threshold": 0,
        "category": "美妆个护",
        "creatorLevels": [1, 2, 3, 4],
        "minimumMonthlySales": 0,
        "requireContact": True,
        "exclusions": [],
    }


class RealtimeCreatorProcessorTests(unittest.TestCase):
    def test_duplicate_shortcut_respects_strong_identity_and_corrupt_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            row = {'identity': 'prior', 'douyin_id': 'same-public-id', 'buyin_contact_phone': '13800138000'}
            processor.strict_path.write_text(json.dumps({'candidates': [row]}))
            with patch.dict('os.environ', {'AIPR_CONTACT_CORRECTIONS': '', 'AIPR_TASK_ID': ''}):
                self.assertFalse(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '13800138000'}))
                processor._strict_audited_in_process = True
                self.assertTrue(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '+86 13800138000'}))
                self.assertFalse(processor._known_contact_duplicate({'identity': 'rotated', 'douyin_id': 'same-public-id', 'buyin_contact_phone': '13800138000'}))
                self.assertFalse(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '13900139000'}))
                self.assertFalse(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '138****8000'}))
                processor.strict_path.write_text('{broken')
                self.assertFalse(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '13800138000'}))

    def test_duplicate_shortcut_applies_contact_revision_before_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            processor.strict_path.write_text(json.dumps({'candidates': [{'identity': 'prior', 'buyin_contact_phone': '13800138000'}]}))
            processor._strict_audited_in_process = True
            revision = {'creatorId': 'new', 'after': {'phone': '13900139000'}, 'source': 'manual', 'recordedAt': 'now', 'revision': 1}
            with patch('contact_corrections.read_corrections', return_value=[revision]):
                self.assertFalse(processor._known_contact_duplicate({'identity': 'new', 'buyin_contact_phone': '13800138000'}))

    def test_resume_includes_email_only_saved_flow_and_contact_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            flow = RealtimeCreatorFlowStore(output_dir / "aipr_realtime_creator_flow.json")
            flow_row = {"identity": "email-flow", "buyin_contact_email": "flow@example.com"}
            pool_row = {"identity": "email-pool", "buyin_contact_email": "pool@example.com"}
            flow.record("email-flow", "listed", flow_row)
            (output_dir / "aipr_contact_highwater.json").write_text(json.dumps({"candidates": [pool_row]}))
            processor = RealtimeCreatorProcessor(output_dir, rules())
            with patch("realtime_creator_processor.build_strict_contact_highwater", return_value={"candidates": []}) as audit:
                processor._strict_payload()
            self.assertEqual(audit.call_args.args[0]["candidates"], [flow_row, pool_row])

    def test_failed_cloud_review_reuses_evidence_but_rechecks_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            verify = MagicMock(side_effect=AssertionError('Must not repeat saved evidence collection'))
            reveal = MagicMock(side_effect=AssertionError('Uncertain creators must not reveal contacts'))
            processor = RealtimeCreatorProcessor(Path(directory), rules(), verify_candidate=verify,
                reveal_contact=reveal, qualify_candidate=lambda row, _: {**row,
                    'precontact_qualified': False, 'precontact_reason': 'Jev unavailable',
                    'jev_analysis': {'route': 'uncertain', 'error_type': 'HTTPError', 'http_status': 503}})
            processor.flow.record('retry', 'evidence_reviewing', {'identity': 'retry',
                'content_evidence_reviewed': True, 'recent_titles': ['面霜使用体验'],
                'jev_analysis': {'route': 'uncertain', 'error_type': 'HTTPError'}})
            result = processor.process(None, None, {'identity': 'retry'})
            self.assertEqual(result['realtime_flow_state'], 'evidence_reviewing')
            self.assertEqual(result['jev_analysis']['http_status'], 503)
            verify.assert_not_called(); reveal.assert_not_called()

    def test_contact_cooldown_is_resumable_without_error_retry_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            row = processor._record_exception("waiting", {"identity": "waiting"}, RuntimeError("contact_cooldown_active:2000"))
            self.assertEqual(row["realtime_flow_state"], "contact_revealing")
            self.assertEqual(row["ui_contact_probe_status"], "rate_limited")
            self.assertNotIn("transient_retry_count", row)

    def test_legacy_cooldown_error_recovers_but_unrelated_error_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RealtimeCreatorFlowStore(Path(directory) / "aipr_realtime_creator_flow.json")
            store.record("waiting", "error", {"identity": "waiting"}, reason="contact_cooldown_active:2000")
            store.record("broken", "error", {"identity": "broken"}, reason="unrelated_failure")
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            self.assertEqual(processor.flow.get("waiting")["state"], "contact_revealing")
            self.assertEqual(processor.flow.get("broken")["state"], "error")

    def test_uncertain_audit_rejection_is_not_a_terminal_contact_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules(),
                qualify_candidate=lambda row, _rules: {**row, "precontact_qualified": False,
                    "precontact_reason": "Jev 待内容复核", "jev_analysis": {"route": "uncertain"}})
            with patch("realtime_creator_processor.build_strict_contact_highwater", return_value={"candidates": []}):
                result = processor._audit_and_list("pending", {"identity": "pending", "buyin_contact_wechat": "wx_pending"})
            self.assertEqual(result["realtime_flow_state"], "evidence_reviewing")
            self.assertEqual(result["buyin_contact_wechat"], "wx_pending")

    def test_audited_judgment_is_retained_for_next_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            row = {"identity": "retained", "buyin_contact_wechat": "wx_retained"}
            judgment = {"route": "supported", "evidence_sha256": "test-fingerprint"}
            audited = {**row, "jev_analysis": judgment}
            def audit(payload, *_args):
                return {"candidates": [{**payload["candidates"][0], "jev_analysis": judgment}]}
            with patch("realtime_creator_processor.build_strict_contact_highwater", side_effect=audit) as build:
                listed = processor._audit_and_list("retained", row)
                self.assertEqual(listed["jev_analysis"], judgment)
                self.assertEqual(build.call_args.args[0]["candidates"][0]["jev_analysis"], judgment)
            # A subsequent process must also load the last audited judgment.
            resumed = RealtimeCreatorProcessor(Path(directory), rules())
            with patch("realtime_creator_processor.build_strict_contact_highwater", side_effect=audit) as build:
                resumed._strict_payload()
                self.assertEqual(build.call_args.args[0]["candidates"][0]["jev_analysis"], judgment)

    def test_resume_revalidates_saved_rows_missing_from_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            saved = {"identity": "delivery-only", "buyin_contact_wechat": "wx_saved",
                     "content_evidence_reviewed": True, "jev_analysis": {"route": "supported"}}
            processor.strict_path.write_text(json.dumps({"candidates": [saved]}))
            with patch("realtime_creator_processor.build_strict_contact_highwater",
                       return_value={"candidates": []}) as audit:
                processor._strict_payload()
            self.assertEqual(audit.call_args.args[0]["candidates"], [saved])
            self.assertEqual(json.loads(processor.strict_path.read_text())["candidates"], [])

    def test_resume_revalidates_contact_pool_rows_missing_from_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), rules())
            row = {"identity": "contact-only", "buyin_contact_wechat": "wx_saved"}
            (Path(directory) / "aipr_contact_highwater.json").write_text(json.dumps({"candidates": [row]}))
            with patch("realtime_creator_processor.build_strict_contact_highwater",
                       return_value={"candidates": []}) as audit:
                processor._strict_payload()
            self.assertEqual(audit.call_args.args[0]["candidates"], [row])
            self.assertEqual(json.loads(processor.strict_path.read_text())["candidates"], [])

    def test_unsuitable_creator_never_calls_contact_revealer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            reveal_calls: list[str] = []

            def verify(_context, candidate, _evidence_dir, _keywords, page=None):
                return {**candidate, "content_evidence_reviewed": False, "evidence_status": "content_unverified"}

            def reveal(_page, candidate, **_kwargs):
                reveal_calls.append(candidate["identity"])
                return candidate

            processor = RealtimeCreatorProcessor(
                output_dir=output_dir,
                strategy=rules(),
                historical_strategy={},
                verify_candidate=verify,
                reveal_contact=reveal,
                qualify_candidate=lambda row, _rules: {**row, "precontact_qualified": False},
            )

            result = processor.process(object(), object(), {"identity": "creator-1"})

            self.assertEqual(result["realtime_flow_state"], "insufficient_evidence")
            self.assertEqual(reveal_calls, [])
            self.assertEqual(RealtimeCreatorFlowStore(output_dir / "aipr_realtime_creator_flow.json").summary()["listed_count"], 0)

    def test_suitable_creator_with_unique_plaintext_is_listed_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)

            def verify(_context, candidate, _evidence_dir, _keywords, page=None):
                return {
                    **candidate,
                    "content_evidence_reviewed": True,
                    "evidence_status": "verified",
                    "gender": 2,
                    "category": "美妆",
                    "contact_visible": True,
                    "evidence_gate": {"beauty_vertical_verified": True},
                }

            def reveal(_page, candidate, **_kwargs):
                return {
                    **candidate,
                    "buyin_contact_wechat": "wx_unique",
                    "ui_contact_probe_status": "revealed",
                }

            processor = RealtimeCreatorProcessor(
                output_dir=output_dir,
                strategy={**rules(), "targetCount": 250, "deliveryTargetCount": 1000},
                historical_strategy={},
                verify_candidate=verify,
                reveal_contact=reveal,
                qualify_candidate=lambda row, _rules: {**row, "precontact_qualified": True},
            )

            result = processor.process(object(), object(), {"identity": "creator-1", "nickname": "达人一"})
            strict = json.loads((output_dir / "aipr_strict_contact_highwater.json").read_text(encoding="utf-8"))

            self.assertEqual(result["realtime_flow_state"], "listed")
            self.assertEqual(strict["target_count"], 1000)
            self.assertEqual(strict["strict_selected_count"], 1)
            self.assertEqual(strict["candidates"][0]["identity"], "creator-1")
            self.assertEqual(RealtimeCreatorFlowStore(output_dir / "aipr_realtime_creator_flow.json").summary()["listed_count"], 1)

    def test_duplicate_contact_is_terminal_and_not_added_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)

            def verify(_context, candidate, _evidence_dir, _keywords, page=None):
                return {
                    **candidate,
                    "content_evidence_reviewed": True,
                    "evidence_status": "verified",
                    "gender": 2,
                    "category": "美妆",
                    "contact_visible": True,
                    "evidence_gate": {"beauty_vertical_verified": True},
                }

            def reveal(_page, candidate, **_kwargs):
                return {**candidate, "buyin_contact_wechat": "same_contact", "ui_contact_probe_status": "revealed"}

            processor = RealtimeCreatorProcessor(
                output_dir=output_dir,
                strategy=rules(),
                historical_strategy={},
                verify_candidate=verify,
                reveal_contact=reveal,
                qualify_candidate=lambda row, _rules: {**row, "precontact_qualified": True},
            )

            page = MagicMock()
            with patch("realtime_creator_processor.time.monotonic", return_value=10):
                first = processor.process(object(), page, {"identity": "creator-1"})
                second = processor.process(object(), page, {"identity": "creator-2"})
            page.wait_for_timeout.assert_called_once_with(30000)

            self.assertEqual(first["realtime_flow_state"], "listed")
            self.assertEqual(second["realtime_flow_state"], "duplicate_contact")
            strict = json.loads((output_dir / "aipr_strict_contact_highwater.json").read_text(encoding="utf-8"))
            self.assertEqual(strict["strict_selected_count"], 1)

    def test_rate_limited_contact_resume_does_not_repeat_evidence_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            verify_calls: list[str] = []
            reveal_calls: list[str] = []

            def verify(_context, candidate, _evidence_dir, _keywords, page=None):
                verify_calls.append(candidate["identity"])
                return {
                    **candidate,
                    "content_evidence_reviewed": True,
                    "evidence_status": "verified",
                    "gender": 2,
                    "category": "美妆",
                    "contact_visible": True,
                    "evidence_gate": {"beauty_vertical_verified": True},
                }

            def reveal(_page, candidate, **_kwargs):
                reveal_calls.append(candidate["identity"])
                if len(reveal_calls) == 1:
                    return {**candidate, "ui_contact_probe_status": "rate_limited"}
                return {
                    **candidate,
                    "buyin_contact_wechat": "wx_resume_unique",
                    "ui_contact_probe_status": "revealed",
                }

            processor = RealtimeCreatorProcessor(
                output_dir=output_dir,
                strategy=rules(),
                historical_strategy={},
                verify_candidate=verify,
                reveal_contact=reveal,
                qualify_candidate=lambda row, _rules: {**row, "precontact_qualified": True},
            )

            first = processor.process(object(), object(), {"identity": "creator-1"})
            second = processor.process(object(), object(), {"identity": "creator-1"})

            self.assertEqual(first["realtime_flow_state"], "contact_revealing")
            self.assertEqual(second["realtime_flow_state"], "listed")
            self.assertEqual(verify_calls, ["creator-1"])
            self.assertEqual(reveal_calls, ["creator-1", "creator-1"])


if __name__ == "__main__":
    unittest.main()
