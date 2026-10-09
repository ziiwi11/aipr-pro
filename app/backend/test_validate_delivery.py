import json
import tempfile
import unittest
from pathlib import Path
import openpyxl
from validate_delivery import validate

class ValidationTests(unittest.TestCase):
    def fixture(self,root):
        row={'主页身份ID':'sample','微信':'wx-sample','手机号':'13800138000','邮箱':''}
        record={'creator':{'id':'sample','contact':{'wechat':'wx-sample','phone':'13800138000','email':''}},'guardrails':{'allowAutomaticSend':False}}
        workbook=openpyxl.Workbook();sheet=workbook.active;sheet.append(list(row));sheet.append(list(row.values()));workbook.save(root/'list.xlsx')
        (root/'queue.ndjson').write_text(json.dumps(record)+'\n')
        (root/'batch.json').write_text(json.dumps({'dryRunOnly':True,'records':[record]}))
        (root/'manifest.json').write_text(json.dumps({'summary':{'candidateCount':1,'robotRecordCount':1}}))
        data={'rows':[row],'robot_queue':[record],'artifacts':{'standardXlsx':str(root/'list.xlsx'),'robotNdjson':str(root/'queue.ndjson'),'robotBatchJson':str(root/'batch.json'),'handoffManifest':str(root/'manifest.json'),'originalXlsx':''}}
        (root/'final.json').write_text(json.dumps(data));return root/'final.json'
    def test_exact_files_pass_and_hashes_are_recorded_without_sending(self):
        with tempfile.TemporaryDirectory() as temp:
            source=self.fixture(Path(temp));result=validate(source)
            self.assertTrue(result['ok']);self.assertEqual(result['rowCount'],1);self.assertEqual(len(result['files']),5);self.assertFalse(result['sentVerified'])
            self.assertTrue(all(len(file['sha256'])==64 for file in result['files']))
    def test_equal_counts_but_different_contacts_or_unprotected_queue_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=self.fixture(root)
            batch=json.loads((root/'batch.json').read_text());batch['records'][0]['creator']['contact']['wechat']='changed';batch['records'][0]['guardrails']['allowAutomaticSend']=True;(root/'batch.json').write_text(json.dumps(batch))
            result=validate(source);self.assertFalse(result['ok']);self.assertTrue(any('不一致' in error for error in result['errors']));self.assertTrue(any('自动发送' in error for error in result['errors']))
    def test_dangling_contact_baseline_is_not_hidden_by_consistent_delivery_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=self.fixture(root);delivery=json.loads(source.read_text())
            delivery['contact_channel_completion']={'baseline_path':str(root/'missing.json'),'new_wechat_count':1}
            source.write_text(json.dumps(delivery));result=validate(source)
            self.assertFalse(result['ok']);self.assertTrue(any('基线文件不存在' in error for error in result['errors']))
    def test_unknown_completion_baseline_is_allowed_without_claiming_new_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            source=self.fixture(Path(temp));delivery=json.loads(source.read_text())
            delivery['contact_channel_completion']={'baseline_path':'','baseline_available':False,'new_wechat_count':None}
            source.write_text(json.dumps(delivery));self.assertTrue(validate(source)['ok'])
