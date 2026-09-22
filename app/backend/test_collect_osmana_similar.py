from __future__ import annotations

import unittest

from collect_osmana_similar_cdp import (
    candidates_from_similar_payload,
    choose_seed_suggestion,
    reference_seeds_from_strategy,
    seed_search_query,
    select_similar_seeds,
    suggestions_from_payload,
)
from collect_osmana_candidates_cdp import precursor_eligible


class CollectOsmanaSimilarTest(unittest.TestCase):
    def test_selects_only_strict_body_content_and_visual_seeds(self) -> None:
        base = {
            "shop": "B",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "osmana_evaluation": {
                "height_cm": 165,
                "weight_jin": 100,
                "underwear_product_sales_low": 50000,
            },
        }
        rows = [
            {**base, "identity": "strict"},
            {**base, "identity": "no-visual", "visual_persona_verified": False},
            {**base, "identity": "no-body", "osmana_evaluation": {"underwear_product_sales_low": 50000}},
        ]

        selected = select_similar_seeds(rows, "B", 10)

        self.assertEqual([row["identity"] for row in selected], ["strict"])

    def test_allows_missing_body_when_brand_disables_measurement_filter(self) -> None:
        row = {
            "identity": "no-body-required",
            "shop": "A",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "osmana_evaluation": {"underwear_product_sales_low": 50000},
        }

        selected = select_similar_seeds(
            [row],
            "A",
            10,
            require_body_measurements=False,
        )

        self.assertEqual([item["identity"] for item in selected], ["no-body-required"])

    def test_allows_explicit_reference_seed_without_final_sales_evidence(self) -> None:
        row = {
            "identity": "reference-only",
            "shop": "A",
            "reference_seed_only": True,
            "osmana_evaluation": {"underwear_product_sales_low": 0},
        }

        selected = select_similar_seeds(
            [row],
            "A",
            10,
            require_body_measurements=False,
            allow_reference_seeds=True,
        )

        self.assertEqual([item["identity"] for item in selected], ["reference-only"])

    def test_allows_generic_precontact_qualified_seed_when_body_filter_is_disabled(self) -> None:
        row = {
            "identity": "generic-qualified",
            "shop": "B",
            "precontact_qualified": True,
            "precontact_sales": 50000,
            "content_evidence_reviewed": True,
            "content_evidence": ["真人试穿提臀塑形裤"],
            "buyin_profile_url": "https://buyin.jinritemai.com/daren-profile?uid=1",
        }
        selected = select_similar_seeds([row], "B", 10, require_body_measurements=False)
        self.assertEqual([item["identity"] for item in selected], ["generic-qualified"])

    def test_cross_shop_seed_selection_can_reuse_verified_seeds_in_logged_in_shop(self) -> None:
        row = {
            "identity": "verified-in-b",
            "shop": "B",
            "precontact_qualified": True,
            "precontact_sales": 50000,
            "content_evidence_reviewed": True,
            "content_evidence": ["无痕内衣真人试穿"],
            "buyin_profile_url": "https://buyin.jinritemai.com/daren-profile?uid=1",
        }

        selected = select_similar_seeds(
            [row],
            "A",
            10,
            require_body_measurements=False,
            allow_cross_shop=True,
        )

        self.assertEqual([item["identity"] for item in selected], ["verified-in-b"])

    def test_seed_selection_prioritizes_target_product_evidence(self) -> None:
        base = {
            "shop": "A",
            "precontact_qualified": True,
            "precontact_sales": 50000,
            "content_evidence_reviewed": True,
            "buyin_profile_url": "https://buyin.jinritemai.com/daren-profile?uid=1",
        }
        rows = [
            {**base, "identity": "generic", "nickname": "泛好物", "content_evidence": ["日常好物分享"]},
            {**base, "identity": "target", "nickname": "塑形达人", "content_evidence": ["真人试穿提臀收腹塑形裤"]},
        ]

        selected = select_similar_seeds(rows, "A", 1, require_body_measurements=False)

        self.assertEqual([item["identity"] for item in selected], ["target"])

    def test_rejects_seed_whose_only_evidence_is_douyin_boilerplate(self) -> None:
        row = {
            "identity": "boilerplate",
            "shop": "A",
            "source_keyword": "塑形内衣",
            "precontact_qualified": True,
            "precontact_sales": 50000,
            "content_evidence_reviewed": True,
            "content_evidence": ["搜索 Ta 的作品", "登录后免费畅享高清视频"],
            "buyin_profile_url": "https://buyin.jinritemai.com/daren-profile?uid=1",
        }

        selected = select_similar_seeds([row], "A", 10, require_body_measurements=False)

        self.assertEqual(selected, [])

    def test_parses_suggestions_and_chooses_exact_account_by_fans(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "sugList": [
                    {"author_info": {"author_id": "wrong", "nickname": "同名达人", "fans_num": 120000, "aweme_id": "wrong-id"}},
                    {"author_info": {"author_id": "right", "nickname": "同名达人", "fans_num": 10300, "aweme_id": "right-id"}},
                ]
            },
        }
        suggestions = suggestions_from_payload(payload)

        selected = choose_seed_suggestion(
            suggestions,
            {"nickname": "同名达人", "fans": 10000, "douyin_id": "right-id"},
        )

        self.assertEqual(selected["author_id"], "right")

    def test_rejects_nonmatching_suggestion_instead_of_using_wrong_creator(self) -> None:
        suggestions = [{"author_id": "wrong", "nickname": "另一个达人", "fans_num": 10000, "aweme_id": "x"}]

        self.assertIsNone(choose_seed_suggestion(suggestions, {"nickname": "目标达人", "fans": 10000}))

    def test_extracts_reference_creator_from_brand_viral_example(self) -> None:
        strategy = {"viralExamples": "对标账号：晓姐姐，抖音号81483398349。优质达人合作报价300至400元。"}

        seeds = reference_seeds_from_strategy(strategy)

        self.assertEqual(seeds[0]["nickname"], "晓姐姐")
        self.assertEqual(seeds[0]["douyin_id"], "81483398349")
        self.assertTrue(seeds[0]["reference_seed_only"])
        self.assertEqual(seed_search_query(seeds[0]), "81483398349")

    def test_parses_author_data_and_similarity(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "author_list": [
                    {
                        "similarity_data": {"avg_score": {"score": 86}, "summary": "商品，粉丝相似"},
                        "author_data": {
                            "author_base": {
                                "uid": "similar-uid",
                                "nickname": "相似达人",
                                "fans_num": 20000,
                                "gender": 2,
                                "author_level": 3,
                                "aweme_id": "dy-similar",
                            },
                            "author_tag": {"main_cate": ["服饰内衣"], "contact_icon": "有联系方式"},
                            "author_sale": {"sale_d30_low": 50000, "sale_d30_high": 100000, "main_sale_type": "纯短视频"},
                            "sale_info": {"video_total_sales": {"sale_low": 50000, "sale_high": 100000}},
                            "author_video": {"all_video_num_30d": 20},
                        },
                    }
                ]
            },
        }
        rows = candidates_from_similar_payload(payload, "种子达人", "A")
        self.assertEqual(rows[0]["nickname"], "相似达人")
        self.assertEqual(rows[0]["similarity_score"], 86)
        self.assertEqual(rows[0]["source_seed_nickname"], "种子达人")

    def test_omits_target_creator_row_without_similarity_data(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "author_list": [
                    {
                        "similarity_data": None,
                        "author_data": {
                            "author_base": {"uid": "seed", "nickname": "种子本人", "gender": 2, "author_level": 3},
                            "author_tag": {"main_cate": ["服饰内衣"], "contact_icon": "有联系方式"},
                            "author_sale": {"sale_d30_low": 50000, "main_sale_type": "纯短视频"},
                            "author_video": {"all_video_num_30d": 10},
                            "sale_info": {"video_total_sales": {"sale_low": 50000}},
                        },
                    }
                ]
            },
        }

        self.assertEqual(candidates_from_similar_payload(payload, "种子本人", "A"), [])

    def test_precursor_rejects_lv5_for_lv2_to_lv4_task(self) -> None:
        candidate = {
            "gender": 2,
            "talent_level": "LV5",
            "category": "服饰内衣",
            "monthly_sales_low": 50000,
            "contact_visible": True,
            "video_count_30d": 10,
            "video_sales_low": 50000,
            "main_sale_type": "纯短视频",
        }

        self.assertFalse(precursor_eligible(candidate))


if __name__ == "__main__":
    unittest.main()
