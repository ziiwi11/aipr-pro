"""进程内任务队列：重试、指数退避、并发控制

移植自 InfluenceX 的 server/job-queue.js（MIT），适配 AIPR Pro 的场景：

风控场景（实测数据）：
- 连续揭示约 44 次后触发软限流（请求过于频繁 / 稍后再试）
- 约 4 分钟后自动恢复

队列策略：
- 限流类错误 → 指数退避重试（默认基数 4 分钟，匹配实测恢复窗口）
- 其他错误 → 常规退避（默认基数 1 秒）
- 达到 maxRetries 后标记失败，不阻塞后续任务

用法：
    q = create_queue(concurrency=1, base_backoff_ms=1000)
    q.register("reveal-contact", handler)
    q.push("reveal-contact", {"uid": "..."}, max_retries=3)
    q.run_until_drained()
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# 风控信号（与 collect_buyin_creators_cdp.SAFETY_MARKERS 保持一致）
RATE_LIMIT_MARKERS = (
    "请求过于频繁",
    "稍后再试",
    "访问频繁",
    "安全验证",
    "当前环境存在风险",
    "次数已达上限",
)

# 实测：限流后约 4 分钟恢复
RATE_LIMIT_BACKOFF_MS = 240_000


def is_rate_limit_error(error: Any) -> bool:
    """判断异常是否属于平台限流。"""
    text = str(error)
    return any(marker in text for marker in RATE_LIMIT_MARKERS)


@dataclass
class Job:
    id: int
    type: str
    payload: dict[str, Any]
    attempts: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    run_at: float = field(default_factory=time.time)
    state: str = "pending"
    last_error: str | None = None
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "state": self.state,
            "last_error": self.last_error,
            "run_at": self.run_at,
        }


class JobQueue:
    """线程安全的进程内队列。"""

    def __init__(
        self,
        concurrency: int = 1,
        default_max_retries: int = 3,
        base_backoff_ms: int = 1000,
        rate_limit_backoff_ms: int = RATE_LIMIT_BACKOFF_MS,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.concurrency = max(1, int(concurrency))
        self.default_max_retries = max(0, int(default_max_retries))
        self.base_backoff_ms = max(0, int(base_backoff_ms))
        self.rate_limit_backoff_ms = max(0, int(rate_limit_backoff_ms))
        self._sleep = sleeper or time.sleep

        self._handlers: dict[str, Callable[[Job], Any]] = {}
        self._pending: list[Job] = []
        self._running: set[int] = set()
        self._lock = threading.RLock()
        self._next_id = 1
        self._paused = False

        self._stats = {"total": 0, "completed": 0, "failed": 0, "retried": 0}
        self._events: list[tuple[str, dict[str, Any]]] = []

    # ---------- 注册与入队 ----------

    def register(self, job_type: str, handler: Callable[[Job], Any]) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[job_type] = handler

    def push(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        max_retries: int | None = None,
        delay_ms: int = 0,
    ) -> int:
        if job_type not in self._handlers:
            raise KeyError(f"No handler registered for job type: {job_type}")
        now = time.time()
        job = Job(
            id=self._next_id,
            type=job_type,
            payload=dict(payload or {}),
            max_retries=self.default_max_retries if max_retries is None else max(0, int(max_retries)),
            created_at=now,
            run_at=now + max(0, delay_ms) / 1000,
        )
        self._next_id += 1
        with self._lock:
            self._pending.append(job)
            self._stats["total"] += 1
        self._emit("enqueued", job)
        return job.id

    # ---------- 调度 ----------

    def _pick_next_ready(self) -> Job | None:
        now = time.time()
        with self._lock:
            for i, job in enumerate(self._pending):
                if job.run_at <= now:
                    return self._pending.pop(i)
        return None

    def _next_delay(self) -> float | None:
        with self._lock:
            if not self._pending:
                return None
            return max(0.0, min(j.run_at for j in self._pending) - time.time())

    def _run_one(self, job: Job) -> None:
        with self._lock:
            self._running.add(job.id)
            job.state = "running"
            job.attempts += 1
        self._emit("running", job)

        handler = self._handlers[job.type]
        try:
            result = handler(job)
            job.result = result
            job.state = "completed"
            with self._lock:
                self._stats["completed"] += 1
            self._emit("completed", job)
        except Exception as exc:  # noqa: BLE001 — 队列必须吞掉异常以继续调度
            job.last_error = str(exc)[:300]
            if job.attempts >= job.max_retries:
                job.state = "failed"
                with self._lock:
                    self._stats["failed"] += 1
                self._emit("failed", job)
            else:
                base = self.rate_limit_backoff_ms if is_rate_limit_error(exc) else self.base_backoff_ms
                backoff_ms = base * (2 ** (job.attempts - 1))
                jitter_ms = random.randint(0, 250)
                job.run_at = time.time() + (backoff_ms + jitter_ms) / 1000
                job.state = "retrying"
                with self._lock:
                    self._stats["retried"] += 1
                    self._pending.append(job)
                self._emit("retrying", job)
        finally:
            with self._lock:
                self._running.discard(job.id)

    def tick(self) -> bool:
        """执行一轮调度，返回是否还有待处理任务。"""
        if self._paused:
            return self.has_work()
        while True:
            with self._lock:
                slots = self.concurrency - len(self._running)
            if slots <= 0:
                break
            job = self._pick_next_ready()
            if job is None:
                break
            self._run_one(job)
        return self.has_work()

    def run_until_drained(self, poll_interval: float = 0.05, max_wait: float = 1.0) -> dict[str, int]:
        """阻塞直到队列排空。

        max_wait 限制单次 sleep 的上限（默认 1 秒），避免长退避时阻塞过久；
        测试可注入 no-op sleeper 让整个过程瞬时完成。
        """
        while True:
            self.tick()
            if not self.has_work():
                break
            delay = self._next_delay()
            if delay is None:
                if not self._running:
                    break
                self._sleep(poll_interval)
            elif delay > 0:
                self._sleep(min(delay, max_wait))
            else:
                self._sleep(poll_interval)
        return self.get_stats()

    # ---------- 控制 ----------

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def has_work(self) -> bool:
        with self._lock:
            return bool(self._pending) or bool(self._running)

    # ---------- 观测 ----------

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "pending": len(self._pending),
                "running": len(self._running),
                "registered_types": sorted(self._handlers),
                "concurrency": self.concurrency,
                "paused": self._paused,
            }

    def events(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self._events)

    def _emit(self, name: str, job: Job) -> None:
        self._events.append((name, job.to_dict()))


def create_queue(**kwargs: Any) -> JobQueue:
    return JobQueue(**kwargs)


def backoff_schedule(
    attempts: int,
    base_ms: int = 1000,
    rate_limit: bool = False,
    rate_limit_backoff_ms: int = RATE_LIMIT_BACKOFF_MS,
) -> list[int]:
    """预览退避序列（供文档与测试使用）。"""
    base = rate_limit_backoff_ms if rate_limit else base_ms
    return [base * (2**i) for i in range(max(0, attempts))]


def summarize_events(events: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, _ in events:
        counts[name] = counts.get(name, 0) + 1
    return counts


def dumps_stats(stats: dict[str, Any]) -> str:
    return json.dumps(stats, ensure_ascii=False, sort_keys=True)
