import unittest
from contact_corrections import apply_corrections
from creator_delivery_contract import contact_identity_values
class ContactCorrectionsTest(unittest.TestCase):
    def test_revision_replaces_all_aliases_without_mutating_original_or_admission(self):
        row={"identity":"a","buyin_contact_wechat":"old","cart_contact_phone":"13800138000","precontact_qualified":True,"contact_acquired_at":"2026-10-01T00:00:00Z"}
        records=[{"creatorId":"a","after":{"wechat":"1234567890","phone":"","email":""},"source":"合成来源","recordedAt":"2026-10-08T00:00:00Z","revision":1}]
        new=apply_corrections([row],records)[0]
        self.assertEqual(row["buyin_contact_wechat"],"old")
        self.assertEqual(new["cart_contact_phone"],"")
        self.assertTrue(new["precontact_qualified"])
        self.assertEqual(set(contact_identity_values(new)),{"1234567890"})
        self.assertEqual(new["plain_contact"],"1234567890")
        self.assertEqual(new["contact_correction_revision"],1)
        self.assertEqual(new["contact_acquired_at"],"2026-10-01T00:00:00Z")
        self.assertEqual(new["contact_corrected_at"],records[0]["recordedAt"])

    def test_new_delivery_uses_correction_in_json_excel_and_both_queues(self, automatic=False):
        import tempfile, json, os, subprocess, sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'delivery';output.mkdir()
            row={"identity":"creator-1","nickname":"合成达人","talent_level":"3","buyin_profile_url":"https://buyin.example/1","douyin_homepage":"https://douyin.example/1","profile_verified":True,"content_evidence_reviewed":True,"content_evidence":["真人口播 精致场景"],"monthly_sales_value":200000,"buyin_contact_wechat":"wx_original"}
            source=root/'strict.json';source.write_text(json.dumps({"status":"complete","contact_dedup_mode":"strict-any-plaintext-value","strict_selected_count":1,"audit":{"identity_unique":True,"contact_values_unique":True,"cross_round_contact_overlap":0},"candidates":[row]}))
            strategy=root/'strategy.json';strategy.write_text(json.dumps({"targetCount":1,"threshold":78,"exclusions":[]}))
            corrections=root/'corrections.json';corrections.write_text(json.dumps({"schema":"qianxun-contact-corrections-v1","taskId":"test","records":[{"creatorId":"creator-1","after":{"wechat":"1234567890","phone":"","email":""},"source":"合成来源","recordedAt":"2026-10-08T00:00:00Z","revision":1}]}))
            env={**os.environ,"AIPR_CONTACT_CORRECTIONS":str(corrections),"JEV_INTEGRATION":"0","JEV_CONFIG_DIR":temp,"AIPR_JEV_API_KEY":"","AIPR_JEV_SAVED_ONLY":"1"}
            process=subprocess.run([sys.executable,str(Path(__file__).with_name('finalize_creator_delivery.py')),'--input',str(source),'--strategy',str(strategy),'--out-dir',str(output),'--task-id','test','--task-name','合成测试',*([] if automatic else ['--deliver-current']),'--require-strict-highwater'],env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            final=Path(json.loads(process.stdout.strip().splitlines()[-1])['output']);delivery=json.loads(final.read_text())
            self.assertEqual(delivery['rows'][0]['微信'],'1234567890')
            self.assertEqual(delivery['contact_corrections_revision'],1)
            self.assertEqual(delivery['rows'][0]['联系方式获取时间'],'')
            self.assertEqual(delivery['rows'][0]['联系方式修订时间'],'2026-10-08T00:00:00Z')
            self.assertEqual(json.loads(source.read_text())['candidates'][0]['buyin_contact_wechat'],'wx_original')
            check=subprocess.run([sys.executable,str(Path(__file__).with_name('validate_delivery.py')),'--source',str(final)],env=env,capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)
            self.assertTrue(json.loads(check.stdout)['ok'],check.stdout)

    def test_automatic_pipeline_finalizer_keeps_contact_revisions(self):
        self.test_new_delivery_uses_correction_in_json_excel_and_both_queues(automatic=True)
