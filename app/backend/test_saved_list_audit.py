import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from audit_strict_contact_highwater import reaudit_saved_task


class SavedListAuditTest(unittest.TestCase):
    def test_recovery_reads_all_saved_sources_and_forbids_paid_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {'candidates': [{'identity': 'old', 'jev_analysis': {'route': 'supported'}}]}
            (root/'aipr_strict_contact_highwater.json').write_text(json.dumps(old))
            (root/'aipr_contact_highwater.json').write_text(json.dumps({'candidates': [{'identity': 'retained'}]}))
            (root/'aipr_realtime_creator_flow.json').write_text(json.dumps({'records': [{'row': {'identity': 'flow'}}]}))
            def audit(payload, rules, historical, target, progress):
                self.assertEqual(os.environ['AIPR_JEV_SAVED_ONLY'], '1')
                self.assertEqual([r['identity'] for r in payload['candidates']], ['old', 'retained', 'flow'])
                self.assertEqual(rules['contentFitCategory'], '美妆个护')
                return {'candidates': [payload['candidates'][0]], 'strict_selected_count': 1}
            with patch('audit_strict_contact_highwater.build_strict_contact_highwater', side_effect=audit), patch.dict(os.environ, {'AIPR_JEV_SAVED_ONLY': 'original'}):
                result = reaudit_saved_task(root, {'targetCount': 20, 'contentFitCategory': '美妆个护'})
                self.assertEqual(os.environ['AIPR_JEV_SAVED_ONLY'], 'original')
            self.assertEqual(json.loads(Path(result['previous_snapshot']).read_text()), old)
            self.assertEqual(json.loads((root/'aipr_strict_contact_highwater.json').read_text())['strict_selected_count'], 1)

    def test_unreadable_source_cannot_replace_formal_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old='{"candidates":[{"identity":"preserved"}]}'
            (root/'aipr_strict_contact_highwater.json').write_text(old)
            (root/'aipr_contact_highwater.json').write_text('{broken')
            with self.assertRaises(ValueError):
                reaudit_saved_task(root, {})
            self.assertEqual((root/'aipr_strict_contact_highwater.json').read_text(), old)

    def test_backup_failure_aborts_formal_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old='{"candidates":[]}'
            (root/'aipr_strict_contact_highwater.json').write_text(old)
            with patch('audit_strict_contact_highwater.build_strict_contact_highwater', return_value={'candidates': []}), patch('audit_strict_contact_highwater.atomic_write_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): reaudit_saved_task(root, {})
            self.assertEqual((root/'aipr_strict_contact_highwater.json').read_text(), old)

    def test_unchanged_policy_cannot_silently_remove_formal_creators(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old='{"candidates":[{"identity":"preserved"}]}'
            (root/'aipr_strict_contact_highwater.json').write_text(old)
            with patch('audit_strict_contact_highwater.build_strict_contact_highwater', return_value={'candidates': [], 'strict_selected_count': 0}):
                with self.assertRaisesRegex(ValueError, 'saved_audit_requires_review'):
                    reaudit_saved_task(root, {})
            self.assertEqual((root/'aipr_strict_contact_highwater.json').read_text(), old)
            self.assertTrue(json.loads((root/'aipr_saved_list_audit_pending_review.json').read_text())['requires_review'])

    def test_frozen_baseline_owns_shared_contact_and_requires_review_before_replace(self):
        from test_strict_contact_highwater import candidate, RULES
        from audit_strict_contact_highwater import apply_pending_saved_audit
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JEV_INTEGRATION':'0'}):
            root=Path(directory); rules={**RULES,'brief':'same task','targetCount':20}
            accepted=candidate('accepted','shared-contact');other=candidate('replacement','shared-contact');new=candidate('new','unique-contact')
            current={'candidates':[other,new]}; old_text=json.dumps(current)
            (root/'aipr_strict_contact_highwater.json').write_text(old_text)
            baseline=root/'baseline.json';baseline.write_text(json.dumps({'candidates':[accepted],'strategy':{'brief':'same task'}}))
            with self.assertRaisesRegex(ValueError,'saved_audit_requires_review'):
                reaudit_saved_task(root,rules,baseline_path=baseline)
            self.assertEqual((root/'aipr_strict_contact_highwater.json').read_text(),old_text)
            pending=json.loads((root/'aipr_saved_list_audit_pending_review.json').read_text())
            self.assertEqual([x['identity'] for x in pending['candidates']],['accepted','new'])
            self.assertEqual(pending['baseline_missing_count'],0)
            result=apply_pending_saved_audit(root,rules)
            self.assertEqual([x['identity'] for x in result['candidates']],['accepted','new'])
            self.assertEqual(json.loads(Path(result['previous_snapshot']).read_text()),current)

    def test_stale_review_and_changed_brief_cannot_mutate_saved_list(self):
        from test_strict_contact_highwater import candidate, RULES
        from audit_strict_contact_highwater import apply_pending_saved_audit
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JEV_INTEGRATION':'0'}):
            root=Path(directory);rules={**RULES,'brief':'original task','targetCount':20}
            accepted=candidate('accepted','shared');other=candidate('other','shared')
            strict=root/'aipr_strict_contact_highwater.json';strict.write_text(json.dumps({'candidates':[other]}))
            baseline=root/'baseline.json';baseline.write_text(json.dumps({'candidates':[accepted],'strategy':{'brief':'original task'}}))
            with self.assertRaisesRegex(ValueError,'baseline_brief_changed'):
                reaudit_saved_task(root,{**rules,'brief':'another task'},baseline_path=baseline)
            with self.assertRaisesRegex(ValueError,'requires_review'):
                reaudit_saved_task(root,rules,baseline_path=baseline)
            changed=json.dumps({'candidates':[other], 'modified':True});strict.write_text(changed)
            with self.assertRaisesRegex(ValueError,'review_expired'):
                apply_pending_saved_audit(root,rules)
            self.assertEqual(strict.read_text(),changed)
