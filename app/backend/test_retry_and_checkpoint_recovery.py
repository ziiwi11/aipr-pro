import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from realtime_creator_processor import RealtimeCreatorProcessor
from realtime_creator_flow import RealtimeCreatorFlowStore, is_terminal_state
from creator_delivery_contract import mark_precontact_qualification

class RetryAndCheckpointRecoveryTests(unittest.TestCase):
    def test_missing_profile_evidence_is_pending_not_unsuitable(self):
        with tempfile.TemporaryDirectory() as directory, patch('jev_local_client.decision_enabled', return_value=False):
            p = RealtimeCreatorProcessor(Path(directory), {},
                verify_candidate=lambda *_args, **_kwargs: {'identity': 'pending', 'content_evidence_reviewed': True,
                    'douyin_homepage': 'https://example.test/user/pending', 'profile_verified': False},
                reveal_contact=lambda *a, **k: self.fail('No contact reveal before evidence'))
            row = p.process(None, None, {'identity': 'pending'})
            self.assertEqual(row['precontact_decision'], '待内容复核')
            self.assertEqual(row['realtime_flow_state'], 'evidence_reviewing')

    def test_transient_disconnect_is_retryable_and_eventually_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def verify(_ctx, row, *_args, **_kwargs):
                calls.append(row['identity'])
                if len(calls) == 1: raise ConnectionError('connection closed')
                return {**row, 'content_evidence_reviewed': False}
            p = RealtimeCreatorProcessor(Path(directory), {}, verify_candidate=verify)
            first = p.process(None, None, {'identity': 'retry'})
            self.assertEqual(first['realtime_flow_state'], 'retry_pending')
            self.assertFalse(is_terminal_state(first['realtime_flow_state']))
            # Restarting the software must retain the retry count and source row.
            p = RealtimeCreatorProcessor(Path(directory), {}, verify_candidate=verify)
            second = p.process(None, None, {'identity': 'retry'})
            self.assertEqual(len(calls), 2)
            self.assertEqual(second['transient_retry_count'], 1)

    def test_transient_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            def verify(*a, **k): raise TimeoutError('network timeout')
            p = RealtimeCreatorProcessor(Path(directory), {}, verify_candidate=verify)
            states = [p.process(None, None, {'identity': 'retry'})['realtime_flow_state'] for _ in range(4)]
            self.assertEqual(states, ['retry_pending'] * 3 + ['error'])
            self.assertEqual(p.process(None, None, {'identity': 'retry'})['transient_retry_count'], 4)

    def test_programming_errors_are_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            def verify(*a, **k): raise ValueError('bad configuration')
            p = RealtimeCreatorProcessor(Path(directory), {}, verify_candidate=verify)
            self.assertEqual(p.process(None, None, {'identity': 'bad'})['realtime_flow_state'], 'error')

    def test_corrupt_checkpoint_uses_valid_backup_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flow.json'
            s = RealtimeCreatorFlowStore(path)
            s.record('a', 'discovered', {'identity': 'a'})
            s.record('a', 'listed', {'identity': 'a', 'buyin_contact_wechat': 'wx_saved'})
            path.write_text('{broken')
            recovered = RealtimeCreatorFlowStore(path)
            self.assertEqual(recovered.get('a')['state'], 'discovered')
            recovered.record('b', 'discovered', {'identity': 'b'})
            self.assertEqual(len(recovered.rows()), 2)
            self.assertEqual(json.loads(path.with_suffix('.json.bak').read_text())['records'][0]['identity'], 'a')

    def test_two_corrupt_checkpoints_stop_without_erasing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flow.json'; path.write_text('{broken')
            path.with_suffix('.json.bak').write_text('{broken backup')
            with self.assertRaisesRegex(ValueError, 'flow_checkpoint_and_backup_unreadable'):
                RealtimeCreatorFlowStore(path)
            self.assertEqual(path.read_text(), '{broken')

    def test_legacy_missing_evidence_is_migrated_but_real_rejections_stay_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flow.json'
            s = RealtimeCreatorFlowStore(path)
            s.record('pending', 'unsuitable', {'identity': 'pending'}, '抖音主页或近期内容证据尚未完成复核')
            s.record('rejected', 'unsuitable', {'identity': 'rejected'}, '销售额不足')
            reopened = RealtimeCreatorFlowStore(path)
            self.assertEqual(reopened.get('pending')['state'], 'evidence_reviewing')
            self.assertEqual(reopened.get('rejected')['state'], 'unsuitable')

if __name__ == '__main__': unittest.main()
