import json
import tempfile
import unittest
from pathlib import Path
from realtime_creator_flow import RealtimeCreatorFlowStore

from audit_strict_contact_highwater import build_strict_contact_highwater
from creator_delivery_contract import (
    canonicalize_contact_fields,
    normalize_contact_value,
    contact_identity_values,
    select_delivery_candidates,
)
from scrape_buyin_profile_contact_icons_cdp import (
    contact_resume_filename,
    public_intro_filename,
    save_contact_and_strict_highwater,
    save_strict_audit,
)


def candidate(identity: str, contact: str, douyin_id: str | None = None) -> dict:
    return {
        "identity": identity,
        "douyin_id": douyin_id or f"dy-{identity}",
        "nickname": f"达人{identity}",
        "talent_level": "LV2",
        "category": "服饰内衣",
        "profile_text": "服饰内衣 视频20个 真人试穿 ¥2万-¥5万",
        "douyin_content_text": "真人试穿 提臀塑形裤 上身展示",
        "buyin_profile_url": f"https://example.test/{identity}",
        "douyin_homepage": f"https://douyin.com/user/{identity}",
        "content_evidence_reviewed": True,
        "monthly_sales_value": 20000,
        "buyin_contact_wechat": contact,
    }


RULES = {
    "threshold": 78,
    "category": "服饰内衣",
    "creatorLevels": [2, 3, 4],
    "minimumMonthlySales": 10000,
    "contentType": "真人口播",
    "requireContact": True,
    "exclusions": [],
}


class StrictContactHighwaterTest(unittest.TestCase):
    def test_bulk_contacts_reconcile_old_terminal_and_review_states(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            strategy = root / "strategy.json"
            historical = root / "historical.json"
            strategy.write_text(json.dumps(RULES))
            historical.write_text(json.dumps({}))
            flow_path = root / "aipr_realtime_creator_flow.json"
            store = RealtimeCreatorFlowStore(flow_path)
            store.record("reviewed", "evidence_reviewing", {"identity": "reviewed"})
            store.record("authorized", "not_authorized", {"identity": "authorized"}, "old denial")
            store.record("unrelated", "not_authorized", {"identity": "unrelated"})
            first_seen = store.get("authorized")["first_seen_at"]
            strict = save_strict_audit(
                {"candidates": [candidate("reviewed", "wx-review"), candidate("authorized", "wx-authorized")]},
                strategy, historical, root / "aipr_strict_contact_highwater.json", 10,
            )
            store = RealtimeCreatorFlowStore(flow_path)
            self.assertEqual(store.summary()["listed_count"], 2)
            self.assertEqual(store.get("authorized")["first_seen_at"], first_seen)
            self.assertEqual(store.get("authorized")["reason"], "")
            self.assertEqual(store.get("unrelated")["state"], "not_authorized")
            self.assertEqual(store.reconcile_strict_selection(strict), 0)
            with self.assertRaisesRegex(ValueError, "terminal_state_transition"):
                store.record("authorized", "evidence_reviewing", {})

    def test_invalid_strict_selection_does_not_partially_modify_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RealtimeCreatorFlowStore(Path(folder) / "flow.json")
            store.record("kept", "evidence_reviewing", {"identity": "kept"})
            strict = build_strict_contact_highwater(
                {"candidates": [candidate("kept", "wx-kept"), candidate("invalid", "wx-invalid")]},
                RULES, {}, 10,
            )
            strict["candidates"][1]["precontact_qualified"] = False
            before = store.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "invalid_strict_flow_selection"):
                store.reconcile_strict_selection(strict)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.get("kept")["state"], "evidence_reviewing")

    def test_audited_email_only_contacts_are_reconciled(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RealtimeCreatorFlowStore(Path(folder) / "flow.json")
            row = candidate("email", "")
            row["buyin_contact_email"] = "creator@example.test"
            strict = build_strict_contact_highwater({"candidates": [row]}, RULES, {}, 10)
            self.assertEqual(len(strict["candidates"]), 1)
            self.assertEqual(store.reconcile_strict_selection(strict), 1)
            self.assertEqual(store.get("email")["state"], "listed")

    def test_incomplete_target_cannot_close_pending_contact_states(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RealtimeCreatorFlowStore(Path(folder) / "flow.json")
            store.record("pending", "contact_revealing", {"identity": "pending", "shop": "A"})
            strict = build_strict_contact_highwater(
                {"candidates": [candidate("kept", "wx-kept")]}, RULES, {}, 10)
            before = store.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "cannot_finish_incomplete_contact_stage"):
                store.reconcile_strict_selection(strict, finish_contacts=True)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.get("pending")["state"], "contact_revealing")

    def test_replenishment_contact_temporaries_are_isolated(self):
        payload = {"strategy": {"strategyPurpose": "replenishment-source-only"}}
        self.assertEqual(
            contact_resume_filename(payload),
            "aipr_contact_resume_replenishment_input.json",
        )
        self.assertEqual(
            public_intro_filename(payload, "B"),
            "aipr_public_intro_replenishment_B.json",
        )
        self.assertEqual(contact_resume_filename({}), "aipr_contact_resume_input.json")
        self.assertEqual(public_intro_filename({}, "B"), "aipr_public_intro_B.json")

    def test_contact_fields_are_canonicalized_before_delivery(self):
        row = {
            "buyin_contact_phone": "13800000000(+2890)",
            "buyin_contact_wechat": "WX_Valid_123",
            "buyin_contact_email": "Creator@Example.COM",
        }

        normalized = canonicalize_contact_fields(row)

        self.assertEqual(normalized["buyin_contact_phone"], "13800000000")
        self.assertEqual(normalized["buyin_contact_wechat"], "wx_valid_123")
        self.assertEqual(normalized["buyin_contact_email"], "creator@example.com")
        self.assertEqual(
            contact_identity_values(normalized),
            {"13800000000", "wx_valid_123", "creator@example.com"},
        )

    def test_resume_strict_audit_applies_recorded_contact_revision(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            filename=Path(temp)/"corrections.json"
            filename.write_text(json.dumps({"schema":"qianxun-contact-corrections-v1","taskId":"resume","records":[{"creatorId":"a","after":{"wechat":"A13800000000","phone":"","email":""},"source":"historical_platform_ui_prefix_repair","recordedAt":"2026-10-08","revision":1}]}))
            original=candidate("a","13800000000")
            with patch.dict(os.environ,{"AIPR_CONTACT_CORRECTIONS":str(filename),"AIPR_TASK_ID":"resume"}):
                result=build_strict_contact_highwater({"candidates":[original]},RULES,{},1)
            self.assertEqual(result["candidates"][0]["buyin_contact_wechat"],"a13800000000")
            self.assertEqual(original["buyin_contact_wechat"],"13800000000")

    def test_wechat_containing_phone_digits_keeps_its_letters(self):
        row = canonicalize_contact_fields({"buyin_contact_wechat": "A13800000000", "buyin_contact_phone": "13800000000"})
        self.assertEqual(row["buyin_contact_wechat"], "a13800000000")
        self.assertEqual(contact_identity_values(row), {"a13800000000", "13800000000"})
        self.assertEqual(normalize_contact_value("A13800000000"), "a13800000000")
        self.assertEqual(canonicalize_contact_fields({"buyin_contact_wechat":"13800000000"})["buyin_contact_wechat"], "13800000000")

    def test_invalid_contact_placeholders_do_not_count_as_plain_contacts(self):
        row = {
            "buyin_contact_phone": "1234567",
            "buyin_contact_wechat": "同手机号",
            "buyin_contact_email": "not-an-email",
        }

        normalized = canonicalize_contact_fields(row)

        self.assertEqual(contact_identity_values(normalized), set())
        self.assertEqual(normalized["buyin_contact_phone"], "")
        self.assertEqual(normalized["buyin_contact_wechat"], "")
        self.assertEqual(normalized["buyin_contact_email"], "")

    def test_delivery_deduplicates_on_any_strong_creator_identity(self):
        rows = [
            candidate("encrypted-a", "wechat-a", douyin_id="same-public-id"),
            candidate("encrypted-b", "wechat-b", douyin_id="same-public-id"),
            candidate("encrypted-c", "wechat-c"),
        ]

        selected = select_delivery_candidates(rows, RULES, 3)

        self.assertEqual([row["identity"] for row in selected], ["encrypted-a", "encrypted-c"])

    def test_delivery_rejects_any_historical_strong_identity(self):
        rows = [candidate("fresh-encrypted", "wechat-a", douyin_id="delivered-public"), candidate("fresh", "wechat-b")]
        rules = {**RULES, "excludeIdentities": ["delivered-public"]}

        selected = select_delivery_candidates(rows, rules, 2)

        self.assertEqual([row["identity"] for row in selected], ["fresh"])

    def test_audit_enforces_cross_round_and_in_round_contact_uniqueness(self):
        payload = {
            "candidates": [
                candidate("historical-contact", "old-contact"),
                candidate("kept", "fresh-contact", douyin_id="same-public"),
                candidate("duplicate-id", "different-contact", douyin_id="same-public"),
                candidate("duplicate-contact", "fresh-contact"),
                candidate("kept-two", "another-contact"),
            ]
        }

        result = build_strict_contact_highwater(
            payload,
            RULES,
            {"excludeContacts": ["old-contact"]},
            target_count=10,
        )

        self.assertEqual(result["strict_selected_count"], 2)
        self.assertEqual([row["identity"] for row in result["candidates"]], ["kept", "kept-two"])
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["audit"]["identity_unique"])
        self.assertTrue(result["audit"]["contact_values_unique"])
        self.assertEqual(result["audit"]["cross_round_contact_overlap"], 0)

    def test_contact_batch_can_atomically_save_the_strict_checkpoint(self):
        payload = {"candidates": [candidate("kept", "fresh-contact")]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            strategy = root / "strategy.json"
            historical = root / "historical.json"
            output = root / "aipr_strict_contact_highwater.json"
            strategy.write_text(json.dumps(RULES), encoding="utf-8")
            historical.write_text(json.dumps({"excludeContacts": ["old-contact"]}), encoding="utf-8")

            result = save_strict_audit(payload, strategy, historical, output, target_count=10)

            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["strict_selected_count"], 1)
            self.assertEqual(saved["strict_selected_count"], 1)
            self.assertTrue(saved["audit"]["identity_unique"])
            self.assertTrue(saved["audit"]["contact_values_unique"])

    def test_replenishment_batch_audits_the_accumulated_contact_highwater(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            strategy = root / "strategy.json"
            historical = root / "historical.json"
            audit_output = root / "aipr_strict_contact_highwater.json"
            strategy.write_text(json.dumps(RULES), encoding="utf-8")
            historical.write_text(json.dumps({"excludeContacts": ["old-contact"]}), encoding="utf-8")
            (root / "aipr_contact_highwater.json").write_text(json.dumps({
                "candidates": [candidate("existing-pool", "existing-contact")],
            }), encoding="utf-8")

            strict = save_contact_and_strict_highwater(
                root,
                {"candidates": [candidate("new-pool", "new-contact")]},
                strategy,
                historical,
                audit_output,
                target_count=10,
            )

            self.assertEqual(strict["strict_selected_count"], 2)
            self.assertEqual(
                [row["identity"] for row in strict["candidates"]],
                ["existing-pool", "new-pool"],
            )
            merged = json.loads((root / "aipr_contact_highwater.json").read_text(encoding="utf-8"))
            self.assertEqual(len(merged["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()


class SavedListProgressTests(unittest.TestCase):
    def test_progress_tracks_real_completed_rows_without_revealing_contacts(self):
        from unittest.mock import patch
        events = []
        with patch("audit_strict_contact_highwater.mark_precontact_qualification", side_effect=lambda row, rules: row), patch("audit_strict_contact_highwater.select_delivery_candidates", return_value=[]), patch("audit_strict_contact_highwater._assert_strict_invariants", return_value={}):
            result = build_strict_contact_highwater({"candidates": [{"identity":str(i)} for i in range(27)]}, {}, {}, progress=events.append)
        self.assertEqual([e["completed"] for e in events], [0,25,27])
        self.assertTrue(all(e["total"] == 27 for e in events))
        self.assertFalse(any("contact" in e for e in events))
        self.assertEqual(result["source_candidate_count"],27)
