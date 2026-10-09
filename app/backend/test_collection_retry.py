"""采集重试包装测试

验证 run_collection_with_retry 的行为：
- 成功（code 0）时不重试
- 限流（code 9）时按指数退避重试
- 达到 max_retries 后放弃
- 非限流错误码不重试
- 事件正确合并
"""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect_and_contact_pipeline as pipeline  # noqa: E402


class FakeSleeper:
    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def fake_stream(results: list[tuple[int, list[dict]]]):
    """按顺序返回预设结果。"""
    calls = {"n": 0}

    def _run(command, **kwargs):
        idx = min(calls["n"], len(results) - 1)
        calls["n"] += 1
        return results[idx]

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


class RetryTest(unittest.TestCase):
    def test_jev_account_block_cannot_be_recovered_as_short_pool_or_page_batch(self):
        for original_code in (0, 7):
            sleeper = FakeSleeper()
            events = [{'status': 'jev_action_required', 'http_status': 402},
                      {'status': 'collection_checkpoint_saved', 'candidate_count': 3000},
                      {'status': 'collection_batch_paused'}]
            stream = fake_stream([(original_code, events)])
            with mock.patch.object(pipeline, 'run_stream', stream), mock.patch.object(pipeline, 'emit'):
                code, saved = pipeline.run_collection_with_retry(['x'], sleeper=sleeper)
            self.assertEqual(code, 11)
            self.assertEqual(saved, events)
            self.assertEqual(sleeper.waits, [])
            self.assertEqual(stream.calls['n'], 1)

    def test_exhausted_platform_cooldown_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            command = ["x", "--out-dir", directory]
            stream = fake_stream([(9, [{"status": "platform_paused"}])])
            with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit"), mock.patch.object(pipeline.time, "time", return_value=1000):
                code, _ = pipeline.run_collection_with_retry(command, sleeper=FakeSleeper())
            self.assertEqual(code, 9)
            payload = json.loads((Path(directory) / "collection-platform-cooldown.json").read_text())
            self.assertEqual(payload["retry_after"], 1960)
            sleeper = FakeSleeper()
            stream = fake_stream([(0, [{"status": "collection_finished"}])])
            with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit"), mock.patch.object(pipeline.time, "time", return_value=1100):
                pipeline.run_collection_with_retry(command, sleeper=sleeper)
            self.assertEqual(sleeper.waits, [860])

    def test_old_cooldown_does_not_block_final_incomplete_pool(self):
        events = [{"status": "pipeline_platform_paused"},
                  {"status": "collection_checkpoint_saved", "candidate_count": 423},
                  {"status": "collection_incomplete"}]
        self.assertTrue(pipeline.collection_ended_without_platform_pause(events))
        self.assertFalse(pipeline.collection_ended_without_platform_pause(
            events + [{"status": "platform_paused"}]))

    def test_successful_batch_resets_consecutive_failure_budget(self):
        sleeper = FakeSleeper()
        limited = (9, [{"status": "pipeline_platform_paused"}])
        batch = (0, [{"status": "collection_batch_paused"}])
        stream = fake_stream([limited, limited, batch, limited, limited,
                              (0, [{"status": "collection_finished"}])])
        with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit"):
            code, _ = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 6)
        self.assertGreaterEqual(sleeper.waits[3], 240)
        self.assertLess(sleeper.waits[3], 246)

    def test_connection_closed_resumes_saved_checkpoint(self):
        sleeper = FakeSleeper()
        stream = fake_stream([
            (7, [{"status": "shop_error", "message": "Page.goto: net::ERR_CONNECTION_CLOSED"},
                 {"status": "collection_checkpoint_saved", "candidate_count": 85}]),
            (0, [{"status": "collection_finished", "candidate_count": 600}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit"):
            code, events = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 2)
        self.assertGreaterEqual(sleeper.waits[0], 30)
        self.assertEqual(events[-1]["candidate_count"], 600)

    def test_page_batch_checkpoint_is_not_task_completion(self):
        sleeper = FakeSleeper()
        stream = fake_stream([
            (0, [{"status": "collection_batch_paused", "candidate_count": 120}]),
            (0, [{"status": "collection_finished", "candidate_count": 600}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit"):
            code, events = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 2)
        self.assertEqual(events[-1]["candidate_count"], 600)

    def test_contact_quota_checkpoint_waits_instead_of_page_batch_spin(self):
        sleeper = FakeSleeper()
        stream = fake_stream([
            (0, [{"status": "pipeline_waiting_for_contact_quota", "retry_after": 1600},
                 {"status": "collection_batch_paused"}]),
            (0, [{"status": "collection_finished"}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), mock.patch.object(pipeline, "emit") as emit, mock.patch.object(pipeline.time, "time", return_value=1000):
            code, _ = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 2)
        self.assertEqual(sleeper.waits, [600])
        self.assertNotIn("collection_batch_resuming", [call.args[0]["status"] for call in emit.call_args_list])

    def test_success_no_retry(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([(0, [{"status": "collection_finished"}])])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit"):
            code, events = pipeline.run_collection_with_retry(
                ["x"], sleeper=sleeper,
            )
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 1)  # type: ignore[attr-defined]
        self.assertEqual(sleeper.waits, [])

    def test_rate_limit_retries_then_succeeds(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([
            (9, [{"status": "pipeline_platform_paused", "source_status": "rate_limited"}]),
            (0, [{"status": "collection_finished"}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit"):
            code, events = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 0)
        self.assertEqual(stream.calls["n"], 2)  # type: ignore[attr-defined]
        self.assertEqual(len(sleeper.waits), 1)
        # 首次退避 ≈ 240s（含 jitter）
        self.assertGreaterEqual(sleeper.waits[0], 240)
        self.assertLess(sleeper.waits[0], 250)

    def test_backoff_grows_exponentially(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([(9, [{"status": "pipeline_platform_paused"}])] * 3)
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit"):
            code, _ = pipeline.run_collection_with_retry(
                ["x"], max_retries=3, sleeper=sleeper,
            )
        self.assertEqual(code, 9)
        self.assertEqual(len(sleeper.waits), 2)  # 最后一次不再等
        # 240s → 480s
        self.assertGreaterEqual(sleeper.waits[0], 240)
        self.assertGreaterEqual(sleeper.waits[1], 480)

    def test_exhausted_returns_code_9(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([(9, [{"status": "pipeline_platform_paused"}])])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit") as emit:
            code, events = pipeline.run_collection_with_retry(
                ["x"], max_retries=2, sleeper=sleeper,
            )
        self.assertEqual(code, 9)
        self.assertEqual(stream.calls["n"], 2)  # type: ignore[attr-defined]
        # 应有 retry_exhausted 事件
        statuses = [c.args[0].get("status") for c in emit.call_args_list]
        self.assertIn("collection_retry_exhausted", statuses)

    def test_non_rate_limit_error_not_retried(self) -> None:
        """非 9 的退出码不触发重试。"""
        sleeper = FakeSleeper()
        stream = fake_stream([(2, [{"status": "pipeline_error"}])])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit"):
            code, _ = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        self.assertEqual(code, 2)
        self.assertEqual(stream.calls["n"], 1)  # type: ignore[attr-defined]
        self.assertEqual(sleeper.waits, [])

    def test_events_accumulated_across_attempts(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([
            (9, [{"status": "pipeline_platform_paused"}, {"status": "a"}]),
            (0, [{"status": "collection_finished"}, {"status": "b"}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit"):
            _, events = pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        statuses = [e.get("status") for e in events]
        self.assertEqual(statuses, ["pipeline_platform_paused", "a", "collection_finished", "b"])

    def test_retry_scheduled_event_emitted(self) -> None:
        sleeper = FakeSleeper()
        stream = fake_stream([
            (9, [{"status": "pipeline_platform_paused", "source_status": "rate_limited"}]),
            (0, [{"status": "collection_finished"}]),
        ])
        with mock.patch.object(pipeline, "run_stream", stream), \
             mock.patch.object(pipeline, "emit") as emit:
            pipeline.run_collection_with_retry(["x"], sleeper=sleeper)
        payloads = [c.args[0] for c in emit.call_args_list]
        scheduled = next((p for p in payloads if p.get("status") == "collection_retry_scheduled"), None)
        self.assertIsNotNone(scheduled)
        self.assertEqual(scheduled["attempt"], 1)
        self.assertEqual(scheduled["next_attempt"], 2)
        self.assertGreaterEqual(scheduled["backoff_ms"], 240_000)


if __name__ == "__main__":
    unittest.main()
