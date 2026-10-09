import unittest
from pathlib import Path

from collect_and_contact_pipeline import (
    build_replenishment_exclusions,
    contact_quota_exhausted_shops,
    extend_replenishment_keywords,
    extend_low_pool_keywords,
    load_historical_contact_candidates,
    load_verified_candidate_seed,
    platform_pause_event,
    resolve_evidence_lanes_per_shop,
    resolve_max_replenishment_rounds,
    recover_completed_collection,
    restore_replenishment_state,
    run_stream,
    should_replenish_source_pool,
    merge_candidate_sources,
    has_new_discovery_candidates,
    resumable_collection_pool,
    should_reuse_historical_contacts,
)


class PipelineReplenishmentTest(unittest.TestCase):
    def test_repeated_discovery_alias_is_not_a_new_candidate(self):
        saved = {"candidates": [{"identity": "old", "buyin_uid": "shared"}]}
        repeated = {"candidates": [{"identity": "alias", "buyin_uid": "shared"}]}
        self.assertFalse(has_new_discovery_candidates(repeated, saved))
        self.assertFalse(has_new_discovery_candidates({"candidates": []}, saved))
        self.assertTrue(has_new_discovery_candidates({"candidates": [{"identity": "new"}]}, saved))

    def test_beauty_low_pool_expands_to_allowed_lifestyle_sources(self):
        first = extend_low_pool_keywords([], 1, {"category": "美妆个护"})
        later = extend_low_pool_keywords(first, 3, {"category": "美妆个护"})
        self.assertGreater(len(later), len(first))
        self.assertIn("生活好物", later)
        self.assertNotIn("内衣试穿", later)

    def test_loads_only_strict_qualified_verified_candidate_seed_rows(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            (output_dir / "aipr_verified_candidate_seed.json").write_text(json.dumps({
                "candidates": [
                    {"identity": "kept", "osmana_evaluation": {"qualified": True}},
                    {"identity": "excluded", "osmana_evaluation": {"qualified": True}},
                    {"identity": "generic"},
                    {"identity": "failed", "osmana_evaluation": {"qualified": False}},
                ]
            }), encoding="utf-8")

            payload = load_verified_candidate_seed(output_dir, {"excluded"})

            self.assertEqual(payload["candidate_count"], 1)
            self.assertEqual(payload["candidates"][0]["identity"], "kept")

    def test_recovers_completed_contact_source_pool_from_highwater(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aipr_collection_highwater.json"
            path.write_text(json.dumps({
                "status": "ready",
                "candidate_count": 6,
                "candidates": [{"identity": str(index)} for index in range(6)],
            }), encoding="utf-8")

            recovered = recover_completed_collection(path, {"targetCount": 2, "requireContact": True})

            self.assertEqual(recovered["status"], "collection_finished")
            self.assertEqual(recovered["candidate_count"], 6)
            self.assertTrue(recovered["recovered_from_highwater"])

    def test_idle_worker_can_recover_without_waiting_for_process_exit(self):
        import sys
        import time

        started = time.monotonic()
        code, events = run_stream(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            idle_timeout_seconds=0.1,
            recover_on_idle=lambda: {"status": "collection_finished", "output": "highwater.json"},
        )

        self.assertEqual(code, 0)
        self.assertEqual(events[-1]["output"], "highwater.json")
        self.assertLess(time.monotonic() - started, 3)

    def test_rate_limit_event_stops_child_and_parent_round_immediately(self):
        import json
        import sys
        import time

        started = time.monotonic()
        # 连续 3 次 rate_limited 才判定平台真限制并终止进程树；
        # 单次属频次抖动，子进程内部会跳过该达人继续。
        payload = json.dumps({"status": "rate_limited", "message": "请求过于频繁，请稍后再试"}, ensure_ascii=False)
        code, events = run_stream([
            sys.executable,
            "-c",
            f"import time; [print({payload!r}, flush=True) for _ in range(3)]; time.sleep(20)",
        ])

        self.assertEqual(code, 9)
        self.assertTrue(platform_pause_event(events[-1]))
        self.assertLess(time.monotonic() - started, 3)

    def test_single_rate_limit_event_does_not_stop_round(self):
        """单次 rate_limited 不应终止整轮采集（仅记为抖动）。"""
        import json
        import sys
        import time

        payload = json.dumps({"status": "rate_limited", "message": "请求过于频繁，请稍后再试"}, ensure_ascii=False)
        code, events = run_stream([
            sys.executable,
            "-c",
            f"import time; print({payload!r}, flush=True); time.sleep(0.5); "
            f"print({json.dumps({'status': 'collection_finished', 'output': 'highwater.json'})!r}, flush=True)",
        ])

        self.assertEqual(code, 0)
        self.assertTrue(platform_pause_event(events[0]))

    def test_merge_sources_excludes_delivered_douyin_id_when_identity_changed(self):
        payload = {
            "candidates": [{
                "identity": "new-buyin-identity",
                "douyin_id": "delivered-douyin-id",
            }],
        }

        merged = merge_candidate_sources(payload, [], {"delivered-douyin-id"})

        self.assertEqual(merged["candidate_count"], 0)
        self.assertEqual(merged["candidates"], [])

    def test_loads_only_unused_plain_contacts_from_sibling_task_history(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = root / "task-current"
            previous = root / "task-previous"
            current.mkdir()
            previous.mkdir()
            (previous / "aipr_creator_contacts_1.json").write_text(json.dumps({
                "candidates": [
                    {"identity": "available", "buyin_contact_wechat": "wx", "nickname": "A"},
                    {"identity": "excluded", "buyin_contact_phone": "13800000000", "nickname": "B"},
                    {"identity": "delivered", "buyin_contact_wechat": "old", "nickname": "D"},
                    {"identity": "blank", "nickname": "C"},
                ]
            }), encoding="utf-8")
            (previous / "aipr_final_delivery_1.json").write_text(json.dumps({
                "rows": [{"主页身份ID": "delivered"}]
            }), encoding="utf-8")
            (current / "aipr_contact_highwater.json").write_text(json.dumps({
                "candidates": [{
                    "identity": "current-kept",
                    "precontact_qualified": True,
                    "buyin_contact_wechat": "current_wx",
                }]
            }), encoding="utf-8")

            rows = load_historical_contact_candidates(root, current, {"excluded"})

            self.assertEqual([row["identity"] for row in rows], ["available", "current-kept"])

    def test_contact_heavy_tasks_default_to_sixteen_replenishment_rounds(self):
        self.assertEqual(resolve_max_replenishment_rounds({}), 16)
        self.assertEqual(resolve_max_replenishment_rounds({"maxReplenishmentRounds": 12}), 12)
        self.assertEqual(resolve_max_replenishment_rounds({"maxReplenishmentRounds": 0}), 1)

    def test_historical_contacts_are_opt_in_for_fresh_tasks(self):
        self.assertFalse(should_reuse_historical_contacts({}))
        self.assertFalse(should_reuse_historical_contacts({"reuseHistoricalContacts": False}))
        self.assertTrue(should_reuse_historical_contacts({"reuseHistoricalContacts": True}))

    def test_reuses_completed_collection_pool_for_the_same_exclusions_and_keywords(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            strategy = {
                "targetCount": 2,
                "keywords": ["塑形裤", "内衣试穿"],
                "excludeIdentities": ["old-1"],
                "replenishmentRound": 3,
            }
            pool = {
                "status": "ready",
                "candidate_count": 2,
                "strategy": {**strategy, "replenishmentRound": 1},
                "candidates": [{"identity": "new-1"}, {"identity": "new-2"}],
            }
            path = output_dir / "aipr_buyin_creator_pool_similar.json"
            path.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")

            resumed = resumable_collection_pool(output_dir, strategy)

            self.assertEqual(resumed, {"output": str(path), "candidate_count": 2})
            self.assertIsNone(resumable_collection_pool(
                output_dir,
                {**strategy, "excludeIdentities": ["old-1", "old-2"]},
            ))

    def test_excludes_exhausted_rows_but_keeps_qualified_contacted_creator(self):
        rows = [
            {"identity": "qualified", "precontact_qualified": True, "buyin_contact_wechat": "wx"},
            {"identity": "no-contact", "precontact_qualified": True},
            {"identity": "wrong-persona", "precontact_qualified": False},
        ]
        exclusions = build_replenishment_exclusions(rows, {"legacy"})
        self.assertEqual(exclusions, {"legacy", "no-contact", "wrong-persona"})

    def test_adds_precise_shapewear_keywords_without_duplicates(self):
        keywords = extend_replenishment_keywords(["提臀裤", "内衣试穿"])
        self.assertEqual(keywords.count("内衣试穿"), 1)
        self.assertIn("收腹提臀裤", keywords)
        self.assertIn("塑形裤测评", keywords)

    def test_beauty_task_never_inherits_shapewear_replenishment_keywords(self):
        strategy = {"category": "美妆个护", "keywords": ["唇部精华", "淡唇纹"]}
        keywords = extend_replenishment_keywords(strategy["keywords"], strategy=strategy)
        low_pool = extend_low_pool_keywords(keywords, strategy=strategy)

        self.assertIn("润唇精华", keywords)
        self.assertIn("唇部产品测评", low_pool)
        self.assertNotIn("收腹提臀裤", keywords)
        self.assertNotIn("女士穿搭", low_pool)

    def test_pipeline_retries_from_replenishment_instead_of_stopping_on_incomplete_delivery(self):
        source = Path(__file__).with_name("collect_and_contact_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("for round_index in range(1, max_rounds + 1)", source)
        self.assertIn('"status": "delivery_replenishing"', source)
        self.assertIn("build_replenishment_exclusions(contact_payload", source)
        self.assertIn("load_historical_contact_candidates(output_dir.parent", source)
        self.assertIn('"status": "historical_contact_source_merged"', source)
        self.assertIn('"status": "verified_candidate_seed_resumed"', source)
        self.assertIn('"status": "evidence_highwater_reused"', source)

    def test_detects_contact_quota_pause_event(self):
        events = [
            {"status": "contact_progress"},
            {"status": "contact_daily_quota_exhausted", "shops": ["A", "B"]},
        ]
        self.assertEqual(contact_quota_exhausted_shops(events), ["A", "B"])

    def test_evidence_concurrency_is_serialized_for_embedded_shop_pages(self):
        self.assertEqual(resolve_evidence_lanes_per_shop({}), 4)
        self.assertEqual(resolve_evidence_lanes_per_shop({"evidenceLanesPerShop": 3}), 3)
        self.assertEqual(resolve_evidence_lanes_per_shop({"evidenceLanesPerShop": 99}), 4)
        self.assertEqual(resolve_evidence_lanes_per_shop({"evidenceLanesPerShop": 0}), 1)
        pipeline_source = Path(__file__).with_name("collect_and_contact_pipeline.py").read_text(encoding="utf-8")
        verifier_source = Path(__file__).with_name("verify_creator_evidence_cdp.py").read_text(encoding="utf-8")
        self.assertIn('"--lanes-per-shop"', pipeline_source)
        self.assertIn('parser.add_argument("--lanes-per-shop"', verifier_source)
        self.assertIn('lane_width = 1 if any("?shop=" in endpoint', verifier_source)
        self.assertIn("partition_evidence_lanes(work, lanes_per_shop=lane_width, active_shops=active_shops)", verifier_source)
        self.assertIn("wait_for_lane_futures(futures)", verifier_source)

    def test_pipeline_restart_recovers_exhausted_identities_from_contact_highwater(self):
        strategy = {"targetCount": 100, "excludeIdentities": ["legacy"], "keywords": ["塑身裤"]}
        contact_payload = {
            "strategy": {
                "keywords": ["塑身裤", "提臀裤试穿"],
                "excludeIdentities": ["older-failure"],
                "replenishmentRound": 1,
            },
            "candidates": [
                {"identity": "keep", "precontact_qualified": True, "buyin_contact_wechat": "wx"},
                {"identity": "no-contact", "precontact_qualified": True},
                {"identity": "wrong-persona", "precontact_qualified": False},
            ]
        }
        restored = restore_replenishment_state(strategy, contact_payload)
        self.assertEqual(restored["excludeIdentities"], ["legacy", "no-contact", "older-failure", "wrong-persona"])
        self.assertEqual(restored["keywords"], ["塑身裤", "提臀裤试穿"])
        self.assertEqual(restored["replenishmentRound"], 1)
        self.assertEqual(restored["targetCount"], 100)

    def test_strict_restart_drops_false_exclusions_created_before_product_verification(self):
        strategy = {
            "brief": "内衣单品近30天短视频销售额不少于1万元",
            "minimumUnderwearProductSales": 10000,
            "excludeIdentities": ["legacy-delivered", "unverified-a", "unverified-b"],
        }
        contact_payload = {
            "strategy": {"excludeIdentities": ["legacy-delivered", "unverified-a"]},
            "candidates": [
                {"identity": "unverified-a", "precontact_qualified": False},
                {"identity": "unverified-b", "precontact_qualified": False},
            ],
        }

        restored = restore_replenishment_state(strategy, contact_payload)

        self.assertEqual(restored["excludeIdentities"], ["legacy-delivered"])

    def test_low_source_pool_expands_related_underwear_keywords_instead_of_stopping(self):
        keywords = extend_low_pool_keywords(["塑身裤", "内衣好物"])
        self.assertEqual(keywords.count("内衣好物"), 1)
        self.assertIn("女士穿搭", keywords)
        self.assertIn("收腹内裤", keywords)
        self.assertIn("服饰测评", keywords)
        self.assertTrue(should_replenish_source_pool(24, 100, 2, 8))
        self.assertFalse(should_replenish_source_pool(100, 100, 2, 8))
        self.assertFalse(should_replenish_source_pool(24, 100, 8, 8))
        source = Path(__file__).with_name("collect_and_contact_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"status": "source_pool_replenishing"', source)

    def test_later_low_pool_rounds_add_fresh_long_tail_keywords(self):
        first_round = extend_low_pool_keywords(["塑身裤"], round_index=1)
        second_round = extend_low_pool_keywords(first_round, round_index=2)

        self.assertNotIn("塑形连体衣", first_round)
        self.assertIn("塑形连体衣", second_round)
        self.assertGreater(len(second_round), len(first_round))

    def test_similar_source_merges_new_creators_without_duplicates_or_excluded_rows(self):
        base = {"strategy": {"targetCount": 100}, "candidates": [{"identity": "kept", "nickname": "A"}]}
        extra = {
            "candidates": [
                {"identity": "kept", "similarity_score": 90},
                {"identity": "new", "nickname": "B"},
                {"identity": "excluded", "nickname": "C"},
            ]
        }
        merged = merge_candidate_sources(base, [extra], {"excluded"})
        self.assertEqual([row["identity"] for row in merged["candidates"]], ["kept", "new"])
        self.assertEqual(merged["candidate_count"], 2)
        source = Path(__file__).with_name("collect_and_contact_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"collect_osmana_similar_cdp.py"', source)
        self.assertIn('"status": "similar_source_finished"', source)
        self.assertIn('"--cross-shop-seeds"', source)
        self.assertIn('"--target-count"', source)


if __name__ == "__main__":
    unittest.main()
