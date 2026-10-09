from __future__ import annotations

import json
import os
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from realtime_creator_flow import RealtimeCreatorFlowStore


class FinalizeHandoffTest(unittest.TestCase):
    def setUp(self):
        isolated=tempfile.TemporaryDirectory(prefix="qianxun-test-jev-")
        self.addCleanup(isolated.cleanup)
        environment=patch.dict(os.environ,{"JEV_INTEGRATION":"0","JEV_CONFIG_DIR":isolated.name,"AIPR_JEV_API_KEY":""})
        environment.start();self.addCleanup(environment.stop)

    def test_current_batch_exports_only_new_rows_without_reconciling_cumulative_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/"batch";out.mkdir()
            rows=[{"identity":identity,"douyin_id":identity,"nickname":identity,"talent_level":"3","profile_verified":True,"douyin_homepage":f"https://douyin.example/{identity}","content_evidence_reviewed":True,"content_evidence":["真人口播 精致场景"],"monthly_sales_value":200000,"buyin_contact_wechat":contact} for identity,contact in [("old","wx_old"),("fresh","wx_fresh")]]
            payload={"status":"incomplete","candidates":rows,"strict_selected_count":2,"contact_dedup_mode":"strict-any-plaintext-value","audit":{"identity_unique":True,"contact_values_unique":True,"cross_round_contact_overlap":0}}
            source=root/"strict.json";source.write_text(json.dumps(payload));original=source.read_bytes()
            baseline=root/"baseline.json";baseline.write_text(json.dumps({"candidates":[rows[0]]}))
            strategy=root/"rules.json";strategy.write_text(json.dumps({"targetCount":1000,"threshold":78,"exclusions":[]}))
            flow=out/"aipr_realtime_creator_flow.json";RealtimeCreatorFlowStore(flow).record("old","listed",rows[0]);flow_before=flow.read_bytes()
            proc=subprocess.run([sys.executable,str(Path(__file__).with_name("finalize_creator_delivery.py")),"--input",str(source),"--strategy",str(strategy),"--out-dir",str(out),"--task-id","t","--require-strict-highwater","--deliver-current","--batch-baseline",str(baseline)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            event=json.loads(proc.stdout.splitlines()[-1]);delivery=json.loads(Path(event["output"]).read_text())
            self.assertEqual(len(delivery["rows"]),1);self.assertEqual(delivery["rows"][0]["达人昵称"],"fresh")
            self.assertEqual(delivery["batch_scope"]["baseline_count"],1)
            self.assertEqual(delivery["robot_queue_count"],1)
            self.assertEqual(source.read_bytes(),original);self.assertEqual(flow.read_bytes(),flow_before)

    def test_finalizer_writes_complete_robot_handoff_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aipr-finalize-") as temp:
            root = Path(temp)
            source = root / "candidates.json"
            strategy = root / "strategy.json"
            output = root / "delivery"
            output.mkdir()
            flow_path = output / "aipr_realtime_creator_flow.json"
            RealtimeCreatorFlowStore(flow_path).record(
                "creator-1", "not_authorized", {"identity": "creator-1"}, "old result")
            RealtimeCreatorFlowStore(flow_path).record(
                "unfinished", "contact_revealing", {"identity": "unfinished", "shop": "A"})
            source.write_text(json.dumps({"candidates": [{
                "identity": "creator-1",
                "nickname": "高匹配达人",
                "talent_level": "3",
                "buyin_profile_url": "https://buyin.example/1",
                "douyin_homepage": "https://douyin.example/1",
                "profile_verified": True,
                "content_evidence_reviewed": True,
                "content_evidence": ["真人口播 精致场景"],
                "monthly_sales_value": 200000,
                "buyin_contact_wechat": "wx_test",
                "buyin_contact_phone": "13800000000",
            }]}, ensure_ascii=False), encoding="utf-8")
            strategy.write_text(json.dumps({"threshold": 78, "exclusions": []}, ensure_ascii=False), encoding="utf-8")

            process = subprocess.run([
                sys.executable,
                str(Path(__file__).with_name("finalize_creator_delivery.py")),
                "--input", str(source),
                "--strategy", str(strategy),
                "--out-dir", str(output),
                "--task-id", "lip-500",
                "--task-name", "唇部精华测试",
            ], text=True, encoding="utf-8", capture_output=True)

            self.assertEqual(process.returncode, 0, process.stderr)
            event = json.loads(process.stdout.strip().splitlines()[-1])
            self.assertEqual(event["status"], "delivery_ready")
            self.assertEqual(RealtimeCreatorFlowStore(flow_path).get("creator-1")["state"], "listed")
            finished_flow = RealtimeCreatorFlowStore(flow_path)
            self.assertEqual(finished_flow.get("unfinished")["state"], "suitable")
            self.assertEqual(finished_flow.summary()["contact_revealing_count"], 0)
            self.assertEqual(finished_flow.summary()["listed_count"], 1)
            self.assertTrue(Path(event["robot_batch_json"]).exists())
            self.assertTrue(Path(event["handoff_manifest"]).exists())
            delivery = json.loads(Path(event["output"]).read_text(encoding="utf-8"))
            self.assertEqual(delivery["robot_contract_version"], "aipr.robot.outreach.v1")
            self.assertEqual(Path(delivery["artifacts"]["finalJson"]), Path(event["output"]))
            manifest = json.loads(Path(event["handoff_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schemaVersion"], "aipr.delivery.handoff.v1")
            self.assertEqual(manifest["summary"]["robotRecordCount"], 1)
            batch = json.loads(Path(event["robot_batch_json"]).read_text(encoding="utf-8"))
            self.assertEqual(batch["schemaVersion"], "aipr.robot.batch.v1")
            self.assertEqual(batch["records"][0]["creator"]["contact"]["wechat"], "wx_test")

    def test_user_closed_partial_list_preserves_planned_target_and_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aipr-finalize-contacts-") as temp:
            root = Path(temp)
            source = root / "strict.json"
            strategy = root / "strategy.json"
            output = root / "delivery"
            output.mkdir()
            flow_path = output / "aipr_realtime_creator_flow.json"
            RealtimeCreatorFlowStore(flow_path).record(
                "creator-1", "evidence_reviewing", {"identity": "creator-1"})
            row = {
                "identity": "creator-1",
                "nickname": "高匹配达人",
                "talent_level": "3",
                "buyin_profile_url": "https://buyin.example/1",
                "douyin_homepage": "https://douyin.example/1",
                "profile_verified": True,
                "content_evidence_reviewed": True,
                "content_evidence": ["真人口播 精致场景"],
                "monthly_sales_value": 200000,
                "buyin_contact_wechat": "wx_unique",
            }
            source.write_text(json.dumps({
                "status": "incomplete",
                "contact_dedup_mode": "strict-any-plaintext-value",
                "strict_selected_count": 1,
                "audit": {
                    "identity_unique": True,
                    "contact_values_unique": True,
                    "cross_round_contact_overlap": 0,
                },
                "candidates": [row],
            }, ensure_ascii=False), encoding="utf-8")
            strategy.write_text(json.dumps({
                "targetCount": 1000,
                "threshold": 78,
                "exclusions": [],
            }, ensure_ascii=False), encoding="utf-8")

            process = subprocess.run([
                sys.executable,
                str(Path(__file__).with_name("finalize_creator_delivery.py")),
                "--input", str(source),
                "--strategy", str(strategy),
                "--out-dir", str(output),
                "--task-id", "lip-contacts",
                "--task-name", "唇部精华联系人测试",
                "--contacts-only",
                "--deliver-current",
                "--require-strict-highwater",
            ], text=True, encoding="utf-8", capture_output=True)

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(source.read_text())["status"], "incomplete")
            delivered = json.loads(Path(json.loads(process.stdout.strip().splitlines()[-1])["output"]).read_text())
            self.assertEqual(delivered["planned_target_count"], 1000)
            self.assertTrue(delivered["closed_at_current_count"])
            event = json.loads(process.stdout.strip().splitlines()[-1])
            self.assertEqual(event["robot_queue"], "")
            self.assertEqual(RealtimeCreatorFlowStore(flow_path).summary()["listed_count"], 1)
            self.assertEqual(event["robot_batch_json"], "")
            self.assertEqual(event["robot_queue_count"], 0)
            delivery = json.loads(Path(event["output"]).read_text(encoding="utf-8"))
            self.assertEqual(delivery["delivery_mode"], "contacts-only")
            self.assertEqual(delivery["robot_queue"], [])
            self.assertEqual(delivery["strict_selected_count"], 1)
            self.assertTrue(delivery["strict_audit"]["contact_values_unique"])
            self.assertFalse(list(output.glob("*机器人队列*")))
            self.assertFalse(list(output.glob("*机器人批量包*")))


    def test_contacts_only_requires_and_preserves_strict_highwater_audit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aipr-finalize-contacts-") as temp:
            root = Path(temp)
            source = root / "strict.json"
            strategy = root / "strategy.json"
            output = root / "delivery"
            output.mkdir()
            flow_path = output / "aipr_realtime_creator_flow.json"
            RealtimeCreatorFlowStore(flow_path).record(
                "creator-1", "evidence_reviewing", {"identity": "creator-1"})
            row = {
                "identity": "creator-1",
                "nickname": "高匹配达人",
                "talent_level": "3",
                "buyin_profile_url": "https://buyin.example/1",
                "douyin_homepage": "https://douyin.example/1",
                "profile_verified": True,
                "content_evidence_reviewed": True,
                "content_evidence": ["真人口播 精致场景"],
                "monthly_sales_value": 200000,
                "buyin_contact_wechat": "wx_unique",
            }
            source.write_text(json.dumps({
                "status": "complete",
                "contact_dedup_mode": "strict-any-plaintext-value",
                "strict_selected_count": 1,
                "audit": {
                    "identity_unique": True,
                    "contact_values_unique": True,
                    "cross_round_contact_overlap": 0,
                },
                "candidates": [row],
            }, ensure_ascii=False), encoding="utf-8")
            strategy.write_text(json.dumps({
                "targetCount": 1,
                "threshold": 78,
                "exclusions": [],
            }, ensure_ascii=False), encoding="utf-8")

            process = subprocess.run([
                sys.executable,
                str(Path(__file__).with_name("finalize_creator_delivery.py")),
                "--input", str(source),
                "--strategy", str(strategy),
                "--out-dir", str(output),
                "--task-id", "lip-contacts",
                "--task-name", "唇部精华联系人测试",
                "--contacts-only",
                "--require-strict-highwater",
            ], text=True, encoding="utf-8", capture_output=True)

            self.assertEqual(process.returncode, 0, process.stderr)
            event = json.loads(process.stdout.strip().splitlines()[-1])
            self.assertEqual(event["robot_queue"], "")
            self.assertEqual(RealtimeCreatorFlowStore(flow_path).summary()["listed_count"], 1)
            self.assertEqual(event["robot_batch_json"], "")
            self.assertEqual(event["robot_queue_count"], 0)
            delivery = json.loads(Path(event["output"]).read_text(encoding="utf-8"))
            self.assertEqual(delivery["delivery_mode"], "contacts-only")
            self.assertEqual(delivery["robot_queue"], [])
            self.assertEqual(delivery["strict_selected_count"], 1)
            self.assertTrue(delivery["strict_audit"]["contact_values_unique"])
            self.assertFalse(list(output.glob("*机器人队列*")))
            self.assertFalse(list(output.glob("*机器人批量包*")))


if __name__ == "__main__":
    unittest.main()
