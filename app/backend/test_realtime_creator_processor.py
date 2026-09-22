from __future__ import annotations

import json
import tempfile
import unittest
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

            first = processor.process(object(), object(), {"identity": "creator-1"})
            second = processor.process(object(), object(), {"identity": "creator-2"})

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
