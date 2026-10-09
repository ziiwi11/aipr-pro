from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from contact_icons_single import select_contact_targets
from scrape_buyin_profile_contact_icons_cdp import (
    assign_contact_lanes,
    contact_preflight_profile_url,
    merge_recent_contact_shards,
    profile_session_ready,
    public_intro_required,
)
from scrape_buyin_public_intro_contacts_cdp import select_targets as select_intro_targets


class ContactLaneAssignmentTest(unittest.TestCase):
    def test_preflight_prefers_each_shops_successful_profile(self):
        rows = [
            {"shop": "A", "precontact_qualified": True, "ui_contact_probe_status": "revealed", "buyin_profile_url": "https://buyin.example/a"},
            {"shop": "B", "precontact_qualified": True, "ui_contact_probe_status": "revealed", "buyin_profile_url": "https://buyin.example/b"},
        ]
        self.assertEqual(contact_preflight_profile_url(rows, shop="A"), "https://buyin.example/a")
        self.assertEqual(contact_preflight_profile_url(rows, shop="B"), "https://buyin.example/b")

    def test_preflight_skips_creator_that_previously_hit_rate_limit(self) -> None:
        rows = [
            {
                "identity": "poisoned",
                "precontact_qualified": True,
                "buyin_profile_url": "https://buyin.example/poisoned",
                "ui_contact_probe_status": "rate_limited",
            },
            {
                "identity": "healthy",
                "precontact_qualified": True,
                "buyin_profile_url": "https://buyin.example/healthy",
            },
        ]

        self.assertEqual(contact_preflight_profile_url(rows), "https://buyin.example/healthy")

    def test_preflight_prefers_profile_that_already_opened_successfully(self) -> None:
        rows = [
            {
                "identity": "untouched",
                "precontact_qualified": True,
                "buyin_profile_url": "https://buyin.example/untouched",
            },
            {
                "identity": "known-good",
                "precontact_qualified": True,
                "buyin_profile_url": "https://buyin.example/known-good",
                "buyin_contact_wechat": "known_contact",
                "ui_contact_probe_status": "revealed",
            },
        ]

        self.assertEqual(contact_preflight_profile_url(rows), "https://buyin.example/known-good")

    def test_reuses_completed_public_intro_scan(self) -> None:
        rows = [{
            "identity": "done",
            "contact_shop": "A",
            "precontact_qualified": True,
            "buyin_public_intro_checked": True,
        }]

        self.assertFalse(public_intro_required(rows, "A"))
    def test_preserves_source_shop_for_session_scoped_buyin_uid(self) -> None:
        rows = [
            {
                "identity": f"creator-{index}",
                "shop": "A",
                "buyin_profile_url": f"https://buyin.example/creator-{index}",
                "content_evidence_reviewed": True,
                "precontact_qualified": True,
            }
            for index in range(6)
        ]
        rows.extend([
            {
                "identity": "already-contacted",
                "shop": "A",
                "content_evidence_reviewed": True,
                "precontact_qualified": True,
                "buyin_contact_wechat": "wx_done",
            },
            {
                "identity": "unqualified",
                "shop": "A",
                "content_evidence_reviewed": True,
                "precontact_qualified": False,
            },
        ])

        assigned = assign_contact_lanes(rows)

        self.assertEqual(sum(row.get("contact_shop") == "A" for row in assigned), 6)
        self.assertEqual(sum(row.get("contact_shop") == "B" for row in assigned), 0)
        self.assertNotIn("contact_shop", next(row for row in assigned if row["identity"] == "already-contacted"))
        self.assertNotIn("contact_shop", next(row for row in assigned if row["identity"] == "unqualified"))
        self.assertEqual(len(select_contact_targets(assigned, "A", 0)), 6)
        self.assertEqual(len(select_contact_targets(assigned, "B", 0)), 0)
        self.assertEqual(len(select_intro_targets(assigned, "A", 0)), 6)
        self.assertEqual(len(select_intro_targets(assigned, "B", 0)), 0)

    def test_assigns_only_active_shops_and_skips_terminal_contact_failures(self) -> None:
        rows = [
            {
                "identity": "retry-on-a",
                "content_evidence_reviewed": True,
                "precontact_qualified": True,
            },
            {
                "identity": "terminal",
                "content_evidence_reviewed": True,
                "precontact_qualified": True,
                "ui_contact_probe_status": "category_not_matched",
            },
        ]

        assigned = assign_contact_lanes(rows, active_shops=["A"])

        self.assertEqual(assigned[0]["contact_shop"], "A")
        self.assertNotIn("contact_shop", assigned[1])

    def test_recovers_contact_shards_without_overwriting_fresh_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            shard = {
                "candidates": [{
                    "identity": "creator-1",
                    "content_evidence_reviewed": True,
                    "evidence_contract_version": 1,
                    "buyin_contact_wechat": "wx_recovered",
                    "ui_contact_probe_status": "revealed",
                }],
            }
            (output_dir / "ui_contact_icon_retry_A_20260719_120000.json").write_text(
                json.dumps(shard, ensure_ascii=False), encoding="utf-8"
            )
            fresh = [{
                "identity": "creator-1",
                "content_evidence_reviewed": False,
                "evidence_contract_version": 4,
            }]

            recovered = merge_recent_contact_shards(output_dir, fresh)

            self.assertEqual(recovered[0]["buyin_contact_wechat"], "wx_recovered")
            self.assertFalse(recovered[0]["content_evidence_reviewed"])
            self.assertEqual(recovered[0]["evidence_contract_version"], 4)

    def test_profile_session_rejects_redirected_storefront_pages(self) -> None:
        self.assertFalse(profile_session_ready("https://www.douyinec.com/", "抖音电商官网"))
        self.assertTrue(profile_session_ready(
            "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=1",
            "达人自主披露联系方式 粉丝数 带货口碑",
        ))


if __name__ == "__main__":
    unittest.main()
