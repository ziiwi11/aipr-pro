import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_and_contact_pipeline as pipeline


class PartialSourceReplenishmentTests(unittest.TestCase):
    def test_short_category_pool_preserves_category_mode_and_stops_without_keyword_fallback(self):
        class NextCollection(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy_path = root / 'strategy.json'
            strategy_path.write_text(json.dumps({
                'targetCount': 500, 'category': '美妆个护', 'keywords': ['唇部护理'],
                'sourceDiscoveryMode': 'structured_browse', 'activeShops': ['A'],
                'maxReplenishmentRounds': 2,
            }))
            pool = root / 'pool.json'
            pool.write_text(json.dumps({'candidates': [{'identity': str(i)} for i in range(297)]}))
            (root / 'aipr_contact_highwater.json').write_text('{"candidates": []}')
            attempts = []

            def collect(command):
                attempts.append(json.loads(strategy_path.read_text()))
                if len(attempts) == 2:
                    raise NextCollection()
                return 7, [
                    {'status': 'collection_checkpoint_saved', 'output': str(pool)},
                    {'status': 'collection_incomplete'},
                ]

            with patch('sys.argv', ['pipeline', '--strategy', str(strategy_path), '--out-dir', str(root)]), \
                    patch.object(pipeline, 'prune_automation_pages', return_value=0), \
                    patch.object(pipeline, 'load_verified_candidate_seed', return_value=None), \
                    patch.object(pipeline, 'resumable_collection_pool', return_value=None), \
                    patch.object(pipeline, 'run_collection_with_retry', side_effect=collect), \
                    patch.object(pipeline, 'run_stream', return_value=(0, [])) as similar, \
                    patch.object(pipeline, 'emit'):
                with self.assertRaises(SystemExit) as stopped:
                    pipeline.main()
                self.assertEqual(stopped.exception.code, 7)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(json.loads(strategy_path.read_text())['sourceDiscoveryMode'], 'structured_browse')
            self.assertEqual(json.loads(strategy_path.read_text())['keywords'], ['唇部护理'])
            self.assertEqual(similar.call_count, 1)
            self.assertEqual(similar.call_args.args[0][similar.call_args.args[0].index('--shop') + 1], 'A')
            self.assertEqual(len(json.loads(pool.read_text())['candidates']), 297)

    def test_empty_or_missing_checkpoint_cannot_be_promoted(self):
        self.assertIsNone(pipeline.usable_partial_collection({'output': 'pool.json'}, 0))
        self.assertIsNone(pipeline.usable_partial_collection({}, 297))

    def test_platform_pause_remains_a_stop_condition(self):
        self.assertFalse(pipeline.collection_ended_without_platform_pause([
            {'status': 'collection_checkpoint_saved', 'output': 'pool.json'},
            {'status': 'platform_paused'},
        ]))


if __name__ == '__main__':
    unittest.main()
