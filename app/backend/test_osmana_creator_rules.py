from __future__ import annotations

import unittest

from osmana_creator_rules import (
    evaluate_osmana_candidate,
    extract_profile_intro,
    extract_height_weight,
    is_underwear_product,
)


class OsmanaCreatorRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = {
            "minimumLevel": 2,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "minimumUnderwearProductSales": 10000,
            "requirePlainContact": True,
        }

    def candidate(self) -> dict:
        return {
            "nickname": "测试达人",
            "talent_level": "LV2",
            "main_sale_type": "纯短视频",
            "profile_text": "达人简介：170/52kg，一般M码，真人试穿测评",
            "douyin_homepage": "https://www.douyin.com/user/example",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "douyin_content_text": "久坐臀型管理，收腹提臀塑形裤真人上身前后对比",
            "buyin_contact_wechat": "osmana_test",
            "products_30d": [
                {
                    "title": "高腰收腹提臀塑形裤女",
                    "sales_low": 10001,
                    "sales_high": 25000,
                    "related_video_num": 3,
                    "related_live_times": 0,
                }
            ],
        }

    def test_extracts_metric_height_and_weight(self) -> None:
        self.assertEqual(extract_height_weight("170/52kg，一般M码"), (170.0, 104.0))
        self.assertEqual(extract_height_weight("身高160cm 体重95斤"), (160.0, 95.0))
        self.assertEqual(extract_height_weight("身高163 体重85斤"), (163.0, 85.0))
        self.assertEqual(extract_height_weight("167/112 梨形身材"), (167.0, 112.0))
        self.assertEqual(extract_height_weight("170/98 真人试穿"), (170.0, 98.0))

    def test_extracts_only_creator_intro_from_full_buyin_page(self) -> None:
        page = "达人简介：🎀168cm / 52kg 梨形身材 达人手机号：*********** 概览 商品规格20kg"
        intro = extract_profile_intro(page)
        self.assertEqual(intro, "🎀168cm / 52kg 梨形身材")
        self.assertEqual(extract_height_weight(intro), (168.0, 104.0))

    def test_ignores_body_like_numbers_outside_creator_intro(self) -> None:
        row = self.candidate()
        row["profile_text"] = "达人简介：真人试穿 达人手机号：*********** 概览 商品标题165cm 49kg适用"
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertIsNone(result["height_cm"])
        self.assertIsNone(result["weight_jin"])
        self.assertIn("missing_height_evidence", result["failures"])

    def test_underwear_product_requires_specific_underwear_language(self) -> None:
        self.assertTrue(is_underwear_product("高腰收腹提臀塑形裤女"))
        self.assertTrue(is_underwear_product("无钢圈聚拢文胸"))
        self.assertFalse(is_underwear_product("夏季显瘦女款短袖T恤"))
        self.assertFalse(is_underwear_product("厚底洞洞鞋女"))

    def test_rejects_lv1(self) -> None:
        row = self.candidate()
        row["talent_level"] = "LV1"
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("level_below_2", result["failures"])

    def test_accepts_lv5_as_lv2_or_above(self) -> None:
        row = self.candidate()
        row["talent_level"] = "LV5"
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertTrue(result["qualified"])

    def test_rejects_out_of_range_body_measurements(self) -> None:
        row = self.candidate()
        row["profile_text"] = "达人简介：172cm 56kg，真人试穿测评"
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("height_out_of_range", result["failures"])
        self.assertIn("weight_out_of_range", result["failures"])

    def test_body_measurements_can_be_disabled_by_brand_strategy(self) -> None:
        row = self.candidate()
        row["profile_text"] = "达人简介：女性真人内衣试穿测评"
        strategy = {**self.strategy, "requireBodyMeasurements": False}

        result = evaluate_osmana_candidate(row, strategy)

        self.assertTrue(result["qualified"])
        self.assertNotIn("missing_height_evidence", result["failures"])
        self.assertNotIn("missing_weight_evidence", result["failures"])

    def test_rejects_underwear_product_at_9999(self) -> None:
        row = self.candidate()
        row["products_30d"][0]["sales_low"] = 9999
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("underwear_product_sales_not_above_10000", result["failures"])

    def test_accepts_underwear_product_at_10001(self) -> None:
        result = evaluate_osmana_candidate(self.candidate(), self.strategy)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["underwear_product_sales_low"], 10001)
        self.assertEqual(result["height_cm"], 170.0)
        self.assertEqual(result["weight_jin"], 104.0)

    def test_accepts_underwear_product_at_exact_minimum(self) -> None:
        row = self.candidate()
        row["products_30d"][0]["sales_low"] = 10000

        result = evaluate_osmana_candidate(row, self.strategy)

        self.assertTrue(result["qualified"])
        self.assertEqual(result["underwear_product_sales_low"], 10000)

    def test_rejects_missing_plain_contact(self) -> None:
        row = self.candidate()
        row.pop("buyin_contact_wechat")
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("missing_plain_contact", result["failures"])

    def test_rejects_content_without_verified_real_person_visuals(self) -> None:
        row = self.candidate()
        row.pop("visual_persona_verified")
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("visual_persona_unverified", result["failures"])

    def test_allows_generic_real_person_oral_content_when_product_relevance_is_optional(self) -> None:
        row = self.candidate()
        row["douyin_content_text"] = "真人正面口播服饰好物，稳定出镜展示"
        strategy = {
            **self.strategy,
            "requireBodyMeasurements": False,
            "requireShapewearContent": False,
        }

        result = evaluate_osmana_candidate(row, strategy)

        self.assertTrue(result["qualified"])
        self.assertNotIn("content_not_shapewear_relevant", result["failures"])

    def test_rejects_underwear_sales_with_live_association(self) -> None:
        row = self.candidate()
        row["products_30d"][0]["related_live_times"] = 2
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("short_video_underwear_sales_not_above_10000", result["failures"])

    def test_rejects_underwear_sales_without_short_video(self) -> None:
        row = self.candidate()
        row["products_30d"][0]["related_video_num"] = 0
        result = evaluate_osmana_candidate(row, self.strategy)
        self.assertFalse(result["qualified"])
        self.assertIn("short_video_underwear_sales_not_above_10000", result["failures"])

    def test_rejects_creator_with_live_content(self) -> None:
        row = self.candidate()
        row["main_sale_type"] = "直播为主"
        row["profile_text"] += " 内容数据 直播 12个；20万次 视频 30个；100万次"

        result = evaluate_osmana_candidate(row, self.strategy)

        self.assertFalse(result["qualified"])
        self.assertIn("creator_not_short_video_only", result["failures"])

    def test_accepts_profile_evidence_with_zero_live_content(self) -> None:
        row = self.candidate()
        row.pop("main_sale_type")
        row["profile_text"] += " 内容数据 直播 0个；0次 视频 30个；100万次"

        result = evaluate_osmana_candidate(row, self.strategy)

        self.assertTrue(result["qualified"])

    def test_rejects_male_child_and_pregnancy_underwear_products(self) -> None:
        for title in ("男士抗菌内裤", "女童安全裤", "儿童打底裤", "孕妇哺乳文胸"):
            row = self.candidate()
            row["products_30d"][0]["title"] = title
            result = evaluate_osmana_candidate(row, self.strategy)
            self.assertFalse(result["qualified"], title)
            self.assertIn("short_video_underwear_sales_not_above_10000", result["failures"])


    def test_rejects_teen_underwear_product(self) -> None:
        row = self.candidate()
        row["products_30d"][0]["title"] = "青少年冰丝内裤"

        result = evaluate_osmana_candidate(row, self.strategy)

        self.assertFalse(result["qualified"])
        self.assertIn("short_video_underwear_sales_not_above_10000", result["failures"])

    def test_rejects_minor_girl_underwear_product_variants(self) -> None:
        titles = (
            "12-18岁发育期少女内衣",
            "女学生专用无痕文胸",
            "少女小背心夏季薄款内衣",
        )
        for title in titles:
            with self.subTest(title=title):
                row = self.candidate()
                row["products_30d"][0]["title"] = title

                result = evaluate_osmana_candidate(row, self.strategy)

                self.assertFalse(result["qualified"])
                self.assertIn("short_video_underwear_sales_not_above_10000", result["failures"])


if __name__ == "__main__":
    unittest.main()
