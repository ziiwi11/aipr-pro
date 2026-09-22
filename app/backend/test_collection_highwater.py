import unittest

from collect_buyin_creators_cdp import (
    assign_keywords_to_shops,
    assert_safe_payload,
    assert_safe_payloads,
    candidate_matches_strategy,
    collection_highwater_filename,
    collection_output_prefix,
    completed_keywords_from_payload,
    completed_pages_from_payload,
    contact_signal,
    contact_field_present,
    extract_candidates,
    finish_collection,
    filter_resumed_candidate_pool,
    merge_candidate_pool,
    normalize_gender,
    normalize_categories,
    parse_count,
    pending_shop_keywords,
    resolve_active_shops,
    save_highwater,
    source_keyword_delay_ms,
    source_browse_max_pages,
    source_browse_pages_per_run,
    source_browse_profile_id,
    source_discovery_mode,
    source_max_pages,
    source_max_keywords_per_run,
    source_page_delay_ms,
    strategy_filter_labels,
    structured_browse_request_body,
)
from pipeline_acceptance import remaining_shop_target, source_pool_target


class CollectionHighWaterTest(unittest.TestCase):
    def test_structured_browse_mode_does_not_require_keywords(self):
        self.assertEqual(source_discovery_mode({"sourceDiscoveryMode": "structured_browse"}), "structured_browse")
        self.assertEqual(source_discovery_mode({"sourceDiscoveryMode": "browse"}), "structured_browse")
        self.assertEqual(source_discovery_mode({}), "keyword_search")

    def test_structured_browse_checkpoint_resumes_by_page(self):
        completed = completed_pages_from_payload({
            "completed_pages_by_shop": {"B": [1, "2", 0, "bad"]}
        })
        self.assertEqual(completed, {"B": {1, 2}})

    def test_structured_browse_reuses_filter_request_with_empty_query(self):
        body = structured_browse_request_body([
            {"query": "旧关键词", "page": 1, "filters": {"category": "美妆"}},
            {"query": "旧关键词", "page": 2},
        ])
        self.assertEqual(body["query"], "")
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["filters"], {"category": "美妆"})

    def test_structured_browse_page_limits_are_bounded(self):
        self.assertEqual(source_browse_pages_per_run({}), 12)
        self.assertEqual(source_browse_pages_per_run({"sourceBrowsePagesPerRun": 99}), 30)
        self.assertEqual(source_browse_max_pages({}), 60)
        self.assertEqual(source_browse_max_pages({"sourceBrowseMaxPages": 999}), 100)

    def test_structured_browse_profile_id_changes_with_level_segment(self):
        base = {
            "category": "美妆个护", "contentType": "真人口播",
            "minimumFollowers": 3000, "maximumFollowers": 500000,
            "requireContact": True,
        }
        self.assertNotEqual(
            source_browse_profile_id({**base, "creatorLevels": [1, 2]}),
            source_browse_profile_id({**base, "creatorLevels": [3, 4]}),
        )
        self.assertEqual(
            source_browse_profile_id({"sourceBrowseProfileId": "lv1-lv2"}),
            "lv1-lv2",
        )

    def test_source_checkpoint_resumes_after_completed_shop_keywords(self):
        payload = {
            "completed_keywords_by_shop": {
                "B": ["唇部精华", "润唇", "淡唇纹"],
            }
        }
        completed = completed_keywords_from_payload(payload)
        pending = pending_shop_keywords(
            ["唇部精华", "润唇", "淡唇纹", "居家变美"],
            completed["B"],
        )
        self.assertEqual(pending, [(3, "居家变美")])

    def test_checkpoint_persists_completed_keywords_for_next_run(self):
        import json
        import tempfile
        from pathlib import Path

        strategy = {
            "strategyPurpose": "replenishment-source-only",
            "targetCount": 2,
            "requireContact": True,
            "keywords": ["唇部精华", "润唇", "居家变美"],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aipr_replenishment_collection_highwater.json"
            save_highwater(
                path,
                strategy,
                {"one": {"identity": "one"}},
                {"B": {"唇部精华", "润唇"}},
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["completed_keywords_by_shop"],
                {"B": ["唇部精华", "润唇"]},
            )

    def test_source_pool_and_checkpoint_use_atomic_json_writes(self):
        from pathlib import Path

        source = Path(__file__).with_name("collect_buyin_creators_cdp.py").read_text(encoding="utf-8")
        self.assertIn("atomic_write_json(path, {", source)
        self.assertIn("atomic_write_json(output, payload)", source)

    def test_source_only_replenishment_uses_an_isolated_highwater(self):
        source_only = {"strategyPurpose": "replenishment-source-only"}
        self.assertEqual(
            collection_highwater_filename(source_only),
            "aipr_replenishment_collection_highwater.json",
        )
        self.assertEqual(
            collection_output_prefix(source_only),
            "aipr_buyin_creator_pool_replenishment",
        )
        self.assertEqual(collection_highwater_filename({}), "aipr_collection_highwater.json")
        self.assertEqual(collection_output_prefix({}), "aipr_buyin_creator_pool")

    def test_partial_source_pool_is_checkpoint_not_ready(self):
        import json
        import tempfile
        from pathlib import Path

        strategy = {
            "strategyPurpose": "replenishment-source-only",
            "targetCount": 2,
            "requireContact": True,
        }
        candidates = {"one": {"identity": "one"}, "two": {"identity": "two"}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            highwater = root / "aipr_replenishment_collection_highwater.json"
            save_highwater(highwater, strategy, candidates)
            saved = json.loads(highwater.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "checkpoint")
            self.assertEqual(saved["target_count"], 6)
            self.assertFalse(saved["complete"])

            output = finish_collection(
                root, strategy, candidates, highwater,
                emit_status="collection_checkpoint_saved",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "checkpoint")
            self.assertFalse(payload["complete"])

    def test_source_only_replenishment_assigns_every_keyword_to_b(self):
        self.assertEqual(resolve_active_shops({"activeShops": ["B"]}), ["B"])
        self.assertEqual(resolve_active_shops({}), ["A", "B"])
        keywords = ["唇部精华", "居家变美", "通勤妆容", "口播测评"]
        self.assertEqual(
            assign_keywords_to_shops([("B", "b-endpoint")], keywords),
            [("B", "b-endpoint", keywords)],
        )

    def test_two_shop_collection_partitions_keywords_without_loss(self):
        keywords = ["k1", "k2", "k3", "k4", "k5"]
        assignments = assign_keywords_to_shops(
            [("A", "a-endpoint"), ("B", "b-endpoint")], keywords
        )
        self.assertEqual(assignments[0][2], ["k1", "k3", "k5"])
        self.assertEqual(assignments[1][2], ["k2", "k4"])
        self.assertEqual(sorted(assignments[0][2] + assignments[1][2]), sorted(keywords))

    def test_beauty_filter_uses_the_beauty_category(self):
        # 「美妆个护」现在同时勾选「美妆」与「个护家清」两个平台标签：
        # 判定侧 creator_delivery_contract 本就接受「美妆」或「个护家清」，
        # 采集侧只勾「美妆」会漏掉大量个护家清达人。
        labels = strategy_filter_labels({"category": "美妆个护"})
        self.assertIn("美妆", labels)
        self.assertIn("个护家清", labels)

    def test_extracts_current_buyin_parent_record_fields(self):
        payload = {"code": 0, "data": {"list": [{
            "author_base": {
                "uid": "creator-1", "nickname": "美妆小美", "aweme_id": "douyin-mei",
                "fans_num": 12345, "gender": 2, "city": "上海", "author_level": 3,
            },
            "author_tag": {"main_cate": ["美妆"], "contact_icon": "点击小眼睛查看"},
            "author_contact": {"wechat": "", "phone": ""},
            "author_sale": {"sale_d30_low": 10000, "sale_d30_high": 25000, "main_sale_type": "纯短视频"},
            "author_video": {"all_video_num_30d": 12},
        }]}}
        rows = extract_candidates([payload], "唇部护理", "A")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["douyin_id"], "douyin-mei")
        self.assertEqual(rows[0]["fans"], 12345)
        self.assertEqual(rows[0]["gender"], 2)
        self.assertEqual(rows[0]["category"], "美妆")
        self.assertTrue(rows[0]["contact_visible"])

    def test_legacy_search_payload_builds_profile_without_undefined_level(self):
        payload = {
            "data": {
                "nested": {
                    "nickname": "场景美妆达人",
                    "author_id": "legacy-creator",
                    "author_level": "2",
                    "gender": 2,
                }
            }
        }

        rows = extract_candidates([payload], "居家变美", "B")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["identity"], "legacy-creator")
        self.assertIn("legacy-creator", rows[0]["buyin_profile_url"])

    def test_legacy_chinese_female_gender_is_normalized(self):
        payload = {
            "data": {
                "nested": {
                    "nickname": "居家护肤女生",
                    "author_id": "legacy-female",
                    "gender": "女性",
                    "category": "美妆",
                    "contact_visible": True,
                }
            }
        }
        rows = extract_candidates([payload], "居家变美", "B")
        self.assertEqual(rows[0]["gender"], 2)
        self.assertTrue(candidate_matches_strategy(rows[0], {
            "category": "美妆个护",
            "requireContact": True,
            "keywords": ["居家变美"],
        }))

    def test_gender_normalization_accepts_known_platform_encodings(self):
        self.assertEqual(normalize_gender(2), 2)
        self.assertEqual(normalize_gender("2"), 2)
        self.assertEqual(normalize_gender("女"), 2)
        self.assertEqual(normalize_gender("female"), 2)
        self.assertEqual(normalize_gender("男性"), 1)
        self.assertEqual(normalize_gender("unknown"), 0)

    def test_platform_count_formats_are_parsed_without_crashing_page(self):
        self.assertEqual(parse_count("3,000"), 3000)
        self.assertEqual(parse_count("1.2万"), 12000)
        self.assertEqual(parse_count("2w+"), 20000)
        self.assertEqual(parse_count("1.5亿"), 150000000)
        self.assertEqual(parse_count("--"), 0)

        payload = {"code": 0, "data": {"list": [{
            "author_base": {
                "uid": "formatted-counts", "nickname": "通勤妆小美",
                "fans_num": "1.2万", "gender": "女", "author_level": "LV3",
            },
            "author_tag": {"main_cate": ["美妆"], "contact_icon": "有联系方式"},
            "author_sale": {"sale_d30_low": "3,000", "sale_d30_high": "2万+"},
            "author_video": {"all_video_num_30d": "--"},
        }]}}
        rows = extract_candidates([payload], "通勤妆容", "B")
        self.assertEqual(rows[0]["fans"], 12000)
        self.assertEqual(rows[0]["author_level"], 3)
        self.assertEqual(rows[0]["monthly_sales_high"], 20000)
        self.assertEqual(rows[0]["video_count_30d"], 0)

    def test_contact_visibility_strings_are_not_treated_as_generic_truthy_values(self):
        for value in (False, 0, "0", "false", "暂无联系方式", "无联系方式", "disabled"):
            self.assertFalse(contact_signal(value), value)
        for value in (True, 1, "true", "有联系方式", "点击小眼睛查看", "/contact-icon.svg"):
            self.assertTrue(contact_signal(value), value)

        payload = {"data": {"nested": {
            "nickname": "无联系方式女生",
            "author_id": "no-contact-legacy",
            "gender": "女",
            "category": "美妆",
            "contact_visible": "false",
            "has_contact": "暂无联系方式",
        }}}
        rows = extract_candidates([payload], "居家变美", "B")
        self.assertFalse(rows[0]["contact_visible"])
        self.assertFalse(candidate_matches_strategy(rows[0], {
            "category": "美妆个护", "requireContact": True, "keywords": ["居家变美"]
        }))

    def test_contact_field_placeholders_do_not_mark_creator_contactable(self):
        for value in ("", "--", "暂无", "未设置", "null", "none", "n/a", "false", "0"):
            self.assertFalse(contact_field_present(value), value)
        for value in ("138****0000", "wx_creator", "creator@example.com"):
            self.assertTrue(contact_field_present(value), value)

        payload = {"code": 0, "data": {"list": [{
            "author_base": {
                "uid": "placeholder-contact", "nickname": "占位符测试",
                "fans_num": 10000, "gender": 2, "author_level": 2,
            },
            "author_tag": {"main_cate": ["美妆"], "contact_icon": ""},
            "author_contact": {"wechat": "暂无", "phone": "--", "email": "null"},
        }]}}
        rows = extract_candidates([payload], "唇部护理", "B")
        self.assertFalse(rows[0]["contact_visible"])

    def test_category_field_accepts_list_and_delimited_string_shapes(self):
        self.assertEqual(normalize_categories(["美妆", "个护家清"]), ["美妆", "个护家清"])
        self.assertEqual(normalize_categories("美妆/个护家清"), ["美妆", "个护家清"])
        payload = {"code": 0, "data": {"list": [{
            "author_base": {
                "uid": "string-category", "nickname": "护肤小美",
                "fans_num": 10000, "gender": 2, "author_level": 2,
            },
            "author_tag": {"main_cate": "美妆/个护家清", "contact_icon": "/contact-icon.svg"},
        }]}}
        rows = extract_candidates([payload], "唇部护理", "B")
        self.assertEqual(rows[0]["categories"], ["美妆", "个护家清"])
        self.assertEqual(rows[0]["category"], "美妆/个护家清")
        self.assertTrue(candidate_matches_strategy(rows[0], {
            "category": "美妆个护", "requireContact": True, "keywords": ["唇部护理"]
        }))

    def test_beauty_task_requires_female_vertical_creator_with_contact(self):
        strategy = {"category": "美妆个护", "keywords": ["唇部护理"], "requireContact": True}
        base = {"gender": 2, "category": "美妆/个护家清", "contact_visible": True}
        self.assertTrue(candidate_matches_strategy(base, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "gender": 1}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "category": "食品饮料"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "contact_visible": False}, strategy))

    def test_source_pool_applies_follower_bounds_before_browser_evidence(self):
        strategy = {
            "category": "美妆个护",
            "requireContact": True,
            "minimumFollowers": 3000,
            "maximumFollowers": 500000,
        }
        base = {"gender": 2, "category": "美妆", "contact_visible": True}
        self.assertTrue(candidate_matches_strategy({**base, "fans": 3000}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "fans": 2999}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "fans": 500001}, strategy))

    def test_source_pool_can_require_recent_video_activity(self):
        strategy = {
            "category": "美妆个护",
            "requireContact": True,
            "minimumVideos30d": 3,
        }
        base = {"gender": 2, "category": "美妆", "contact_visible": True, "fans": 10000}
        self.assertTrue(candidate_matches_strategy({**base, "video_count_30d": 3}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "video_count_30d": 2}, strategy))

    def test_source_pool_rejects_hard_exclusions_before_evidence_work(self):
        strategy = {
            "category": "美妆个护",
            "requireContact": True,
            "exclusions": ["母婴", "品牌店铺"],
        }
        base = {"gender": 2, "category": "美妆", "contact_visible": True, "fans": 10000}
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "宝妈护肤日记"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "欢乐麻麻"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "精致美妆旗舰店"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "芹姐百货"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "桠觅叶商贸行（个体工商户）"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "星河日用品有限公司"}, strategy))
        self.assertTrue(candidate_matches_strategy({**base, "nickname": "通勤妆容小美"}, strategy))

    def test_source_pool_rejects_task_specific_nickname_markers(self):
        strategy = {
            "category": "美妆个护",
            "requireContact": True,
            "keywords": ["居家变美"],
            "excludeNicknameContains": ["护肤"],
        }
        base = {"gender": 2, "category": "美妆", "contact_visible": True}
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "荟悉护肤品号"}, strategy))
        self.assertFalse(candidate_matches_strategy({**base, "nickname": "娴姐护肤"}, strategy))
        self.assertTrue(candidate_matches_strategy({**base, "nickname": "通勤妆容小美"}, strategy))

    def test_resume_reapplies_tightened_hard_exclusions(self):
        strategy = {
            "category": "美妆个护",
            "requireContact": True,
            "keywords": ["梳妆台好物"],
            "exclusions": ["品牌店铺"],
        }
        candidates = {
            "business": {
                "identity": "business", "nickname": "桠觅叶商贸行（个体工商户）",
                "gender": 2, "category": "个护家清", "contact_visible": True,
            },
            "creator": {
                "identity": "creator", "nickname": "通勤妆容小美",
                "gender": 2, "category": "美妆", "contact_visible": True,
            },
        }
        filtered = filter_resumed_candidate_pool(candidates, strategy)
        self.assertEqual(list(filtered), ["creator"])

    def test_applies_the_one_wan_buyin_sales_filter(self):
        labels = strategy_filter_labels({"category": "服饰内衣", "minimumMonthlySales": 10000})
        self.assertIn("1万以上", labels)

    def test_source_pool_oversamples_contact_required_tasks(self):
        self.assertEqual(source_pool_target(100, True), 300)
        self.assertEqual(source_pool_target(100, False), 100)

    def test_source_request_pacing_is_configurable_and_bounded(self):
        self.assertEqual(source_keyword_delay_ms({}), 2600)
        self.assertEqual(source_page_delay_ms({}), 1100)
        self.assertEqual(source_keyword_delay_ms({"sourceKeywordDelayMs": 5000}), 5000)
        self.assertEqual(source_page_delay_ms({"sourcePageDelayMs": 3000}), 3000)
        self.assertEqual(source_keyword_delay_ms({"sourceKeywordDelayMs": 1}), 2600)
        self.assertEqual(source_page_delay_ms({"sourcePageDelayMs": 99999}), 15000)

    def test_source_pagination_uses_actual_pool_target_and_strategy_cap(self):
        self.assertEqual(source_max_pages({}, 499), 3)
        self.assertEqual(source_max_pages({}, 750), 8)
        self.assertEqual(source_max_pages({"sourceMaxPages": 5}, 750), 5)
        self.assertEqual(source_max_pages({"sourceMaxPages": 99}, 750), 8)
        self.assertEqual(source_max_pages({"sourceMaxPages": 0}, 750), 1)

    def test_source_keyword_batch_size_is_optional_and_bounded(self):
        self.assertEqual(source_max_keywords_per_run({}), 0)
        self.assertEqual(source_max_keywords_per_run({"sourceMaxKeywordsPerRun": 0}), 0)
        self.assertEqual(source_max_keywords_per_run({"sourceMaxKeywordsPerRun": 12}), 12)
        self.assertEqual(source_max_keywords_per_run({"sourceMaxKeywordsPerRun": 999}), 50)
        self.assertEqual(source_max_keywords_per_run({"sourceMaxKeywordsPerRun": "bad"}), 0)

    def test_nested_search_api_frequency_control_stops_collection(self):
        with self.assertRaisesRegex(RuntimeError, "platform_paused:请求过于频繁"):
            assert_safe_payload({"data": {"error_msg": "请求过于频繁，请稍后再试"}})
        with self.assertRaisesRegex(RuntimeError, r"platform_paused:(访问频繁|稍后再试)"):
            assert_safe_payloads([
                {"code": 0, "data": {"list": []}},
                {"code": 429, "data": {"toast": "访问频繁，请稍后再试"}},
            ])

    def test_creator_bio_text_does_not_trigger_payload_frequency_control(self):
        assert_safe_payload({"data": {"list": [{"nickname": "稍后再试试口红的小美"}]}})

    def test_second_shop_takes_over_the_first_shop_shortfall(self):
        self.assertEqual(remaining_shop_target(300, other_shop_count=12), 288)

    def test_merge_keeps_existing_records_and_excludes_prior_deliveries(self):
        existing = {"1": {"identity": "1", "nickname": "旧达人", "wechat": "kept"}}
        incoming = [
            {"identity": "1", "nickname": "旧达人更新"},
            {"identity": "2", "nickname": "已交付"},
            {"identity": "3", "nickname": "新达人"},
        ]
        merged, added = merge_candidate_pool(existing, incoming, {"2"})
        self.assertEqual(added, 1)
        self.assertEqual(merged["1"]["wechat"], "kept")
        self.assertIn("3", merged)
        self.assertNotIn("2", merged)

    def test_merge_deduplicates_any_strong_identity_within_new_pool(self):
        existing = {
            "buyin-old": {
                "identity": "buyin-old",
                "douyin_id": "douyin-same",
                "nickname": "原昵称",
                "shop": "B",
            }
        }
        incoming = [{
            "identity": "buyin-new",
            "buyin_uid": "buyin-new",
            "douyin_id": "douyin-same",
            "nickname": "改名后的昵称",
            "source_keyword": "通勤妆容",
        }]

        merged, added = merge_candidate_pool(existing, incoming)

        self.assertEqual(added, 0)
        self.assertEqual(list(merged), ["buyin-old"])
        self.assertEqual(merged["buyin-old"]["identity"], "buyin-old")
        self.assertEqual(merged["buyin-old"]["source_keyword"], "通勤妆容")


if __name__ == "__main__":
    unittest.main()
