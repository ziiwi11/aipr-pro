from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from realtime_creator_flow import (
    RealtimeCreatorFlowStore,
    has_authorized_plaintext,
    is_terminal_state,
)


class RealtimeCreatorFlowStoreTests(unittest.TestCase):
    def test_persists_each_creator_immediately_and_summarizes_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aipr_realtime_creator_flow.json"
            store = RealtimeCreatorFlowStore(path)

            store.record("creator-1", "discovered", {"identity": "creator-1"})
            first_payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(first_payload["records"][0]["state"], "discovered")

            store.record(
                "creator-1",
                "listed",
                {"identity": "creator-1", "buyin_contact_wechat": "wx_unique"},
            )
            store.record(
                "creator-2",
                "unsuitable",
                {"identity": "creator-2"},
                reason="content_not_matched",
            )

            reopened = RealtimeCreatorFlowStore(path)
            self.assertEqual(reopened.get("creator-1")["state"], "listed")
            self.assertEqual(reopened.get("creator-2")["reason"], "content_not_matched")
            self.assertEqual(
                reopened.summary(),
                {
                    "discovered_count": 2,
                    "suitable_count": 1,
                    "contact_revealing_count": 0,
                    "plaintext_count": 1,
                    "listed_count": 1,
                    "terminal_count": 2,
                },
            )

    def test_plaintext_requires_unmasked_wechat_or_phone(self) -> None:
        self.assertTrue(has_authorized_plaintext({"buyin_contact_wechat": "wx_creator"}))
        self.assertTrue(has_authorized_plaintext({"buyin_contact_phone": "13800000000"}))
        self.assertFalse(has_authorized_plaintext({"buyin_contact_phone": "138****0000"}))
        self.assertFalse(has_authorized_plaintext({"buyin_contact_wechat": "***"}))
        self.assertFalse(has_authorized_plaintext({"contact_visible": True}))

    def test_email_only_contacts_require_valid_unmasked_address(self) -> None:
        for key in ("buyin_contact_email", "cart_contact_email", "email", "邮箱"):
            self.assertTrue(has_authorized_plaintext({key: "creator@example.com"}))
            for invalid in ("c***@example.com", "未授权", "example.com", "creator@"):
                self.assertFalse(has_authorized_plaintext({key: invalid}))

    def test_terminal_states_cannot_move_back_into_processing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RealtimeCreatorFlowStore(Path(directory) / "flow.json")
            store.record("creator-1", "unsuitable", {"identity": "creator-1"})
            with self.assertRaisesRegex(ValueError, "terminal_state_transition"):
                store.record("creator-1", "evidence_reviewing", {"identity": "creator-1"})

        for state in (
            "listed",
            "duplicate_identity",
            "unsuitable",
            "insufficient_evidence",
            "not_authorized",
            "not_available",
            "duplicate_contact",
            "error",
        ):
            self.assertTrue(is_terminal_state(state), state)

    def test_explicit_retry_reset_restores_selected_terminal_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RealtimeCreatorFlowStore(Path(directory) / "flow.json")
            store.record(
                "creator-1",
                "insufficient_evidence",
                {"identity": "creator-1", "evidence_status": "content_unverified"},
            )
            store.record("creator-2", "unsuitable", {"identity": "creator-2"})

            reset = store.reset_for_retry(
                ["creator-1"], reason="profile_skeleton_wait_fixed"
            )

            self.assertEqual(reset, 1)
            self.assertEqual(store.get("creator-1")["state"], "discovered")
            self.assertEqual(
                store.get("creator-1")["reason"], "profile_skeleton_wait_fixed"
            )
            self.assertEqual(store.get("creator-2")["state"], "unsuitable")


if __name__ == "__main__":
    unittest.main()
