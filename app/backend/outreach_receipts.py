"""外联回执账本

为机器人队列增加发送状态与回复标记的记录能力，形成「请求 → 发送 → 回复」闭环。

设计约束（与 creator_delivery_contract 的 guardrails 一致）：
- 只记录状态，不主动发送
- 状态流转受白名单约束，拒绝非法跳转
- 追加式存储（JSONL），便于审计与回放

状态机：
    requested → queued → sent → replied
                      ↘ failed
                      ↘ bounced

用法：
    from outreach_receipts import ReceiptLedger
    ledger = ReceiptLedger(path)
    ledger.record(event_id, "sent", channel="wechat")
    ledger.record(event_id, "replied", note="已回复报价")
    summary = ledger.summary()
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# 允许的状态
STATES = ("requested", "queued", "sent", "replied", "failed", "bounced")

# 合法流转（from → 允许的 to）
TRANSITIONS: dict[str, set[str]] = {
    "requested": {"queued", "failed"},
    "queued": {"sent", "failed"},
    "sent": {"replied", "bounced", "failed"},
    "replied": set(),
    "failed": {"queued"},      # 允许重试
    "bounced": {"queued"},     # 允许换渠道重试
}

TERMINAL_STATES = {"replied"}


class TransitionError(ValueError):
    """非法的状态流转。"""


@dataclass
class Receipt:
    event_id: str
    state: str
    at: float = field(default_factory=time.time)
    channel: str = ""
    note: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "state": self.state,
            "at": self.at,
            "channel": self.channel,
            "note": self.note,
            "meta": self.meta,
        }


def can_transition(current: str, target: str) -> bool:
    if current not in TRANSITIONS:
        return False
    if target not in STATES:
        return False
    return target in TRANSITIONS[current]


class ReceiptLedger:
    """追加式回执账本（线程安全）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self._receipts: list[Receipt] = []
        if self.path and self.path.exists():
            self._load()

    # ---------- 读写 ----------

    def _load(self) -> None:
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._receipts.append(Receipt(
                    event_id=str(d.get("eventId") or ""),
                    state=str(d.get("state") or ""),
                    at=float(d.get("at") or 0),
                    channel=str(d.get("channel") or ""),
                    note=str(d.get("note") or ""),
                    meta=d.get("meta") if isinstance(d.get("meta"), dict) else {},
                ))
        except OSError:
            pass

    def _append(self, receipt: Receipt) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---------- 状态 ----------

    def current_state(self, event_id: str) -> str | None:
        with self._lock:
            for r in reversed(self._receipts):
                if r.event_id == event_id:
                    return r.state
        return None

    def history(self, event_id: str) -> list[Receipt]:
        with self._lock:
            return [r for r in self._receipts if r.event_id == event_id]

    def record(
        self,
        event_id: str,
        state: str,
        channel: str = "",
        note: str = "",
        meta: dict[str, Any] | None = None,
        enforce_transition: bool = True,
    ) -> Receipt:
        """记录一次状态变更。

        enforce_transition=True 时校验状态机；首次记录（无历史）只允许
        requested/queued/sent。
        """
        if state not in STATES:
            raise ValueError(f"unknown state: {state}")
        with self._lock:
            current = self.current_state(event_id)
            if enforce_transition:
                if current is None:
                    if state not in ("requested", "queued", "sent"):
                        raise TransitionError(
                            f"initial state must be requested/queued/sent, got {state}"
                        )
                elif not can_transition(current, state):
                    raise TransitionError(f"illegal transition {current} -> {state}")
            receipt = Receipt(
                event_id=event_id, state=state, channel=channel,
                note=note, meta=dict(meta or {}),
            )
            self._receipts.append(receipt)
            self._append(receipt)
            return receipt

    # ---------- 统计 ----------

    def all_receipts(self) -> list[Receipt]:
        with self._lock:
            return list(self._receipts)

    def latest_by_event(self) -> dict[str, Receipt]:
        out: dict[str, Receipt] = {}
        with self._lock:
            for r in self._receipts:
                out[r.event_id] = r
        return out

    def summary(self) -> dict[str, Any]:
        latest = self.latest_by_event()
        counts: dict[str, int] = {s: 0 for s in STATES}
        channels: dict[str, int] = {}
        for r in latest.values():
            counts[r.state] = counts.get(r.state, 0) + 1
            if r.channel:
                channels[r.channel] = channels.get(r.channel, 0) + 1

        total = len(latest)
        sent = counts.get("sent", 0) + counts.get("replied", 0) + counts.get("bounced", 0)
        replied = counts.get("replied", 0)

        def rate(n: int, d: int) -> str:
            return f"{n / d * 100:.1f}" if d > 0 else "0.0"

        return {
            "total_events": total,
            "by_state": counts,
            "by_channel": channels,
            "rates": {
                "send_rate": rate(sent, total),
                "reply_rate": rate(replied, sent),
            },
            "pending": counts.get("requested", 0) + counts.get("queued", 0),
            "terminal": sum(1 for r in latest.values() if r.state in TERMINAL_STATES),
        }

    def pending_events(self) -> list[str]:
        latest = self.latest_by_event()
        return sorted(
            eid for eid, r in latest.items()
            if r.state in ("requested", "queued", "failed", "bounced")
        )

    def replied_events(self) -> list[str]:
        latest = self.latest_by_event()
        return sorted(eid for eid, r in latest.items() if r.state == "replied")


def merge_receipts_into_rows(
    rows: Iterable[dict[str, Any]],
    ledger: ReceiptLedger,
    id_field: str = "主页身份ID",
    task_id: str = "",
) -> list[dict[str, Any]]:
    """把回执状态合并到交付行（不改变原有字段）。"""
    latest = ledger.latest_by_event()
    out: list[dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        identity = str(current.get(id_field) or current.get("identity") or "")
        event_id = f"{task_id}:{identity}" if task_id else identity
        receipt = latest.get(event_id)
        if receipt:
            current["外联状态"] = receipt.state
            current["外联渠道"] = receipt.channel
            current["外联时间"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(receipt.at)
            )
            if receipt.note:
                current["外联备注"] = receipt.note
        out.append(current)
    return out


def dumps_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)
