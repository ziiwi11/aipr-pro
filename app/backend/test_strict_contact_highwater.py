import json
import tempfile
import unittest
from pathlib import Path

from audit_strict_contact_highwater import build_strict_contact_highwater
from creator_delivery_contract import (
    canonicalize_contact_fields,
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
