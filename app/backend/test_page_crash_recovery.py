import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from realtime_creator_processor import RealtimeCreatorProcessor
from realtime_creator_flow import RealtimeCreatorFlowStore
from collect_buyin_creators_cdp import process_new_candidate_identities, resume_retry_candidates, resume_contact_candidates
from collect_buyin_creators_cdp import RealtimeDeliveryTargetReached
import collect_and_contact_pipeline as pipeline

class PageCrashRecoveryTests(unittest.TestCase):
    def test_full_formal_target_stops_before_next_contact_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {"targetCount": 1})
            def complete(_context, _page, row):
                processor.strict_path.write_text(json.dumps({"status":"complete", "strict_selected_count":1,
                    "candidates":[{"identity":"first"}]}))
                return {**row, "realtime_flow_state":"listed"}
            output = {"first":{"identity":"first"}, "next":{"identity":"next"}}
            with patch.object(processor, 'process', side_effect=complete) as process:
                with self.assertRaises(RealtimeDeliveryTargetReached):
                    process_new_candidate_identities(output, list(output), processor, None, None)
                self.assertEqual(process.call_count, 1)
            self.assertEqual(output['first']['realtime_flow_state'], 'listed')
            with patch.object(processor, 'process') as process:
                with self.assertRaises(RealtimeDeliveryTargetReached):
                    process_new_candidate_identities(output, ['next'], processor, None, None)
                process.assert_not_called()

    def test_unfulfilled_or_invalid_formal_checkpoint_does_not_stop_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {"targetCount":2})
            for payload in [{"status":"checkpoint","strict_selected_count":2,"candidates":[{},{}]},
                            {"status":"complete","strict_selected_count":2,"candidates":[{}]},
                            {"status":"complete","strict_selected_count":1,"candidates":[{},{}]}]:
                processor.strict_path.write_text(json.dumps(payload))
                self.assertFalse(processor.delivery_target_reached())
            processor.strict_path.write_text('{invalid')
            self.assertFalse(processor.delivery_target_reached())

    def test_contact_resume_uses_ledger_when_replenishment_pool_omits_saved_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {})
            for identity, state, shop in [('contact','contact_revealing','A'),
                    ('plain','plaintext_unique','A'), ('other','contact_revealing','B'),
                    ('listed','listed','A')]:
                processor.flow.record(identity,state,{'identity':identity,'shop':shop})
            output = {}
            with patch('collect_buyin_creators_cdp.process_new_candidate_identities',
                    return_value={'processed':2,'paused':False}) as process:
                result = resume_contact_candidates(output,processor,None,None,'A')
            self.assertEqual(result['processed'],2)
            self.assertEqual(process.call_args.args[1],['contact','plain'])
            self.assertEqual(set(output),{'contact','plain'})

    def test_contact_resume_preserves_shop_cooldown_without_contact_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {})
            processor.flow.record('contact','contact_revealing',{'identity':'contact','shop':'A'})
            with patch('contact_shop_cooldown.shop_cooldown_until',return_value=float('inf')), \
                    patch('collect_buyin_creators_cdp.process_new_candidate_identities') as process:
                result = resume_contact_candidates({},processor,None,None,'A')
            self.assertEqual(result,{'processed':0,'paused':True})
            process.assert_not_called()
            self.assertEqual(processor.flow.get('contact')['state'],'contact_revealing')

    def test_daily_quota_pause_is_retained_during_contact_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {})
            row={'identity':'contact','shop':'A','realtime_flow_reason':'daily_quota_exhausted'}
            processor.flow.record('contact','contact_revealing',row,'daily_quota_exhausted')
            with patch.object(processor,'process',return_value=row) as process:
                result = resume_contact_candidates({},processor,None,None,'A')
            self.assertEqual(result,{'processed':1,'paused':True})
            self.assertEqual(process.call_count,1)

    def test_reconnect_retries_saved_creator_in_same_shop_without_repeating_listed_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def verify(_context, row, *args, **kwargs):
                calls.append(row['identity'])
                return {**row,'evidence_status':'content_unverified','content_evidence_reviewed':False}
            processor = RealtimeCreatorProcessor(Path(directory),{},verify_candidate=verify)
            processor.flow.record('retry','retry_pending',{'identity':'retry','shop':'A'})
            processor.flow.record('other','retry_pending',{'identity':'other','shop':'B'})
            processor.flow.record('listed','listed',{'identity':'listed','shop':'A','buyin_contact_wechat':'wx_saved'})
            output = {}; result = resume_retry_candidates(output,processor,None,None,'A')
            self.assertEqual(calls,['retry'])
            self.assertEqual(result['processed'],1)
            self.assertEqual(list(output),['retry'])
            self.assertEqual(processor.flow.get('listed')['state'],'listed')

    def test_explicit_resume_rechecks_cloud_failure_and_payment_but_not_model_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {})
            for identity, analysis in [('cloud', {'error_type': 'HTTPError'}),
                    ('uncertain', {'route': 'uncertain'}),
                    ('payment', {'error_type': 'HTTPError', 'http_status': 402,
                                 'action_required': True, 'retryable': False})]:
                processor.flow.record(identity, 'evidence_reviewing',
                    {'identity': identity, 'shop': 'A', 'jev_analysis': analysis})
            with patch.object(processor, 'process', return_value={'realtime_flow_reason': ''}) as process:
                result = resume_retry_candidates({}, processor, None, None, 'A')
            self.assertEqual(result['processed'], 2)
            self.assertEqual([call.args[2]['identity'] for call in process.call_args_list], ['cloud', 'payment'])

    def test_payment_failure_stops_before_processing_more_creators(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = RealtimeCreatorProcessor(Path(directory), {})
            output = {'first': {'identity': 'first'}, 'second': {'identity': 'second'}}
            with patch.object(processor, 'process', return_value={'jev_analysis':
                    {'action_required': True, 'http_status': 402}}) as process:
                with self.assertRaisesRegex(RuntimeError, 'HTTP 402'):
                    process_new_candidate_identities(output, list(output), processor, None, None)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(output['first']['jev_analysis']['http_status'], 402)

    def test_returned_crash_is_retry_pending_and_never_reveals_contacts(self):
        with tempfile.TemporaryDirectory() as directory:
            def verify(_context, row, *args, **kwargs):
                return {**row, 'evidence_status': 'error', 'evidence_error': 'Page.goto: Page crashed'}
            processor = RealtimeCreatorProcessor(Path(directory), {}, verify_candidate=verify,
                reveal_contact=lambda *a, **k: self.fail('unverified contact reveal'))
            result = processor.process(None, None, {'identity': 'crashed'})
            self.assertEqual(result['realtime_flow_state'], 'retry_pending')
            self.assertEqual(result['transient_retry_count'], 1)
            output = {'crashed': {'identity': 'crashed'}, 'next': {'identity': 'next'}}
            with self.assertRaisesRegex(RuntimeError, 'realtime_page_crashed'):
                process_new_candidate_identities(output, list(output), processor, None, None)
            self.assertEqual(output['crashed']['realtime_flow_state'], 'retry_pending')
            self.assertIsNone(processor.flow.get('next'))

    def test_old_crash_rejections_are_reopened_but_real_missing_evidence_stays(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flow.json'; store = RealtimeCreatorFlowStore(path)
            store.record('crashed', 'insufficient_evidence', {'identity':'crashed','evidence_status':'error',
                'evidence_error':'Page.goto: Page crashed'}, 'error')
            store.record('missing', 'insufficient_evidence', {'identity':'missing','evidence_status':'content_unverified'})
            store.record('listed', 'listed', {'identity':'listed','buyin_contact_wechat':'wx_test'})
            reopened = RealtimeCreatorFlowStore(path)
            self.assertEqual(reopened.get('crashed')['state'], 'retry_pending')
            self.assertEqual(reopened.get('missing')['state'], 'insufficient_evidence')
            self.assertEqual(reopened.get('listed')['state'], 'listed')
            self.assertTrue(path.with_suffix('.json.bak').exists())

    def test_collector_crash_reconnects_with_bounded_backoff(self):
        failure = (7, [{'status':'shop_error','message':'realtime_page_crashed'}])
        with patch.object(pipeline,'run_stream',return_value=failure) as run, patch.object(pipeline,'emit'):
            waits = []; code, events = pipeline.run_collection_with_retry(['fake-worker'],sleeper=waits.append)
        self.assertEqual(code, 7)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len(waits), 2)
        self.assertGreaterEqual(waits[0], 30)

if __name__ == '__main__': unittest.main()
