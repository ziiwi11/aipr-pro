import unittest
from unittest.mock import patch
import creator_delivery_contract as contract

class JevAdmissionTest(unittest.TestCase):
    candidate = {'profile_verified': True, 'douyin_homepage': 'https://www.douyin.com/user/test',
                 'content_evidence_reviewed': True, 'recent_titles': ['面霜真人口播试用'],
                 'buyin_contact_wechat': 'test-only', 'talent_level': 'LV2', 'monthly_sales': '¥100000'}
    rules = {'category': '美妆个护', 'contentType': '真人口播', 'brief': '真人展示面霜使用体验'}

    def assess(self, route):
        with patch('jev_local_client.decision_enabled', return_value=True), patch('creator_jev.review', return_value={'enabled': True, 'route': route, 'confidence': .9, 'needs_review': True}):
            return contract.score_candidate(dict(self.candidate), self.rules)

    def test_semantic_match_can_pass_without_literal_keywords(self):
        r=self.assess('supported')
        self.assertEqual(r['decision'], '推荐建联')
        self.assertFalse(r['jev_analysis']['auto_send_allowed'])
        self.assertFalse(r['jev_analysis']['needs_review'])

    def test_conflict_leaves_formal_list(self):
        r=self.assess('review_conflict')
        self.assertEqual(r['decision'], '暂不推荐')
        self.assertTrue(r['jev_analysis']['admission_changed'])
        self.assertTrue(r['jev_analysis']['needs_review'])

    def test_uncertainty_requires_review(self):
        r=self.assess('uncertain')
        self.assertEqual(r['decision'], '待内容复核')
        self.assertTrue(r['jev_analysis']['needs_review'])

    def test_failure_cannot_pass(self):
        with patch('jev_local_client.decision_enabled',return_value=True),patch('creator_jev.review',return_value={'enabled':True,'route':'uncertain','reason':'服务不可用'}):
            self.assertEqual(contract.score_candidate(self.candidate,self.rules)['decision'],'待内容复核')

    def test_hard_sales_gate_survives_semantic_match(self):
        with patch('jev_local_client.decision_enabled',return_value=True),patch('creator_jev.review') as review:
            r=contract.score_candidate(self.candidate,{**self.rules,'minimumMonthlySales':200000})
            self.assertEqual(r['decision'],'淘汰');review.assert_not_called()

    def test_uncertain_stays_pending_in_realtime_flow(self):
        import tempfile
        from pathlib import Path
        from realtime_creator_processor import RealtimeCreatorProcessor
        def qualify(row, rules):
            return {**row, 'precontact_qualified': False, 'precontact_reason': 'Jev 待复核',
                    'jev_analysis': {'route': 'uncertain'}}
        with tempfile.TemporaryDirectory() as tmp:
            processor=RealtimeCreatorProcessor(Path(tmp), self.rules,
                verify_candidate=lambda *args, **kwargs: {**args[1], 'content_evidence_reviewed': True},
                qualify_candidate=qualify, reveal_contact=lambda *args, **kwargs: self.fail('Must not reveal contact'))
            row=processor.process(None,None,{**self.candidate,'identity':'test-jev'})
            self.assertEqual(row['realtime_flow_state'],'evidence_reviewing')

    def test_uncertain_does_not_enter_selection_or_robot_queue(self):
        with patch('jev_local_client.decision_enabled',return_value=True),patch('creator_jev.review',return_value={'enabled':True,'route':'uncertain'}):
            self.assertEqual(contract.select_delivery_candidates([self.candidate],self.rules,1),[])
            delivery=contract.build_delivery([self.candidate],self.rules,'test')
            self.assertEqual(delivery['robot_queue'],[])

    def test_platform_limit_remains_retryable_and_does_not_reveal_contact(self):
        import tempfile
        from pathlib import Path
        from realtime_creator_processor import RealtimeCreatorProcessor
        with tempfile.TemporaryDirectory() as tmp:
            processor = RealtimeCreatorProcessor(Path(tmp), self.rules,
                verify_candidate=lambda *args, **kwargs: {**args[1],
                    'content_evidence_reviewed': False, 'evidence_status': 'rate_limited'},
                reveal_contact=lambda *args, **kwargs: self.fail('Must wait for platform recovery'))
            row = processor.process(None, None, {**self.candidate, 'identity': 'limited'})
            self.assertEqual(row['realtime_flow_state'], 'evidence_reviewing')
            self.assertEqual(row['realtime_flow_reason'], 'rate_limited')

if __name__=='__main__':unittest.main()
