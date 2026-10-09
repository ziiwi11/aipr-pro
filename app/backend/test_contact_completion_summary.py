import json
import tempfile
import unittest
from pathlib import Path
from finalize_creator_delivery import contact_completion_summary


class ContactCompletionSummaryTests(unittest.TestCase):
    def test_missing_baseline_does_not_turn_existing_wechat_into_new_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing.json'
            result = contact_completion_summary([{'identity': 'one', 'buyin_contact_wechat': 'known', 'ui_contact_channels_checked_at': 'now'}], 20, path)
            self.assertEqual(result['checked_count'], 1)
            self.assertIsNone(result['new_wechat_count'])
            self.assertFalse(result['baseline_available'])
            self.assertEqual(result['baseline_path'], '')
            self.assertFalse(path.exists())

    def test_rotated_identity_and_unchecked_rows_do_not_inflate_supplement_count(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'before.json'
            path.write_text(json.dumps({'candidates': [{'identity': 'old', 'douyin_id': 'same', 'buyin_contact_wechat': 'kept'}]}))
            rows = [
                {'identity': 'new-encrypted', 'douyin_id': 'same', 'buyin_contact_wechat': 'kept', 'ui_contact_channels_checked_at': 'now'},
                {'identity': 'new-person', 'buyin_contact_wechat': 'added', 'ui_contact_channels_checked_at': 'now'},
                {'identity': 'unrelated-unchecked', 'buyin_contact_wechat': 'later'},
            ]
            result = contact_completion_summary(rows, 20, path)
            self.assertEqual(result['new_wechat_count'], 1)
            self.assertTrue(result['baseline_available'])
            self.assertEqual(result['baseline_path'], str(path))

    def test_invalid_baseline_remains_unknown_without_creating_a_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.json'
            path.write_text('{broken')
            result = contact_completion_summary([], 20, path)
            self.assertIsNone(result['new_wechat_count'])
            self.assertEqual(result['baseline_status'], 'unreadable')
            self.assertEqual(path.read_text(), '{broken')
