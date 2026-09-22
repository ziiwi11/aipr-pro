import unittest
import threading
import time
import tempfile
from pathlib import Path
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import Mock

from verify_creator_evidence_cdp import (
    apply_structured_beauty_evidence,
    connect_over_cdp_serialized,
    ensure_evidence_free_space,
    evidence_profile_session_ready,
    evidence_active_shops,
    evidence_highwater_filename,
    evidence_output_prefix,
    evidence_source_pool_ready,
    invalidate_stale_content_evidence,
    merge_evidence_candidate_updates,
    meaningful_lines,
    profile_data_loaded,
    is_beauty_profile_candidate,
    merge_evidence_highwater,
    open_owned_douyin_page,
    partition_evidence_by_shop,
    partition_evidence_lanes,
    pending_evidence_candidates,
    required_evidence_free_bytes,
    should_capture_evidence_screenshots,
    wait_for_lane_futures,
    verify_one,
)


class EvidenceHighWaterTest(unittest.TestCase):
    def test_profile_data_wait_rejects_skeleton_and_accepts_loaded_creator(self):
        self.assertFalse(profile_data_loaded("达人昵称 粉丝 履约分 - 达人简介：暂无"))
        self.assertTrue(profile_data_loaded("小美 1.2万粉丝 履约分 95 达人简介：真人美妆测评"))

    def test_beauty_category_is_detected_without_search_keywords(self):
        self.assertTrue(is_beauty_profile_candidate({"category": "美妆"}, []))
        self.assertTrue(is_beauty_profile_candidate({"category": "个护家清"}, []))
        self.assertFalse(is_beauty_profile_candidate({"category": "食品饮料"}, []))

    def test_replenishment_evidence_rejects_partial_source_checkpoint(self):
        payload = {
            "status": "checkpoint",
            "complete": False,
            "candidate_count": 2,
            "target_count": 3,
            "strategy": {"strategyPurpose": "replenishment-source-only"},
            "candidates": [{"identity": "1"}, {"identity": "2"}],
        }

        self.assertEqual(
            evidence_source_pool_ready(payload),
            (False, "source_pool_status_not_ready"),
        )

    def test_replenishment_evidence_requires_real_rows_at_target(self):
        payload = {
            "status": "ready",
            "complete": True,
            "candidate_count": 3,
            "target_count": 3,
            "strategy": {"strategyPurpose": "replenishment-source-only"},
            "candidates": [{"identity": "1"}, {"identity": "2"}],
        }

        self.assertEqual(
            evidence_source_pool_ready(payload),
            (False, "source_pool_rows_below_target"),
        )

    def test_replenishment_evidence_accepts_complete_source_pool(self):
        payload = {
            "status": "ready",
            "complete": True,
            "candidate_count": 2,
            "target_count": 2,
            "strategy": {"strategyPurpose": "replenishment-source-only"},
            "candidates": [{"identity": "1"}, {"identity": "2"}],
        }

        self.assertEqual(evidence_source_pool_ready(payload), (True, "ready"))

    def test_regular_evidence_source_remains_backward_compatible(self):
        self.assertEqual(
            evidence_source_pool_ready({"strategy": {}, "candidates": []}),
            (True, "legacy_or_regular_source"),
        )

    def test_replenishment_evidence_uses_b_only_and_isolated_files(self):
        payload = {
            "strategy": {
                "activeShops": ["B"],
                "strategyPurpose": "replenishment-source-only",
            }
        }
        self.assertEqual(evidence_active_shops(payload), ["B"])
        self.assertEqual(evidence_highwater_filename(payload), "aipr_replenishment_evidence_highwater.json")
        self.assertEqual(evidence_output_prefix(payload), "aipr_verified_creators_replenishment")

    def test_regular_evidence_keeps_existing_file_contract(self):
        payload = {"strategy": {}}
        self.assertEqual(evidence_active_shops(payload), ["A", "B"])
        self.assertEqual(evidence_highwater_filename(payload), "aipr_evidence_highwater.json")
        self.assertEqual(evidence_output_prefix(payload), "aipr_verified_creators")

    def test_resume_does_not_restore_creators_removed_from_the_fresh_source_pool(self):
        base = [{"identity": "kept", "nickname": "A"}]
        prior = [
            {"identity": "kept", "content_evidence_reviewed": True},
            {"identity": "removed", "content_evidence_reviewed": True},
        ]
        merged = merge_evidence_highwater(base, prior)
        self.assertEqual([row["identity"] for row in merged], ["kept"])
        self.assertTrue(merged[0]["content_evidence_reviewed"])

    def test_skips_creators_whose_content_evidence_is_already_verified(self):
        rows = [
            {"identity": "1", "content_evidence_reviewed": True},
            {"identity": "2", "content_evidence_reviewed": False, "evidence_status": "content_unverified"},
            {"identity": "3"},
        ]
        self.assertEqual([row["identity"] for row in pending_evidence_candidates(rows)], ["3"])

    def test_partitions_two_shop_work_without_duplicates(self):
        rows = [{"identity": "1", "shop": "A"}, {"identity": "2", "shop": "B"}, {"identity": "3"}]
        grouped = partition_evidence_by_shop(rows)
        identities = [row["identity"] for shop_rows in grouped.values() for row in shop_rows]
        self.assertEqual(sorted(identities), ["1", "2", "3"])
        self.assertIn("1", [row["identity"] for row in grouped["A"]])
        self.assertIn("2", [row["identity"] for row in grouped["B"]])

    def test_preserves_source_shop_for_encrypted_creator_identity(self):
        rows = [{"identity": str(index), "shop": "A"} for index in range(10)]

        grouped = partition_evidence_by_shop(rows)

        self.assertEqual(len(grouped["A"]), 10)
        self.assertEqual(len(grouped["B"]), 0)
        identities = [row["identity"] for shop_rows in grouped.values() for row in shop_rows]
        self.assertEqual(sorted(identities), sorted(row["identity"] for row in rows))

    def test_uses_only_active_shop_for_evidence_work(self):
        rows = [{"identity": str(index), "shop": "A"} for index in range(10)]

        grouped = partition_evidence_by_shop(rows, active_shops=["A"])

        self.assertEqual(len(grouped["A"]), 10)
        self.assertEqual(len(grouped["B"]), 0)

    def test_splits_each_shop_into_two_non_overlapping_lanes(self):
        rows = [{"identity": str(index), "shop": "A" if index % 2 else "B"} for index in range(12)]
        lanes = partition_evidence_lanes(rows, 2)
        identities = [row["identity"] for _shop, lane in lanes for row in lane]
        self.assertEqual(len(lanes), 4)
        self.assertEqual(sorted(identities), sorted(row["identity"] for row in rows))

    def test_serializes_cdp_handshakes_before_parallel_lane_work(self):
        state = {"active": 0, "maximum": 0}

        class BrowserType:
            def connect_over_cdp(self, endpoint):
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                time.sleep(0.02)
                state["active"] -= 1
                return endpoint

        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(
                lambda _: connect_over_cdp_serialized(BrowserType(), "shop-a", lock),
                range(4),
            ))
        self.assertEqual(results, ["shop-a"] * 4)
        self.assertEqual(state["maximum"], 1)

    def test_direct_douyin_link_uses_a_lane_owned_page(self):
        profile_page = Mock()
        profile_page.content.return_value = '<a href="https://www.douyin.com/user/stable-id">达人抖音主页</a>'
        owned_page = Mock()
        context = Mock()
        context.new_page.return_value = owned_page

        opened, url, method = open_owned_douyin_page(context, profile_page)

        self.assertIs(opened, owned_page)
        self.assertEqual(url, "https://www.douyin.com/user/stable-id")
        self.assertEqual(method, "direct-profile-link")
        owned_page.goto.assert_called_once()

    def test_retry_clears_stale_error_details_before_reclassifying(self):
        result = verify_one(Mock(), {"identity": "x", "evidence_error": "old failure"}, Path("unused"), [])

        self.assertEqual(result["evidence_status"], "missing_buyin_profile")
        self.assertNotIn("evidence_error", result)

    def test_missing_direct_link_does_not_claim_another_parallel_lane_page(self):
        profile_page = Mock()
        profile_page.content.return_value = "<main>没有抖音主页链接</main>"
        profile_page.get_by_text.return_value.count.return_value = 0
        context = Mock()

        opened, url, method = open_owned_douyin_page(context, profile_page)

        self.assertIsNone(opened)
        self.assertEqual(url, "")
        self.assertEqual(method, "")
        context.new_page.assert_not_called()

    def test_text_douyin_button_uses_popup_owned_by_the_profile_page(self):
        profile_page = Mock()
        profile_page.content.return_value = "<main>douyin profile button</main>"
        node = Mock()
        node.is_visible.return_value = True
        locator = Mock()
        locator.count.return_value = 1
        locator.nth.return_value = node
        profile_page.get_by_text.return_value = locator
        opened = Mock()
        opened.url = "https://www.douyin.com/user/popup-owned"
        popup_info = Mock()
        popup_info.value = opened
        popup_context = Mock()
        popup_context.__enter__ = Mock(return_value=popup_info)
        popup_context.__exit__ = Mock(return_value=False)
        profile_page.expect_popup.return_value = popup_context

        result, url, method = open_owned_douyin_page(Mock(), profile_page)

        self.assertIs(result, opened)
        self.assertEqual(url, "https://www.douyin.com/user/popup-owned")
        self.assertTrue(method.startswith("popup:text:"))
        node.click.assert_called_once()

    def test_evidence_disk_budget_scales_with_pending_candidates(self):
        self.assertGreater(required_evidence_free_bytes(200), required_evidence_free_bytes(20))
        self.assertGreaterEqual(required_evidence_free_bytes(20), 256 * 1024 * 1024)

    def test_low_disk_space_is_rejected_before_browser_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(OSError, "insufficient disk space"):
                ensure_evidence_free_space(
                    Path(temp_dir),
                    100,
                    free_bytes=64 * 1024 * 1024,
                )

    def test_only_verified_content_keeps_visual_evidence(self):
        self.assertTrue(should_capture_evidence_screenshots({"content_evidence_reviewed": True}))
        self.assertFalse(should_capture_evidence_screenshots({"content_evidence_reviewed": False}))
        self.assertFalse(should_capture_evidence_screenshots({"evidence_status": "error"}))

    def test_douyin_boilerplate_is_not_content_evidence(self):
        text = "搜索 Ta 的作品\n登录后免费畅享高清视频\n关注 私信 作品 88"
        self.assertEqual(meaningful_lines(text, ["提臀裤", "塑形内衣"]), [])

    def test_real_underwear_video_copy_is_content_evidence(self):
        text = "真人试穿高腰提臀裤，收腹塑形效果对比很明显"
        self.assertEqual(meaningful_lines(text, ["提臀裤", "塑形内衣"]), [text])

    def test_buyin_beauty_history_is_content_evidence(self):
        text = "皮肤晒黑晒红用面膜护理\n黄黑皮口红试色与精致妆容教程"

        self.assertEqual(meaningful_lines(text, ["唇部护理"]), text.splitlines())

    def test_beauty_platform_fields_are_preserved_as_authoritative_evidence(self):
        base = [{"identity": "beauty-female", "evidence_status": "pending"}]
        updates = [{
            "identity": "beauty-female",
            "content_evidence_reviewed": True,
            "content_evidence": [
                "平台性别：女性",
                "平台主营类目：美妆",
                "平台联系方式：可查看",
            ],
            "evidence_status": "verified",
            "evidence_gate": {"beauty_vertical_verified": True},
        }]

        merged = merge_evidence_candidate_updates(base, updates)

        self.assertTrue(merged[0]["content_evidence_reviewed"])
        self.assertTrue(merged[0]["evidence_gate"]["beauty_vertical_verified"])

    def test_structured_beauty_candidate_still_requires_content_review(self):
        candidate = {
            "identity": "strict-beauty",
            "gender": 2,
            "category": "个护家清",
            "contact_visible": True,
        }

        result = apply_structured_beauty_evidence(candidate, ["唇部护理"])

        self.assertEqual(result["evidence_status"], "metadata_verified_pending_content")
        self.assertEqual(result["content_evidence_source"], "buyin_search_response")
        self.assertFalse(result["content_evidence_reviewed"])
        self.assertTrue(result["evidence_gate"]["contact_visibility_verified"])

    def test_structured_beauty_candidate_rejects_wrong_gender(self):
        candidate = {
            "identity": "male-beauty",
            "gender": 1,
            "category": "美妆",
            "contact_visible": True,
        }

        result = apply_structured_beauty_evidence(candidate, ["唇部护理"])

        self.assertNotIn("content_evidence_reviewed", result)

    def test_stale_verified_boilerplate_is_returned_to_pending_review(self):
        rows = [{
            "identity": "stale",
            "content_evidence_reviewed": True,
            "evidence_status": "verified",
            "douyin_content_text": "搜索 Ta 的作品 登录后免费畅享高清视频",
            "content_evidence": ["搜索 Ta 的作品"],
        }]
        refreshed = invalidate_stale_content_evidence(rows, ["提臀裤", "塑形内衣"])
        self.assertFalse(refreshed[0]["content_evidence_reviewed"])
        self.assertEqual(refreshed[0]["evidence_status"], "pending")

    def test_legacy_evidence_without_current_contract_is_rechecked(self):
        rows = [{
            "identity": "legacy",
            "content_evidence_reviewed": True,
            "evidence_status": "verified",
            "douyin_content_text": "真人试穿提臀塑形裤，收腹效果明显",
            "content_evidence": ["真人试穿提臀塑形裤，收腹效果明显"],
        }]

        refreshed = invalidate_stale_content_evidence(rows, ["提臀裤", "塑形内衣"])

        self.assertFalse(refreshed[0]["content_evidence_reviewed"])
        self.assertEqual(refreshed[0]["evidence_status"], "pending")

    def test_unverified_result_without_douyin_homepage_is_retried(self):
        rows = [
            {
                "identity": "redirected",
                "content_evidence_reviewed": False,
                "evidence_contract_version": 4,
                "evidence_status": "content_unverified",
                "douyin_homepage": "",
                "content_evidence": [],
            },
            {
                "identity": "genuine-mismatch",
                "content_evidence_reviewed": False,
                "evidence_contract_version": 4,
                "evidence_status": "content_unverified",
                "douyin_homepage": "https://www.douyin.com/user/real",
                "content_evidence": [],
            },
        ]

        refreshed = invalidate_stale_content_evidence(rows, ["提臀裤"])

        self.assertEqual(refreshed[0]["evidence_status"], "pending")
        self.assertEqual(refreshed[1]["evidence_status"], "content_unverified")

    def test_evidence_profile_session_rejects_redirected_storefront(self):
        self.assertFalse(evidence_profile_session_ready("https://www.douyinec.com/", "抖音电商官网"))
        self.assertTrue(evidence_profile_session_ready(
            "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=1",
            "达人自主披露联系方式 粉丝数 带货口碑",
        ))

    def test_empty_new_evidence_overwrites_stale_old_evidence(self):
        base = [{
            "identity": "same",
            "content_evidence_reviewed": True,
            "content_evidence": ["old unrelated evidence"],
            "evidence_status": "verified",
        }]
        updates = [{
            "identity": "same",
            "content_evidence_reviewed": False,
            "content_evidence": [],
            "evidence_status": "content_unverified",
            "evidence_contract_version": 2,
        }]

        merged = merge_evidence_candidate_updates(base, updates)

        self.assertFalse(merged[0]["content_evidence_reviewed"])
        self.assertEqual(merged[0]["content_evidence"], [])
        self.assertEqual(merged[0]["evidence_status"], "content_unverified")

    def test_lane_failure_is_collected_without_aborting_other_lanes(self):
        succeeded = Future()
        succeeded.set_result(None)
        failed = Future()
        failed.set_exception(RuntimeError("lane disconnected"))

        failures = wait_for_lane_futures([succeeded, failed])

        self.assertEqual(len(failures), 1)
        self.assertIn("lane disconnected", str(failures[0]))


if __name__ == "__main__":
    unittest.main()
