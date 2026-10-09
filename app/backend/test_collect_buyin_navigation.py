import unittest
from asyncio import CancelledError
from pathlib import Path

from collect_buyin_creators_cdp import (
    assert_safe,
    assert_safe_payload,
    candidate_identity_values,
    candidate_matches_strategy,
    candidate_matches_source_profile,
    detach_page_response_listener,
    filter_resumed_candidate_pool,
    is_explicitly_logged_out_page_list,
    merge_candidate_pool,
    record_search_response,
    should_resume_completed_pool,
    source_max_pages,
    strategy_filter_labels,
)


class CollectBuyinNavigationTest(unittest.TestCase):
    def test_unconfirmed_filter_preserves_checkpoint_and_blocks_incomplete_recovery(self):
        import json, tempfile
        from unittest.mock import patch
        import collect_buyin_creators_cdp as collector
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); strategy=root/'strategy.json'
            strategy.write_text(json.dumps({"sourceDiscoveryMode":"structured_browse", "category":"个护家清", "targetCount":20, "activeShops":["A"]}))
            events=[]
            with patch('sys.argv', ['collector','--strategy',str(strategy),'--out-dir',str(root/'out')]), patch.object(collector,'endpoint_is_explicitly_logged_out',return_value=False), patch.object(collector,'collect_shop_browse',side_effect=RuntimeError('buyin_sale_type_not_confirmed:视频达人')), patch.object(collector,'emit',side_effect=events.append):
                with self.assertRaises(SystemExit) as stopped:
                    collector.main()
            self.assertEqual(stopped.exception.code,12)
            statuses=[event['status'] for event in events]
            self.assertIn('collection_checkpoint_saved',statuses)
            self.assertIn('collection_filter_blocked',statuses)
            self.assertNotIn('collection_incomplete',statuses)

    def test_sale_type_click_targets_radio_and_requires_checked_state(self):
        from unittest.mock import Mock, patch
        import collect_buyin_creators_cdp as collector
        page=Mock(); radio=page.get_by_role.return_value.first
        radio.is_checked.return_value=True
        with patch.object(collector,"click_text",return_value=True):
            collector.apply_strategy_filters(page,{"contentType":"短视频","category":""})
        page.get_by_role.assert_called_with("radio",name="视频达人",exact=True)
        radio.click.assert_called_once_with(timeout=3000)
        radio.is_checked.return_value=False;radio.get_attribute.return_value="false"
        with patch.object(collector,"click_text",return_value=True), self.assertRaisesRegex(RuntimeError,"sale_type_not_confirmed"):
            collector.apply_strategy_filters(page,{"contentType":"短视频","category":""})

    def test_multiple_levels_do_not_leave_single_platform_level(self):
        from unittest.mock import patch
        import collect_buyin_creators_cdp as collector
        with patch.object(collector, "click_text", return_value=True) as click:
            collector.apply_strategy_filters(object(), {"creatorLevels": [1, 2, 3, 4]})
        self.assertFalse(any(str(call.args[1]).startswith("LV") for call in click.call_args_list))
        with patch.object(collector, "click_text", return_value=True) as click:
            collector.apply_strategy_filters(object(), {"creatorLevels": [2]})
        self.assertIn(unittest.mock.call(unittest.mock.ANY, "LV2"), click.call_args_list)

    def test_restore_reestablishes_same_shop_session_after_search_timeout(self):
        from unittest.mock import MagicMock, patch
        from playwright.sync_api import TimeoutError
        import collect_buyin_creators_cdp as collector
        page = MagicMock()
        page.locator.return_value.first.wait_for.side_effect = [TimeoutError("redirected"), None]
        with patch.object(collector, "assert_safe"), patch.object(collector, "bootstrap_buyin_page") as bootstrap, \
             patch.object(collector, "click_text"), patch.object(collector, "apply_strategy_filters"), \
             patch.object(collector, "trigger_structured_browse"):
            collector.restore_structured_browse_page(page, {})
        bootstrap.assert_called_once_with(page.context, preferred_page=page)

    def test_restore_does_not_reenter_when_platform_risk_is_present(self):
        from unittest.mock import MagicMock, patch
        from playwright.sync_api import TimeoutError
        import collect_buyin_creators_cdp as collector
        page = MagicMock()
        page.locator.return_value.first.wait_for.side_effect = TimeoutError("missing")
        with patch.object(collector, "assert_safe", side_effect=RuntimeError("platform_paused:风险")), \
             patch.object(collector, "bootstrap_buyin_page") as bootstrap:
            with self.assertRaisesRegex(RuntimeError, "platform_paused"):
                collector.restore_structured_browse_page(page, {})
        bootstrap.assert_not_called()

    def test_response_json_cancellation_during_shutdown_is_ignored(self):
        class FakeRequest:
            post_data_json = {"query": "唇蜜", "page": 1}

        class FakeResponse:
            url = "https://buyin.jinritemai.com/square_pc_api/square/search_feed_author"
            request = FakeRequest()

            def json(self):
                raise CancelledError()

        payloads = []
        request_bodies = []
        record_search_response(FakeResponse(), payloads, request_bodies)

        self.assertEqual(payloads, [])
        self.assertEqual(request_bodies, [{"query": "唇蜜", "page": 1}])

    def test_current_environment_risk_pauses_collection(self):
        class FakeBody:
            def inner_text(self, timeout):
                return "未找到相关达人 当前环境存在风险，请稍后重试"

        class FakePage:
            def locator(self, selector):
                self.assert_selector = selector
                return FakeBody()

        with self.assertRaisesRegex(RuntimeError, "platform_paused:当前环境存在风险"):
            assert_safe(FakePage())

        with self.assertRaisesRegex(RuntimeError, "platform_paused:当前环境存在风险"):
            assert_safe_payload({"code": "10001010A", "msg": "当前环境存在风险，请稍后重试"})

    def test_response_listener_is_detached_before_playwright_shutdown(self):
        calls = []

        class FakePage:
            def remove_listener(self, event, callback):
                calls.append((event, callback))

        callback = object()
        detach_page_response_listener(FakePage(), callback)

        self.assertEqual(calls, [("response", callback)])

    def test_regular_collection_does_not_click_unscoped_find_creator_navigation(self):
        source = Path(__file__).with_name("collect_buyin_creators_cdp.py").read_text(encoding="utf-8")

        self.assertIn("bootstrap_buyin_page(context, preferred_page=_embedded_page)", source)
        self.assertNotIn('click_text(page, "找达人")', source)

    def test_large_collection_uses_explicit_bounded_pagination(self):
        source = Path(__file__).with_name("collect_buyin_creators_cdp.py").read_text(encoding="utf-8")

        self.assertEqual(source_max_pages({}, 750), 8)
        self.assertEqual(source_max_pages({"sourceMaxPages": 5}, 750), 5)
        self.assertIn("maximum_page = source_max_pages(strategy, shop_target)", source)
        self.assertIn("fetch_search_page(page, base_request, page_number)", source)

    def test_explicit_login_redirect_skips_only_the_logged_out_shop(self):
        self.assertTrue(is_explicitly_logged_out_page_list([
            {"type": "page", "url": "https://fxg.jinritemai.com/login/common?extra=1"},
            {"type": "page", "url": "https://www.douyinec.com/"},
        ]))
        self.assertFalse(is_explicitly_logged_out_page_list([
            {"type": "page", "url": "https://fxg.jinritemai.com/login/common?extra=1"},
            {"type": "page", "url": "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"},
        ]))

    def test_completed_highwater_skips_reopening_buyin_collection(self):
        self.assertTrue(should_resume_completed_pool(300, 300))
        self.assertTrue(should_resume_completed_pool(301, 300))
        self.assertFalse(should_resume_completed_pool(299, 300))

    def test_delivered_douyin_id_excludes_changed_buyin_identity(self):
        candidate = {
            "identity": "new-buyin-identity",
            "buyin_uid": "new-buyin-identity",
            "douyin_id": "delivered-douyin-id",
            "nickname": "同一个达人",
        }

        self.assertEqual(
            candidate_identity_values(candidate),
            {"new-buyin-identity", "delivered-douyin-id"},
        )
        merged, added = merge_candidate_pool({}, [candidate], {"delivered-douyin-id"})

        self.assertEqual(merged, {})
        self.assertEqual(added, 0)

    def test_source_profile_rejects_wrong_creator_level(self):
        strategy = {"creatorLevels": [3, 4]}

        self.assertTrue(candidate_matches_source_profile({"author_level": 3}, strategy))
        self.assertTrue(candidate_matches_source_profile({"talent_level": "LV4"}, strategy))
        self.assertFalse(candidate_matches_source_profile({"author_level": 1}, strategy))
        self.assertFalse(candidate_matches_source_profile({"talent_level": "LV2"}, strategy))

    def test_source_profile_level_gate_does_not_filter_preserved_pool(self):
        preserved = filter_resumed_candidate_pool(
            {"old-lv1": {"identity": "old-lv1", "nickname": "旧达人", "author_level": 1}},
            {"creatorLevels": [3, 4]},
        )

        self.assertEqual(list(preserved), ["old-lv1"])

    def test_personal_care_structured_profile_uses_platform_category(self):
        strategy = {
            "category": "个护家清",
            "contentType": "真人口播",
            "requireContact": True,
        }

        self.assertEqual(
            strategy_filter_labels(strategy),
            ["个护家清", "视频达人", "有联系方式"],
        )

    def test_personal_care_profile_keeps_female_gate(self):
        strategy = {"category": "个护家清"}
        candidate = {
            "nickname": "真人好物分享",
            "category": "个护家清",
            "gender": 2,
        }

        self.assertTrue(candidate_matches_strategy(candidate, strategy))
        self.assertFalse(candidate_matches_strategy({**candidate, "gender": 1}, strategy))

    def test_strict_source_profile_rejects_neighboring_beauty_category(self):
        strategy = {
            "category": "个护家清",
            "creatorLevels": [1, 2, 3, 4],
            "sourceProfileCategoryStrict": True,
        }

        self.assertTrue(candidate_matches_source_profile(
            {"category": "美妆/个护家清", "author_level": 1}, strategy,
        ))
        self.assertFalse(candidate_matches_source_profile(
            {"category": "美妆/鞋靴箱包", "author_level": 1}, strategy,
        ))


if __name__ == "__main__":
    unittest.main()
