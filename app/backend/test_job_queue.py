"""任务队列测试

覆盖：
- 注册与入队（未注册类型报错）
- 正常执行与统计
- 失败重试与指数退避
- 风控错误使用更长的退避基数
- 达到 maxRetries 后标记失败
- 并发控制
- 暂停/恢复
- 事件序列
- 延迟任务
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_queue import (  # noqa: E402
    RATE_LIMIT_BACKOFF_MS,
    backoff_schedule,
    create_queue,
    is_rate_limit_error,
    summarize_events,
)


class FakeSleeper:
    """记录睡眠请求但不真正等待。"""

    def __init__(self) -> None:
        self.total = 0.0
        self.calls = 0

    def __call__(self, seconds: float) -> None:
        self.calls += 1
        self.total += seconds


class RegisterTest(unittest.TestCase):
    def test_push_unknown_type_raises(self) -> None:
        q = create_queue()
        with self.assertRaises(KeyError):
            q.push("nope", {})

    def test_register_non_callable_raises(self) -> None:
        q = create_queue()
        with self.assertRaises(TypeError):
            q.register("x", None)  # type: ignore[arg-type]


class SuccessTest(unittest.TestCase):
    def test_single_job_completes(self) -> None:
        q = create_queue()
        seen = []
        q.register("t", lambda job: seen.append(job.payload))
        q.push("t", {"a": 1})
        stats = q.run_until_drained()
        self.assertEqual(seen, [{"a": 1}])
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["failed"], 0)

    def test_multiple_jobs_all_run(self) -> None:
        q = create_queue()
        seen = []
        q.register("t", lambda job: seen.append(job.payload["n"]))
        for i in range(5):
            q.push("t", {"n": i})
        q.run_until_drained()
        self.assertEqual(sorted(seen), [0, 1, 2, 3, 4])

    def test_handler_result_recorded(self) -> None:
        q = create_queue()
        q.register("t", lambda job: {"ok": True})
        q.push("t", {})
        q.run_until_drained()
        self.assertEqual(q.get_stats()["completed"], 1)


class RetryTest(unittest.TestCase):
    def test_retries_then_succeeds(self) -> None:
        sleeper = FakeSleeper()
        q = create_queue(base_backoff_ms=10, sleeper=sleeper)
        attempts = {"n": 0}

        def flaky(job):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("boom")
            return "ok"

        q.register("t", flaky)
        q.push("t", {}, max_retries=5)
        stats = q.run_until_drained()
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["retried"], 2)

    def test_marks_failed_after_max_retries(self) -> None:
        sleeper = FakeSleeper()
        q = create_queue(base_backoff_ms=10, sleeper=sleeper)
        calls = {"n": 0}

        def always_fail(job):
            calls["n"] += 1
            raise RuntimeError("nope")

        q.register("t", always_fail)
        q.push("t", {}, max_retries=3)
        stats = q.run_until_drained()
        self.assertEqual(calls["n"], 3)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["completed"], 0)

    def test_zero_retries_fails_immediately(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        calls = {"n": 0}

        def fail(job):
            calls["n"] += 1
            raise RuntimeError("x")

        q.register("t", fail)
        q.push("t", {}, max_retries=0)
        stats = q.run_until_drained()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(stats["failed"], 1)

    def test_exponential_backoff_growth(self) -> None:
        """退避应随尝试次数指数增长（忽略 jitter）。"""
        self.assertEqual(backoff_schedule(4, base_ms=1000), [1000, 2000, 4000, 8000])


class RateLimitBackoffTest(unittest.TestCase):
    def test_detects_rate_limit_markers(self) -> None:
        for msg in ("请求过于频繁", "稍后再试", "访问频繁", "安全验证", "次数已达上限"):
            self.assertTrue(is_rate_limit_error(RuntimeError(msg)), msg)

    def test_ignores_unrelated_errors(self) -> None:
        self.assertFalse(is_rate_limit_error(RuntimeError("connection refused")))
        self.assertFalse(is_rate_limit_error(ValueError("bad payload")))

    def test_rate_limit_uses_longer_base(self) -> None:
        self.assertEqual(
            backoff_schedule(3, base_ms=1000, rate_limit=True),
            [RATE_LIMIT_BACKOFF_MS, RATE_LIMIT_BACKOFF_MS * 2, RATE_LIMIT_BACKOFF_MS * 4],
        )

    def test_rate_limit_job_waits_longer_than_normal(self) -> None:
        """风控错误触发的退避应显著长于普通错误。

        用较小的 rate_limit_backoff_ms 保持测试快速，
        同时验证「风控基数 > 普通基数」这一关系。
        """
        normal = FakeSleeper()
        q1 = create_queue(base_backoff_ms=10, rate_limit_backoff_ms=1000, sleeper=normal)
        q1.register("t", lambda job: (_ for _ in ()).throw(RuntimeError("boom")))
        q1.push("t", {}, max_retries=3)
        q1.run_until_drained()

        limited = FakeSleeper()
        q2 = create_queue(base_backoff_ms=10, rate_limit_backoff_ms=1000, sleeper=limited)
        q2.register("t", lambda job: (_ for _ in ()).throw(RuntimeError("请求过于频繁")))
        q2.push("t", {}, max_retries=3)
        q2.run_until_drained()

        self.assertGreater(limited.total, normal.total)


class ConcurrencyTest(unittest.TestCase):
    def test_concurrency_limit_respected(self) -> None:
        """并发上限为 1 时，任务应串行执行。"""
        q = create_queue(concurrency=1, sleeper=FakeSleeper())
        order = []

        def handler(job):
            order.append(("start", job.payload["n"]))
            order.append(("end", job.payload["n"]))

        q.register("t", handler)
        for i in range(3):
            q.push("t", {"n": i})
        q.run_until_drained()
        # 串行：每个 start 后紧跟同号 end
        self.assertEqual(
            order,
            [("start", 0), ("end", 0), ("start", 1), ("end", 1), ("start", 2), ("end", 2)],
        )

    def test_stats_report_concurrency(self) -> None:
        q = create_queue(concurrency=4)
        self.assertEqual(q.get_stats()["concurrency"], 4)


class PauseTest(unittest.TestCase):
    def test_paused_queue_does_not_run(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        seen = []
        q.register("t", lambda job: seen.append(1))
        q.push("t", {})
        q.pause()
        q.tick()
        self.assertEqual(seen, [])
        self.assertTrue(q.has_work())

    def test_resume_then_run(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        seen = []
        q.register("t", lambda job: seen.append(1))
        q.push("t", {})
        q.pause()
        q.tick()
        q.resume()
        q.run_until_drained()
        self.assertEqual(seen, [1])


class DelayTest(unittest.TestCase):
    def test_delay_ms_defers_execution(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        seen = []
        q.register("t", lambda job: seen.append(1))
        q.push("t", {}, delay_ms=60_000)
        q.tick()
        self.assertEqual(seen, [], "延迟任务不应立即执行")
        self.assertTrue(q.has_work())


class EventTest(unittest.TestCase):
    def test_event_sequence_on_success(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        q.register("t", lambda job: None)
        q.push("t", {})
        q.run_until_drained()
        names = [n for n, _ in q.events()]
        self.assertEqual(names, ["enqueued", "running", "completed"])

    def test_event_sequence_on_retry_then_fail(self) -> None:
        q = create_queue(base_backoff_ms=1, sleeper=FakeSleeper())
        q.register("t", lambda job: (_ for _ in ()).throw(RuntimeError("x")))
        q.push("t", {}, max_retries=2)
        q.run_until_drained()
        names = [n for n, _ in q.events()]
        self.assertEqual(names, ["enqueued", "running", "retrying", "running", "failed"])

    def test_summarize_events(self) -> None:
        q = create_queue(sleeper=FakeSleeper())
        q.register("t", lambda job: None)
        q.push("t", {})
        q.push("t", {})
        q.run_until_drained()
        counts = summarize_events(q.events())
        self.assertEqual(counts["completed"], 2)
        self.assertEqual(counts["enqueued"], 2)


class StatsTest(unittest.TestCase):
    def test_stats_shape(self) -> None:
        q = create_queue(concurrency=2)
        q.register("a", lambda job: None)
        stats = q.get_stats()
        for key in ("total", "completed", "failed", "retried", "pending", "running",
                    "registered_types", "concurrency", "paused"):
            self.assertIn(key, stats)
        self.assertEqual(stats["registered_types"], ["a"])


if __name__ == "__main__":
    unittest.main()
