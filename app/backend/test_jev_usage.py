import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import jev_local_client as client

class UsageTest(unittest.TestCase):
    def test_usage_ledger_excludes_sensitive_fields_and_does_not_invent_cost(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(client, "ROOT", Path(temp)):
            client.record_usage("aipr-pro", {"model":"jev", "usage":{"input_tokens":123,"output_tokens":9,"secret":"key"},"state":{"phone":"private"}})
            raw=(Path(temp)/"usage-ledger.ndjson").read_text()
            entry=json.loads(raw)
            self.assertEqual(entry["usage"], {"input_tokens":123,"output_tokens":9})
            self.assertIsNone(entry["billed_amount"])
            self.assertNotIn("private",raw)
            self.assertNotIn("secret",raw)
    def test_missing_usage_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(client, "ROOT", Path(temp)):
            client.record_usage("aipr-pro", {})
            self.assertFalse(json.loads((Path(temp)/"usage-ledger.ndjson").read_text())["usage_available"])

    def test_attempts_record_failures_and_task_without_response_data(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(client, "ROOT", Path(temp)), patch.dict(client.os.environ, {"AIPR_TASK_ID":"brand-task-2"}):
            client.record_usage("aipr-pro", {"state":"private","api_key":"secret"}, outcome="http_error",http_status=402,attempt=2,elapsed_ms=100,model="jev-latest")
            raw=(Path(temp)/"usage-ledger.ndjson").read_text();entry=json.loads(raw)
            self.assertEqual(entry["task_id"],"brand-task-2"); self.assertEqual(entry["http_status"],402)
            self.assertEqual(entry["attempt"],2);self.assertNotIn("private",raw);self.assertNotIn("secret",raw)
            self.assertEqual(json.loads((Path(temp)/"account-status.json").read_text())["outcome"],"http_error")
            client.record_usage("aipr-pro",{},model="jev-latest")
            self.assertEqual(json.loads((Path(temp)/"account-status.json").read_text())["outcome"],"success")

    def test_bookkeeping_failure_does_not_repeat_successful_paid_request(self):
        import io
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=io.StringIO('{"answers":{}}')
        opener=MagicMock();opener.open.return_value=response
        with tempfile.TemporaryDirectory() as temp, patch.object(client,"ROOT",Path(temp)), patch.object(client,"enabled",return_value=True), patch.object(client,"settings",return_value={"backend":"cloud","api_key":"test-only"}), patch.object(client.urllib.request,"build_opener",return_value=opener), patch.object(Path,"open",side_effect=OSError("cannot write")), patch.object(client.sys,"stderr",io.StringIO()) as stderr:
            result=client.decide({"state":{},"questions":{}},"aipr-pro")
            self.assertEqual(result["answers"],{})
            self.assertEqual(opener.open.call_count,1)
            self.assertIn("jev_usage_record_failed",stderr.getvalue())
