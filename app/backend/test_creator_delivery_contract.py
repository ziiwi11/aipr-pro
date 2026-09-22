from __future__ import annotations

import unittest

from creator_delivery_contract import (
    build_delivery,
    content_blocked,
    extract_sales_lower,
    extract_short_video_sales_lower,
    mark_precontact_qualification,
    score_candidate,
)

class CreatorDeliveryContractTest(unittest.TestCase):
    def test_structured_beauty_fast_path_respects_expanded_task_exclusions(self) -> None:
        rules = {
            "category": "美妆个护",
            "exclusions": ["母婴", "男性", "美食", "品牌店铺", "宠物"],
        }
        base = {
            "gender": 2,
            "category": "美妆/个护家清",
            "contact_visible": True,
            "content_evidence_reviewed": True,
            "evidence_gate": {"beauty_vertical_verified": True},
        }
        samples = (
            ("兜兜妈（二胎孕晚期)", "母婴"),
            ("小豪（变帅版）", "男性"),
            ("思思（平遥特色手工月饼）", "美食"),
            ("韩妮雅个人护理工厂店", "品牌店铺"),
            ("淮北珊珊美妆店", "品牌店铺"),
            ("芮芮小卖部🍎", "品牌店铺"),
            ("萌宠小七护肤日记", "宠物"),
        )
        for nickname, expected in samples:
            result = score_candidate({**base, "nickname": nickname}, rules)
            self.assertTrue(result["excluded"])
            self.assertIn(expected, result["reason"])

    def test_underwear_product_brief_rejects_generic_total_gmv_fallback(self) -> None:
        candidate = {
            "identity": "shoe-creator",
            "talent_level": "LV3",
            "monthly_sales_value": 500000,
            "buyin_profile_url": "https://buyin.example/creator",
            "douyin_homepage": "https://douyin.example/creator",
            "content_evidence_reviewed": True,
            "content_evidence": ["真人口播 女鞋测评"],
            "buyin_contact_wechat": "wechat123",
        }
        rules = {
            "brief": "内衣单品近30天短视频销售额1万以上",
            "creatorLevels": [2, 3, 4],
            "minimumMonthlySales": 10000,
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertFalse(marked["precontact_qualified"])
        self.assertIn("内衣单品", marked["precontact_reason"])

    def test_underwear_product_brief_accepts_complete_strict_evidence(self) -> None:
        candidate = {
            "identity": "strict-underwear-creator",
            "talent_level": "LV3",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "buyin_contact_wechat": "wechat123",
            "osmana_evaluation": {
                "qualified": True,
                "failures": [],
                "level": 3,
                "underwear_product_sales_low": 50000,
                "underwear_product_title": "高腰收腹提臀塑形裤",
            },
        }
        rules = {
            "brief": "内衣单品近30天短视频销售额1万以上",
            "creatorLevels": [2, 3, 4],
            "minimumMonthlySales": 10000,
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertTrue(marked["precontact_qualified"])
        self.assertEqual(marked["precontact_sales"], 50000)

    def test_marks_creator_eligible_before_contact_without_weakening_final_contact_gate(self) -> None:
        candidate = {
            "identity": "precontact",
            "nickname": "塑形试穿达人",
            "category": "服饰内衣",
            "talent_level": "LV2",
            "buyin_profile_url": "https://buyin.example/profile/precontact",
            "douyin_homepage": "https://douyin.com/user/precontact",
            "profile_verified": True,
            "profile_text": "直播 0个；0次 视频 20件；¥2万-¥5万",
            "content_evidence_reviewed": True,
            "content_evidence": ["真人试穿 收腹提臀塑形裤 上身穿搭"],
        }
        rules = {
            "category": "服饰内衣",
            "creatorLevels": [2, 3, 4],
            "minimumMonthlySales": 10000,
            "contentType": "真人口播",
            "exclusions": ["直播"],
            "threshold": 78,
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertTrue(marked["precontact_qualified"])
        self.assertEqual(score_candidate(marked, rules)["decision"], "待补联系方式")

    def test_structured_beauty_creator_enters_internal_contact_queue(self) -> None:
        candidate = {
            "identity": "female-beauty",
            "gender": 2,
            "category": "个护家清",
            "contact_visible": True,
            "talent_level": "LV2",
            "content_evidence_reviewed": True,
            "content_evidence_source": "buyin_search_response",
            "evidence_gate": {"beauty_vertical_verified": True},
        }
        rules = {
            "category": "美妆个护",
            "creatorLevels": [1, 2, 3, 4],
            "contentType": "真人口播",
            "threshold": 78,
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertTrue(marked["precontact_qualified"])
        self.assertEqual(score_candidate(candidate, rules)["decision"], "待补联系方式")

    def test_structured_beauty_scope_accepts_beauty_label_and_keeps_sales_gate(self) -> None:
        candidate = {
            "identity": "female-beauty-video",
            "gender": 2,
            "category": "美妆",
            "contact_visible": True,
            "talent_level": "LV2",
            "monthly_sales_value": 25000,
            "profile_verified": True,
            "content_evidence_reviewed": True,
            "content_evidence_source": "buyin_profile",
            "evidence_gate": {
                "beauty_vertical_verified": True,
                "buyin_content_count": 12,
            },
        }
        rules = {
            "category": "美妆",
            "creatorLevels": [1, 2, 3, 4],
            "minimumMonthlySales": 10000,
            "contentType": "视频达人",
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertTrue(marked["precontact_qualified"])
        self.assertEqual(marked["precontact_sales"], 25000)

        below_sales = mark_precontact_qualification(
            {**candidate, "identity": "female-beauty-low-sales", "monthly_sales_value": 5000},
            rules,
        )
        self.assertFalse(below_sales["precontact_qualified"])
        self.assertIn("销售额", below_sales["precontact_reason"])

    def test_structured_beauty_delivery_still_requires_plain_contact(self) -> None:
        candidate = {
            "identity": "female-beauty-contact",
            "gender": 2,
            "category": "美妆",
            "contact_visible": True,
            "talent_level": "LV3",
            "content_evidence_reviewed": True,
            "evidence_gate": {"beauty_vertical_verified": True},
            "buyin_contact_wechat": "creator_wechat_123",
        }
        rules = {"category": "美妆个护", "creatorLevels": [1, 2, 3, 4]}

        self.assertEqual(score_candidate(candidate, rules)["decision"], "推荐建联")

    def test_strict_underwear_precontact_recomputes_evaluation_with_contact_probe(self) -> None:
        candidate = {
            "identity": "strict-precontact",
            "talent_level": "LV3",
            "main_sale_type": "纯短视频",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "douyin_content_text": "真人口播 内衣试穿",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 10000,
                "sales_high": 25000,
                "related_video_num": 3,
                "related_live_times": 0,
            }],
        }
        rules = {
            "brief": "内衣单品近30天短视频销售额不少于1万元",
            "creatorLevels": [2, 3, 4],
            "minimumUnderwearProductSales": 10000,
            "minimumLevel": 2,
            "requireBodyMeasurements": False,
            "requireShapewearContent": False,
            "requirePlainContact": True,
        }

        marked = mark_precontact_qualification(candidate, rules)

        self.assertTrue(marked["precontact_qualified"])
        self.assertEqual(marked["precontact_sales"], 10000)
    def test_extract_sales_lower_reads_buyin_ten_thousand_range(self) -> None:
        self.assertEqual(extract_sales_lower("视频带货 结算总额 ¥10万~25万"), 100000)
        self.assertEqual(extract_sales_lower("综合匹配度：- ..."), 0)

    def test_sales_parser_ignores_profile_date_and_reads_short_video_gmv(self) -> None:
        profile = (
            "数据统计时间：2026/06/18 至 2026/07/18 "
            "带货数据 79 带货商品总数 ¥2.5万-5万 结算总额 "
            "直播 0件；- 视频 69件；¥5万-¥10万 图文 7件；¥1,000-¥2,500"
        )
        self.assertEqual(extract_sales_lower(profile), 50000)
        self.assertEqual(extract_short_video_sales_lower(profile), 50000)

    def test_content_blocked_ignores_hidden_login_ui_when_works_are_loaded(self) -> None:
        self.assertTrue(content_blocked("验证码登录", [], ["验证码"]))
        self.assertFalse(content_blocked("登录 #护发精油作品", ["#护发精油作品"], ["验证码", "登录"]))

    def test_score_candidate_rejects_hard_exclusion(self) -> None:
        result = score_candidate(
            {"nickname": "母婴好物", "profile_text": "母婴育儿分享"},
            {"exclusions": ["母婴"], "threshold": 78},
        )

        self.assertTrue(result["excluded"])
        self.assertEqual(result["decision"], "淘汰")

    def test_build_delivery_requires_verified_content_before_recommendation(self) -> None:
        candidates = [{
            "identity": "creator-1",
            "nickname": "测试达人",
            "talent_level": "3",
            "buyin_profile_url": "https://buyin.example/profile/1",
            "douyin_homepage": "https://www.douyin.com/user/1",
            "profile_verified": True,
            "content_evidence_reviewed": False,
            "monthly_sales_value": 200000,
            "buyin_contact_wechat": "wx_test",
            "buyin_contact_phone": "13800000000",
        }]

        delivery = build_delivery(candidates, {"threshold": 78, "exclusions": []}, "task-1")

        self.assertEqual(delivery["candidate_count"], 1)
        self.assertEqual(delivery["recommended_count"], 0)
        self.assertEqual(delivery["rows"][0]["推荐结论"], "待内容复核")
        self.assertEqual(delivery["rows"][0]["微信"], "wx_test")
        self.assertEqual(delivery["robot_queue"], [])

    def test_build_delivery_creates_robot_record_for_verified_high_score_creator(self) -> None:
        candidates = [{
            "identity": "creator-2",
            "nickname": "高匹配达人",
            "talent_level": "3",
            "buyin_profile_url": "https://buyin.example/profile/2",
            "douyin_homepage": "https://www.douyin.com/user/2",
            "profile_verified": True,
            "content_evidence_reviewed": True,
            "content_evidence": ["真人口播 唇部护理 精致场景"],
            "monthly_sales_value": 200000,
            "buyin_contact_wechat": "wx_high",
            "buyin_contact_phone": "13900000000",
        }]

        delivery = build_delivery(candidates, {"threshold": 78, "exclusions": []}, "task-2")

        self.assertEqual(delivery["recommended_count"], 1)
        self.assertEqual(delivery["rows"][0]["推荐结论"], "推荐建联")
        robot = delivery["robot_queue"][0]
        self.assertEqual(robot["schemaVersion"], "aipr.robot.outreach.v1")
        self.assertEqual(robot["event"], "creator.outreach.requested")
        self.assertEqual(robot["task"]["id"], "task-2")
        self.assertEqual(robot["creator"]["contact"]["wechat"], "wx_high")
        self.assertEqual(robot["creator"]["contact"]["phone"], "13900000000")
        self.assertEqual(robot["recommendation"]["fee"], 800)
        self.assertTrue(robot["guardrails"]["requiresHumanApprovalForFee"])

    def test_osmana_hard_failure_cannot_enter_robot_queue(self) -> None:
        candidate = {
            "identity": "osmana-rejected",
            "nickname": "超重塑形达人",
            "talent_level": "LV4",
            "buyin_profile_url": "https://buyin.example/profile/rejected",
            "douyin_homepage": "https://www.douyin.com/user/rejected",
            "content_evidence_reviewed": True,
            "buyin_contact_wechat": "wx_rejected",
            "osmana_evaluation": {
                "qualified": False,
                "failures": ["weight_out_of_range"],
                "level": 4,
                "weight_jin": 160,
                "underwear_product_sales_low": 250000,
            },
        }

        delivery = build_delivery([candidate], {"threshold": 78, "exclusions": []}, "osmana-task")

        self.assertEqual(delivery["recommended_count"], 0)
        self.assertEqual(delivery["rows"][0]["推荐结论"], "淘汰")
        self.assertEqual(delivery["robot_queue"], [])

    def test_osmana_delivery_exports_hard_evidence_and_brand_fee(self) -> None:
        candidate = {
            "identity": "osmana-qualified",
            "nickname": "真人塑形达人",
            "douyin_id": "81483398349",
            "talent_level": "LV3",
            "buyin_profile_url": "https://buyin.example/profile/qualified",
            "douyin_homepage": "https://www.douyin.com/user/qualified",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "content_evidence_screenshot": "C:/evidence/qualified.jpg",
            "buyin_contact_wechat": "wx_qualified",
            "osmana_evaluation": {
                "qualified": True,
                "failures": [],
                "level": 3,
                "height_cm": 165,
                "weight_jin": 98,
                "underwear_product_title": "高腰收腹提臀塑形裤",
                "underwear_product_sales_low": 50000,
                "underwear_product_sales_high": 100000,
                "underwear_product_evidence": {
                    "related_video_num": 6,
                    "related_live_times": 0,
                },
            },
        }
        rules = {
            "threshold": 78,
            "exclusions": [],
            "pricing": {"preferredMin": 300, "preferredMax": 400, "authorizationIncluded": True},
        }

        delivery = build_delivery([candidate], rules, "osmana-task")

        row = delivery["rows"][0]
        self.assertEqual(row["推荐结论"], "推荐建联")
        self.assertEqual(row["抖音号"], "81483398349")
        self.assertEqual(row["身高(cm)"], 165)
        self.assertEqual(row["体重(斤)"], 98)
        self.assertEqual(row["内衣单品近30天短视频销售额"], 50000)
        self.assertEqual(row["关联短视频数"], 6)
        self.assertEqual(row["关联直播场次"], 0)
        self.assertEqual(row["建议报价"], 350)
        self.assertEqual(row["授权要求"], "含授权")
        self.assertEqual(row["内容证据截图"], "C:/evidence/qualified.jpg")
        self.assertEqual(delivery["robot_queue_count"], 1)



if __name__ == "__main__":
    unittest.main()
