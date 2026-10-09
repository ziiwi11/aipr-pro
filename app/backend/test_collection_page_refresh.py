import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import collect_buyin_creators_cdp as collector


class PageRefreshTests(unittest.TestCase):
    def test_checkpoint_revisits_old_page_without_discarding_unseen_pages(self):
        self.assertEqual(collector.structured_page_schedule({1, 2}, 4), [1, 3, 4])
        self.assertEqual(collector.structured_page_schedule({1, 2}, 2), [1, 2])
        self.assertEqual(collector.structured_page_schedule(set(), 2), [1, 2])

    def run_feed(self, feeds):
        page = MagicMock()
        output = {'old': {'identity': 'old', 'buyin_uid': 'uid-old', 'shop': 'A'}}
        strategy = {'category': '美妆', 'sourceBrowsePagesPerRun': 4,
                    'sourceBrowseMaxPages': 3, 'sourceDiscoveryMode': 'structured_browse'}
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            for name in ('assert_safe', 'assert_safe_payloads', 'emit', 'save_highwater'):
                stack.enter_context(patch.object(collector, name))
            stack.enter_context(patch.object(collector, 'sync_playwright'))
            stack.enter_context(patch.object(collector, 'connect_shop', return_value=(MagicMock(), MagicMock(), page)))
            stack.enter_context(patch.object(collector, 'bootstrap_buyin_page', return_value=page))
            for name in ('apply_strategy_filters', 'trigger_structured_browse', 'click_text'):
                stack.enter_context(patch.object(collector, name))
            stack.enter_context(patch.object(collector, 'resolve_structured_browse_request', return_value={}))
            stack.enter_context(patch.object(collector, 'candidate_matches_strategy', return_value=True))
            stack.enter_context(patch.object(collector, 'candidate_matches_source_profile', return_value=True))
            stack.enter_context(patch.object(collector, 'extract_candidates', side_effect=lambda payloads, *_: payloads[0]['data']['list']))
            fetch = stack.enter_context(patch.object(collector, 'fetch_search_page', side_effect=feeds))
            restore = stack.enter_context(patch.object(collector, 'restore_structured_browse_page'))
            result = collector.collect_shop_browse('unused-test-endpoint', 'A', strategy,
                output, 10, set(), Path(directory) / 'checkpoint.json', {'A': {1}})
            return result, output, fetch.call_args_list, restore.call_count, page.wait_for_timeout.call_args_list

    @staticmethod
    def feed(*rows):
        return {'data': {'list': list(rows), 'has_more': False}}

    def test_same_page_refresh_can_add_new_identity_without_readding_old(self):
        old = {'identity': 'old', 'buyin_uid': 'uid-old', 'shop': 'A'}
        new = {'identity': 'new', 'buyin_uid': 'uid-new', 'shop': 'A'}
        result, output, calls, reloads, _ = self.run_feed([
            self.feed(old), self.feed(old, new), self.feed(old), self.feed(old)])
        self.assertTrue(result)
        self.assertEqual(set(output), {'old', 'new'})
        self.assertEqual([call.args[2] for call in calls], [1, 1, 1, 1])
        self.assertEqual(reloads, 4)

    def test_three_unchanged_fetches_back_off_without_infinite_refresh(self):
        old = {'identity': 'old', 'buyin_uid': 'uid-old', 'shop': 'A'}
        result, output, calls, _, waits = self.run_feed([self.feed(old)] * 3)
        self.assertTrue(result)
        self.assertEqual(len(calls), 3)
        self.assertEqual(set(output), {'old'})
        self.assertTrue(any(call.args == (60000,) for call in waits))

