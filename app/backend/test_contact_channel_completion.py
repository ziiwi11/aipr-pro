import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import contact_icons_single as single
from scrape_buyin_profile_contact_icons_cdp import assign_contact_lanes
from complete_saved_contact_channels import retain_unique_supplements


class CompletionTest(unittest.TestCase):
    def test_primary_mode_reveals_wechat_first_and_retains_supplement_work(self):
        page = MagicMock()
        page.url = 'https://buyin.example/profile'
        page.locator.return_value.inner_text.return_value = '达人自主披露联系方式 粉丝数'
        page.title.return_value = '达人详情'
        page.evaluate.return_value = False
        clicks = []
        def indexed(index):
            row = MagicMock()
            row.locator.return_value.dispatch_event.side_effect = lambda event: clicks.append(index) if event == 'click' else None
            return row
        page.locator.return_value.nth.side_effect = indexed
        def items(_):
            return ['达人手机号：********', '达人微信号：creator_wx' if 1 in clicks else '达人微信号：********']
        icons = [{'idx': 0, 'text': '达人手机号：********'}, {'idx': 1, 'text': '达人微信号：********'}]
        with tempfile.TemporaryDirectory() as out, patch.object(single, 'contact_items', items), patch.object(single, 'contact_icons', return_value=icons), patch.object(single, 'visible_buttons', return_value=[]), patch.object(single, 'wait_for_global_contact_slot', return_value=0), patch.object(single, 'confirm_contact_view', return_value={'status': 'not_present'}), patch.object(single, 'page_message', return_value=''):
            result = single.run_candidate(page, {'buyin_profile_url': page.url, 'content_evidence_reviewed': True}, 3000, Path(out), primary_contact_only=True)
        self.assertEqual(clicks, [1])
        self.assertEqual(result['buyin_contact_wechat'], 'creator_wx')
        self.assertEqual(result['buyin_contact_phone'], '')
        self.assertEqual(result['ui_contact_channels_status'], 'primary_ready_supplement_pending')
        self.assertFalse(single.saved_contact_channels_complete(result))

    def test_supplement_never_clears_previously_saved_wechat(self):
        originals = [{'identity': 'a', 'buyin_contact_wechat': 'saved_wx', 'buyin_contact_phone': '13800138000'}]
        updates = [{'identity': 'a', 'buyin_contact_wechat': '', 'buyin_contact_phone': '13900139000'}]
        result = retain_unique_supplements(originals, updates, {})[0]
        self.assertEqual(result['buyin_contact_wechat'], 'saved_wx')
        self.assertEqual(result['buyin_contact_phone'], '13800138000')

    def test_global_cooldown_stops_request_without_waiting_inside_lane(self):
        page = MagicMock()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / '.contact_rate_limit_until').write_text(str(time.time() + 1200))
            with self.assertRaisesRegex(RuntimeError, 'contact_cooldown_active:'):
                single.wait_for_global_contact_slot(page, out, 18000)
        page.wait_for_timeout.assert_not_called()

    def test_saved_phone_mask_is_not_revealed_again(self):
        page = MagicMock()
        icons = [{'idx': 0, 'text': '达人手机号：********'}, {'idx': 1, 'text': '达人微信号：********'}]
        with patch.object(single, 'contact_items', return_value=[]), patch.object(single, 'contact_icons', return_value=icons):
            remaining = single.unresolved_contact_icons(page, {'buyin_contact_phone': '13800138000'})
        self.assertEqual([x['idx'] for x in remaining], [1])

    def test_saved_phone_is_still_selected_and_assigned(self):
        row = {'identity': 'a', 'shop': 'A', 'content_evidence_reviewed': True,
               'precontact_qualified': True, 'buyin_contact_phone': '13800138000'}
        self.assertEqual(single.select_contact_targets([row], 'A', 0), [])
        assigned = assign_contact_lanes([row], ['A'], complete_channels=True)
        self.assertEqual(assigned[0]['contact_shop'], 'A')
        self.assertEqual(len(single.select_contact_targets(assigned, 'A', 0, True)), 1)

    def test_phone_reveal_does_not_stop_before_wechat(self):
        page = MagicMock()
        page.url = 'https://buyin.example/profile'
        page.locator.return_value.inner_text.return_value = '达人自主披露联系方式 粉丝数'
        page.title.return_value = '达人详情'
        row = {'buyin_profile_url': page.url, 'content_evidence_reviewed': True,
               'buyin_contact_email': 'creator@example.com'}
        clicks = []
        def dispatch(event):
            if event == 'click':
                clicks.append(event)
        page.locator.return_value.nth.return_value.locator.return_value.dispatch_event.side_effect = dispatch
        def items(_page):
            return ['达人手机号：13800138000'] + (['达人微信号：creator_wx'] if len(clicks) >= 2 else ['达人微信号：********'])
        def icons(_page):
            return [{'idx': i, 'text': '********'} for i in range(len(clicks), 2)]
        with tempfile.TemporaryDirectory() as out, patch.object(single, 'contact_items', items), patch.object(single, 'contact_icons', icons), patch.object(single, 'visible_buttons', return_value=[]), patch.object(single, 'wait_for_global_contact_slot', return_value=0), patch.object(single, 'confirm_contact_view', return_value={'status': 'not_present'}), patch.object(single, 'page_message', return_value=''):
            result = single.run_candidate(page, row, 3000, Path(out))
        self.assertEqual(len(clicks), 2)
        self.assertEqual(result['buyin_contact_wechat'], 'creator_wx')
        self.assertEqual(result['buyin_contact_phone'], '13800138000')
        self.assertEqual(result['buyin_contact_email'], 'creator@example.com')
        self.assertEqual(result['ui_contact_channels_status'], 'complete')

    def test_partial_contact_preserves_quota_stop(self):
        page = MagicMock()
        page.url = 'https://buyin.example/profile'
        page.locator.return_value.inner_text.return_value = '达人自主披露联系方式 粉丝数'
        page.title.return_value = '达人详情'
        row = {'buyin_profile_url': page.url, 'content_evidence_reviewed': True,
               'buyin_contact_phone': '13800138000'}
        icons = [{'idx': 1, 'text': '达人微信号：********'}]
        with tempfile.TemporaryDirectory() as out, patch.object(single, 'contact_items', return_value=['达人手机号：13800138000', '达人微信号：********']), patch.object(single, 'contact_icons', return_value=icons), patch.object(single, 'visible_buttons', return_value=[]), patch.object(single, 'wait_for_global_contact_slot', return_value=0), patch.object(single, 'confirm_contact_view', return_value={'status': 'daily_quota_exhausted', 'remaining': 0}), patch.object(single, 'page_message', return_value=''):
            result = single.run_candidate(page, row, 3000, Path(out))
        self.assertEqual(result['ui_contact_probe_status'], 'daily_quota_exhausted')
        self.assertEqual(result['ui_contact_channels_status'], 'daily_quota_exhausted')
        self.assertEqual(result['buyin_contact_phone'], '13800138000')
        self.assertTrue(single.should_stop_contact_batch(result))

    def test_proven_duplicate_skips_second_reveal_but_keeps_first_plaintext(self):
        page = MagicMock()
        page.url = 'https://buyin.example/profile'
        page.locator.return_value.inner_text.return_value = '达人自主披露联系方式 粉丝数'
        page.title.return_value = '达人详情'
        page.evaluate.return_value = False
        clicks = []
        page.locator.return_value.nth.return_value.locator.return_value.dispatch_event.side_effect = lambda event: clicks.append(event) if event == 'click' else None
        def items(_):
            return ['达人手机号：13800138000' if clicks else '达人手机号：********', '达人微信号：********']
        def icons(_):
            return [{'idx': i, 'text': '********'} for i in range(len(clicks), 2)]
        with tempfile.TemporaryDirectory() as out, patch.object(single, 'contact_items', items), patch.object(single, 'contact_icons', icons), patch.object(single, 'visible_buttons', return_value=[]), patch.object(single, 'wait_for_global_contact_slot', return_value=0) as slot, patch.object(single, 'confirm_contact_view', return_value={'status': 'not_present'}), patch.object(single, 'page_message', return_value=''):
            result = single.run_candidate(page, {'buyin_profile_url': page.url, 'content_evidence_reviewed': True}, 3000, Path(out), stop_if_duplicate=lambda row: row.get('buyin_contact_phone') == '13800138000')
        self.assertEqual(len(clicks), 1)
        self.assertEqual(slot.call_count, 1)
        self.assertEqual(result['buyin_contact_phone'], '13800138000')
        self.assertEqual(result['ui_contact_remaining_skipped_reason'], 'strict_contact_duplicate')


    def test_supplement_collision_retains_original_phone_and_evidence(self):
        originals = [{'identity': 'a', 'buyin_contact_phone': '13800138000', 'evidence_sha256': 'original'}]
        updates = [{**originals[0], 'buyin_contact_wechat': 'prior_wx', 'evidence_sha256': 'changed'}]
        result = retain_unique_supplements(originals, updates, {'excludeContacts': ['prior_wx']})[0]
        self.assertEqual(result['buyin_contact_wechat'], '')
        self.assertEqual(result['buyin_contact_phone'], '13800138000')
        self.assertEqual(result['evidence_sha256'], 'original')
        self.assertEqual(result['ui_contact_supplement_duplicate_channels'], ['wechat'])

if __name__ == '__main__':
    unittest.main()
