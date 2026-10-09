import unittest
from jev_connection_test import run_test


class JevConnectionTest(unittest.TestCase):
    def test_one_synthetic_call_and_safe_summary(self):
        calls = []
        def call(payload, app, **options):
            calls.append((payload, app, options))
            return {"model": "jev-1.13.0", "answers": {"connection_test": {"type": "noul", "noul": .99}}, "usage": {"input_tokens": 20, "output_tokens": 8}, "api_key": "SECRET"}
        result = run_test(call)
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2]["max_attempts"], 1)
        self.assertNotIn("SECRET", str(result))
        self.assertEqual(result["usage"]["input_tokens"], 20)

    def test_errors_and_malformed_answer_never_claim_success(self):
        def fail(*args, **kwargs):
            raise RuntimeError("SECRET")
        result = run_test(fail)
        self.assertFalse(result["ok"])
        self.assertNotIn("SECRET", str(result))
        self.assertFalse(run_test(lambda *a, **k: {"answers": {}})["ok"])
