from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from verify_osmana_douyin_content_cdp import (
    extract_content_evidence,
    extract_douyin_profile_intro,
    screenshot_filename,
    save,
    select_product_evidence_candidates,
    validate_product_evidence_input,
)


class VerifyOsmanaDouyinContentTest(unittest.TestCase):
    def test_saved_strict_evidence_recomputes_precontact_qualification(self) -> None:
        candidate = {
            "identity": "ready-for-contact",
            "shop": "A",
            "talent_level": "LV3",
            "main_sale_type": "纯短视频",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "douyin_content_text": "真人口播 内衣试穿",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 50000,
                "related_video_num": 3,
                "related_live_times": 0,
            }],
            "precontact_qualified": False,
        }
        strategy = {
            "brief": "内衣单品近30天短视频销售额不少于1万元",
            "creatorLevels": [2, 3, 4],
            "minimumUnderwearProductSales": 10000,
            "minimumLevel": 2,
            "requireBodyMeasurements": False,
            "requireShapewearContent": False,
            "requirePlainContact": True,
        }

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "strict.json"
            save({"strategy": strategy}, [candidate], strategy, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(saved["candidates"][0]["precontact_qualified"])

    def test_rejects_raw_queue_without_buyin_product_evidence(self) -> None:
        rows = [{
            "identity": "raw-candidate",
            "shop": "A",
            "talent_level": "LV2",
            "buyin_profile_url": "https://buyin.example/profile",
        }]

        with self.assertRaisesRegex(ValueError, "missing Buyin product evidence"):
            validate_product_evidence_input(rows)

    def test_extracts_only_douyin_profile_intro_for_body_evidence(self) -> None:
        text = (
            "开启读屏标签 白鹤芋 关注 粉丝 获赞 抖音号：baibaix_x "
            "IP属地：陕西 166/98 健身 | 户外 | 日常休闲穿搭分享 关注 私信 "
            "作品 481 推荐 喜欢 最新作品 165cm 49kg适用塑形裤"
        )

        self.assertEqual(
            extract_douyin_profile_intro(text),
            "166/98 健身 | 户外 | 日常休闲穿搭分享",
        )

    def test_extracts_shapewear_relevant_recent_content(self) -> None:
        text = """晓晓\n作品\n高腰收腹提臀塑形裤真人上身前后对比\n夏季防晒帽分享\n产后妈妈臀这样穿臀线更好看"""
        evidence = extract_content_evidence(text)
        self.assertEqual(len(evidence), 2)
        self.assertIn("收腹提臀", evidence[0])

    def test_rejects_unrelated_product_copy(self) -> None:
        self.assertEqual(extract_content_evidence("厨房收纳盒很好用\n夏季防晒帽"), [])

    def test_relaxed_persona_accepts_underwear_or_oral_content(self) -> None:
        evidence = extract_content_evidence(
            "无痕内衣上身展示\n真人口播测评通勤穿搭",
            require_shapewear=False,
        )

        self.assertEqual(len(evidence), 2)
        self.assertIn("真人口播", evidence[1])

    def test_rechecks_stale_product_evaluation_before_douyin_review(self) -> None:
        candidate = {
            "shop": "B",
            "talent_level": "LV3",
            "products_30d": [{
                "title": "女童夏季安全裤套装",
                "sales_low": 50000,
                "sales_high": 100000,
                "related_video_num": 8,
                "related_live_times": 0,
            }],
            "osmana_evaluation": {"underwear_product_sales_low": 50000},
        }
        strategy = {
            "minimumLevel": 2,
            "minimumUnderwearProductSales": 10000,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "requirePlainContact": True,
        }

        selected, refreshed = select_product_evidence_candidates([candidate], strategy, "B", 0)

        self.assertEqual(selected, [])
        self.assertEqual(refreshed[0]["osmana_evaluation"]["underwear_product_sales_low"], 0)

    def test_resume_skips_terminal_content_reviews(self) -> None:
        base = {
            "shop": "B",
            "talent_level": "LV3",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 50000,
                "related_video_num": 3,
                "related_live_times": 0,
            }],
        }
        rows = [
            {**base, "identity": "done", "douyin_evidence_status": "verified", "content_evidence_screenshot": "C:/frames/done_0123456789_douyin.jpg"},
            {**base, "identity": "unmatched", "douyin_evidence_status": "content_not_matched", "content_evidence_screenshot": "C:/frames/unmatched_abcdef0123_douyin.jpg"},
            {**base, "identity": "legacy", "douyin_evidence_status": "verified", "content_evidence_screenshot": "C:/frames/同名达人_douyin.jpg"},
            {**base, "identity": "pending"},
        ]
        strategy = {"minimumUnderwearProductSales": 10000, "requirePlainContact": False}

        selected, _ = select_product_evidence_candidates(rows, strategy, "B", 0)

        self.assertEqual([row["identity"] for row in selected], ["legacy", "pending"])

    def test_screenshot_filename_is_unique_for_duplicate_nicknames(self) -> None:
        first = screenshot_filename({"nickname": "同名达人", "identity": "identity-a"})
        second = screenshot_filename({"nickname": "同名达人", "identity": "identity-b"})

        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("_douyin.jpg"))

    def test_accepts_underwear_sales_equal_to_minimum_threshold(self) -> None:
        candidate = {
            "identity": "threshold-candidate",
            "shop": "A",
            "talent_level": "LV2",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 10000,
                "related_video_num": 2,
                "related_live_times": 0,
            }],
        }
        strategy = {
            "minimumUnderwearProductSales": 10000,
            "requirePlainContact": False,
        }

        selected, _ = select_product_evidence_candidates([candidate], strategy, "A", 0)

        self.assertEqual([row["identity"] for row in selected], ["threshold-candidate"])

    def test_prioritizes_candidates_with_complete_body_evidence(self) -> None:
        product = [{
            "title": "高腰收腹提臀塑形裤",
            "sales_low": 50000,
            "related_video_num": 3,
            "related_live_times": 0,
        }]
        rows = [
            {"identity": "missing-body", "shop": "B", "talent_level": "LV3", "products_30d": product},
            {"identity": "complete-body", "shop": "B", "talent_level": "LV3", "profile_text": "165cm 49kg", "products_30d": product},
        ]
        strategy = {
            "minimumUnderwearProductSales": 10000,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "requirePlainContact": False,
        }

        selected, _ = select_product_evidence_candidates(rows, strategy, "B", 0)

        self.assertEqual([row["identity"] for row in selected], ["complete-body", "missing-body"])

    def test_refreshes_body_evidence_from_existing_douyin_profile_text(self) -> None:
        product = [{
            "title": "高腰收腹提臀塑形裤",
            "sales_low": 50000,
            "related_video_num": 3,
            "related_live_times": 0,
        }]
        row = {
            "identity": "douyin-body",
            "shop": "B",
            "talent_level": "LV3",
            "products_30d": product,
            "douyin_content_text": (
                "抖音号：sample IP属地：浙江 165/50kg 梨形身材真人试穿 "
                "关注 私信 作品 88 推荐 喜欢"
            ),
        }
        strategy = {
            "minimumUnderwearProductSales": 10000,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "requirePlainContact": False,
        }

        selected, refreshed = select_product_evidence_candidates([row], strategy, "B", 0)

        self.assertEqual(selected[0]["osmana_evaluation"]["height_cm"], 165.0)
        self.assertEqual(refreshed[0]["osmana_evaluation"]["weight_jin"], 100.0)
        self.assertEqual(refreshed[0]["profile_intro_source"], "douyin_homepage")

    def test_keeps_buyin_body_evidence_when_douyin_intro_has_no_measurements(self) -> None:
        product = [{
            "title": "高腰收腹提臀塑形裤",
            "sales_low": 50000,
            "related_video_num": 3,
            "related_live_times": 0,
        }]
        row = {
            "identity": "buyin-body",
            "shop": "B",
            "talent_level": "LV3",
            "profile_text": "达人简介：身高163 体重85斤 真人试穿 达人手机号：*********** 概览",
            "products_30d": product,
            "douyin_content_text": (
                "抖音号：sample IP属地：浙江 分享欲爆棚的穿搭博主 "
                "关注 私信 作品 88 推荐 喜欢"
            ),
        }
        strategy = {
            "minimumUnderwearProductSales": 10000,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "requirePlainContact": False,
        }

        _, refreshed = select_product_evidence_candidates([row], strategy, "B", 0)

        self.assertEqual(refreshed[0]["osmana_evaluation"]["height_cm"], 163.0)
        self.assertEqual(refreshed[0]["osmana_evaluation"]["weight_jin"], 85.0)
        self.assertNotEqual(refreshed[0].get("profile_intro_source"), "douyin_homepage")

    def test_deduplicates_same_public_douyin_account_before_review(self) -> None:
        product = [{
            "title": "高腰收腹提臀塑形裤",
            "sales_low": 50000,
            "related_video_num": 3,
            "related_live_times": 0,
        }]
        rows = [
            {"identity": "encrypted-a", "douyin_id": "same-douyin", "shop": "B", "talent_level": "LV3", "products_30d": product},
            {"identity": "encrypted-b", "douyin_id": "same-douyin", "shop": "B", "talent_level": "LV3", "products_30d": product},
        ]
        strategy = {"minimumUnderwearProductSales": 10000, "requirePlainContact": False}

        selected, _ = select_product_evidence_candidates(rows, strategy, "B", 0)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["douyin_id"], "same-douyin")


if __name__ == "__main__":
    unittest.main()
