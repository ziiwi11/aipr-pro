import unittest
from unittest.mock import Mock, patch
import collect_buyin_creators_cdp as c
import collect_and_contact_pipeline as pipeline

class BrowseRequestRecoveryTests(unittest.TestCase):
    def test_captured_request_does_not_reload(self):
        page = Mock()
        with patch.object(c, "assert_safe"), patch.object(c, "assert_safe_payloads"), patch.object(c, "restore_structured_browse_page") as restore:
            body = c.resolve_structured_browse_request(page, {}, [{"page":1,"query":"old","filters":{"level":[1]}}], [])
            self.assertEqual(body["query"], "")
            self.assertEqual(body["filters"], {"level":[1]})
            restore.assert_not_called()

    def test_missing_request_recovers_from_same_shop(self):
        page = Mock(); strategy = {"category":"美妆个护"}; bodies = []
        def restore(p, s):
            self.assertIs(p,page);self.assertIs(s,strategy)
            bodies.append({"page":1,"query":"","filters":{"level":[1,2]}})
        with patch.object(c,"assert_safe"),patch.object(c,"assert_safe_payloads"),patch.object(c,"emit"),patch.object(c,"restore_structured_browse_page",side_effect=restore):
            self.assertEqual(c.resolve_structured_browse_request(page,strategy,bodies,[])["filters"],{"level":[1,2]})

    def test_failed_recovery_is_bounded_and_login_gate_is_not_retried(self):
        page=Mock()
        with patch.object(c,"assert_safe"),patch.object(c,"assert_safe_payloads"),patch.object(c,"emit"),patch.object(c,"restore_structured_browse_page"):
            with self.assertRaisesRegex(RuntimeError,"request_not_found"):
                c.resolve_structured_browse_request(page,{},[],[])
            self.assertEqual(page.wait_for_timeout.call_count,10)
        with patch.object(c,"assert_safe",side_effect=RuntimeError("login_required")),patch.object(c,"restore_structured_browse_page") as restore:
            with self.assertRaisesRegex(RuntimeError,"login_required"):
                c.resolve_structured_browse_request(page,{},[],[])
            restore.assert_not_called()

    def test_pipeline_retries_missing_template_without_discarding_checkpoint(self):
        failure=(7,[{"status":"shop_error","message":"buyin_structured_browse_request_not_found"}])
        success=(0,[{"status":"collection_finished","candidate_count":500}])
        sleep=Mock()
        with patch.object(pipeline,"run_stream",side_effect=[failure,success]) as run,patch.object(pipeline,"emit"):
            code,events=pipeline.run_collection_with_retry(["worker"],sleeper=sleep)
        self.assertEqual(code,0);self.assertEqual(run.call_count,2)
        self.assertEqual(events[-1]["status"],"collection_finished")
        self.assertGreaterEqual(sleep.call_args.args[0],30)

if __name__ == "__main__":unittest.main()
