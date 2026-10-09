from __future__ import annotations

import json
import os
import tempfile
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_contact_pipeline as pipeline


class IdleTimeoutTest(unittest.TestCase):
    def test_silent_worker_is_bounded_and_previous_events_retained(self):
        started = time.monotonic()
        code, events = pipeline.run_stream([
            sys.executable, "-c",
            "import time; print('{\"status\":\"checkpoint\"}', flush=True); time.sleep(30)",
        ], idle_timeout_seconds=3)
        self.assertEqual(code, 124)
        self.assertEqual(events[0]["status"], "checkpoint")
        self.assertEqual(events[-1]["status"], "worker_idle_timeout")
        self.assertLess(time.monotonic() - started, 15)

    def test_missing_recovery_does_not_loop_forever(self):
        code, events = pipeline.run_stream([
            sys.executable, "-c", "import time; time.sleep(30)",
        ], idle_timeout_seconds=3, recover_on_idle=lambda: None)
        self.assertEqual(code, 124)
        self.assertEqual(events[-1]["status"], "worker_idle_timeout")

    def test_active_worker_has_no_total_runtime_timeout(self):
        code, events = pipeline.run_stream([
            sys.executable, "-c",
            "import time; "
            "[(print('{\"status\":\"progress\"}', flush=True), time.sleep(.8)) for _ in range(5)]",
        ], idle_timeout_seconds=3)
        self.assertEqual(code, 0)
        self.assertEqual(len(events), 5)

    @unittest.skipUnless(os.name == "posix", "Mac process group behavior")
    def test_timeout_stops_descendant_holding_pipes_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "saved.json"
            child_code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
            script = (
                "import subprocess,sys,time,pathlib,json; "
                f"pathlib.Path({str(checkpoint)!r}).write_text('saved-checkpoint'); "
                f"child=subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "print(json.dumps(dict(status='spawned', pid=child.pid)), flush=True); time.sleep(30)"
            )
            started = time.monotonic()
            code, events = pipeline.run_stream([sys.executable, "-c", script], idle_timeout_seconds=3)
            self.assertEqual(code, 124)
            self.assertEqual(events[-1]["status"], "worker_idle_timeout")
            self.assertEqual(checkpoint.read_text(), "saved-checkpoint")
            self.assertLess(time.monotonic() - started, 15)

    def test_idle_failure_retries_but_is_bounded(self):
        timeout = (124, [{"status": "worker_idle_timeout"}])
        with mock.patch.object(pipeline, "run_stream", return_value=timeout) as run, mock.patch.object(pipeline, "emit") as emit:
            waits = []
            code, events = pipeline.run_collection_with_retry(["fake-worker"], sleeper=waits.append)
        self.assertEqual(code, 124)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len(waits), 2)
        self.assertGreaterEqual(waits[0], 30)
        self.assertEqual(len(events), 3)
        self.assertIn("collection_retry_exhausted", [x.args[0]["status"] for x in emit.call_args_list])


if __name__ == "__main__":
    unittest.main()
