"""外联回执账本测试

覆盖：
- 状态机流转（合法/非法）
- 首次记录的状态约束
- 持久化与重载
- 统计汇总（发送率/回复率）
- 待处理与已回复筛选
- 合并到交付行
- 边界：空账本、损坏行、并发
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from outreach_receipts import (  # noqa: E402
    ReceiptLedger,
    TransitionError,
    can_transition,
    merge_receipts_into_rows,
)


class TransitionRuleTest(unittest.TestCase):
    def test_legal_transitions(self) -> None:
        self.assertTrue(can_transition("requested", "queued"))
        self.assertTrue(can_transition("queued", "sent"))
        self.assertTrue(can_transition("sent", "replied"))
        self.assertTrue(can_transition("sent", "bounced"))
        self.assertTrue(can_transition("failed", "queued"))

    def test_illegal_transitions(self) -> None:
        self.assertFalse(can_transition("requested", "sent"))
        self.assertFalse(can_transition("replied", "sent"))
        self.assertFalse(can_transition("replied", "queued"))
        self.assertFalse(can_transition("unknown", "sent"))

    def test_unknown_target(self) -> None:
        self.assertFalse(can_transition("sent", "bogus"))


class RecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ReceiptLedger()

    def test_first_record_allows_sent(self) -> None:
        self.ledger.record("e1", "sent")
        self.assertEqual(self.ledger.current_state("e1"), "sent")

    def test_first_record_rejects_replied(self) -> None:
        with self.assertRaises(TransitionError):
            self.ledger.record("e1", "replied")

    def test_unknown_state_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.record("e1", "bogus")

    def test_full_happy_path(self) -> None:
        self.ledger.record("e1", "requested")
        self.ledger.record("e1", "queued")
        self.ledger.record("e1", "sent", channel="wechat")
        self.ledger.record("e1", "replied", note="已回复报价")
        self.assertEqual(self.ledger.current_state("e1"), "replied")
        self.assertEqual(len(self.ledger.history("e1")), 4)

    def test_illegal_jump_rejected(self) -> None:
        self.ledger.record("e1", "requested")
        with self.assertRaises(TransitionError):
            self.ledger.record("e1", "sent")

    def test_enforce_can_be_disabled(self) -> None:
        self.ledger.record("e1", "requested")
        self.ledger.record("e1", "sent", enforce_transition=False)
        self.assertEqual(self.ledger.current_state("e1"), "sent")

    def test_failed_then_retry(self) -> None:
        self.ledger.record("e1", "queued")
        self.ledger.record("e1", "failed", note="限流")
        self.ledger.record("e1", "queued")
        self.ledger.record("e1", "sent")
        self.assertEqual(self.ledger.current_state("e1"), "sent")

    def test_unknown_event_returns_none(self) -> None:
        self.assertIsNone(self.ledger.current_state("nope"))


class PersistenceTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "receipts.jsonl"
            ledger = ReceiptLedger(path)
            ledger.record("e1", "sent", channel="phone")
            ledger.record("e2", "requested")

            reloaded = ReceiptLedger(path)
            self.assertEqual(reloaded.current_state("e1"), "sent")
            self.assertEqual(reloaded.current_state("e2"), "requested")
            self.assertEqual(len(reloaded.all_receipts()), 2)

    def test_missing_file_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ledger = ReceiptLedger(Path(d) / "nope.jsonl")
            self.assertEqual(ledger.all_receipts(), [])

    def test_corrupt_lines_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "receipts.jsonl"
            path.write_text(
                '{"eventId":"e1","state":"sent","at":1}\n'
                'not json\n'
                '{"eventId":"e2","state":"queued","at":2}\n',
                encoding="utf-8",
            )
            ledger = ReceiptLedger(path)
            self.assertEqual(len(ledger.all_receipts()), 2)

    def test_appends_not_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "receipts.jsonl"
            ReceiptLedger(path).record("e1", "sent")
            ReceiptLedger(path).record("e2", "sent")
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)


class SummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ReceiptLedger()

    def test_empty_summary(self) -> None:
        s = self.ledger.summary()
        self.assertEqual(s["total_events"], 0)
        self.assertEqual(s["rates"]["send_rate"], "0.0")
        self.assertEqual(s["rates"]["reply_rate"], "0.0")

    def test_counts_by_state(self) -> None:
        self.ledger.record("e1", "sent")
        self.ledger.record("e2", "sent")
        self.ledger.record("e2", "replied")
        self.ledger.record("e3", "requested")
        s = self.ledger.summary()
        self.assertEqual(s["total_events"], 3)
        self.assertEqual(s["by_state"]["sent"], 1)      # e1
        self.assertEqual(s["by_state"]["replied"], 1)   # e2
        self.assertEqual(s["by_state"]["requested"], 1)  # e3

    def test_send_and_reply_rates(self) -> None:
        for i in range(4):
            self.ledger.record(f"e{i}", "sent")
        self.ledger.record("e0", "replied")
        self.ledger.record("e1", "replied")
        s = self.ledger.summary()
        self.assertEqual(s["rates"]["send_rate"], "100.0")
        self.assertEqual(s["rates"]["reply_rate"], "50.0")

    def test_channel_breakdown(self) -> None:
        self.ledger.record("e1", "sent", channel="wechat")
        self.ledger.record("e2", "sent", channel="wechat")
        self.ledger.record("e3", "sent", channel="phone")
        s = self.ledger.summary()
        self.assertEqual(s["by_channel"], {"wechat": 2, "phone": 1})

    def test_pending_and_replied_lists(self) -> None:
        """pending 只含未发出的事件（requested/queued/failed/bounced）。"""
        self.ledger.record("e1", "requested")
        self.ledger.record("e2", "sent")
        self.ledger.record("e2", "replied")
        self.ledger.record("e3", "sent")
        self.ledger.record("e4", "queued")
        self.ledger.record("e5", "queued")
        self.ledger.record("e5", "failed")
        self.assertEqual(self.ledger.pending_events(), ["e1", "e4", "e5"])
        self.assertEqual(self.ledger.replied_events(), ["e2"])


class MergeTest(unittest.TestCase):
    def test_merges_receipt_into_row(self) -> None:
        ledger = ReceiptLedger()
        ledger.record("t1:uid1", "sent", channel="wechat")
        rows = [{"主页身份ID": "uid1", "达人昵称": "a"}]
        merged = merge_receipts_into_rows(rows, ledger, task_id="t1")
        self.assertEqual(merged[0]["外联状态"], "sent")
        self.assertEqual(merged[0]["外联渠道"], "wechat")
        self.assertIn("外联时间", merged[0])

    def test_rows_without_receipt_unchanged(self) -> None:
        ledger = ReceiptLedger()
        rows = [{"主页身份ID": "uid-x", "达人昵称": "a"}]
        merged = merge_receipts_into_rows(rows, ledger, task_id="t1")
        self.assertNotIn("外联状态", merged[0])
        self.assertEqual(merged[0]["达人昵称"], "a")

    def test_original_fields_preserved(self) -> None:
        ledger = ReceiptLedger()
        ledger.record("t1:uid1", "sent")
        rows = [{"主页身份ID": "uid1", "手机号": "138", "达人昵称": "a"}]
        merged = merge_receipts_into_rows(rows, ledger, task_id="t1")
        self.assertEqual(merged[0]["手机号"], "138")
        self.assertEqual(merged[0]["达人昵称"], "a")

    def test_note_merged_when_present(self) -> None:
        ledger = ReceiptLedger()
        ledger.record("t1:uid1", "sent")
        ledger.record("t1:uid1", "replied", note="同意合作")
        merged = merge_receipts_into_rows([{"主页身份ID": "uid1"}], ledger, task_id="t1")
        self.assertEqual(merged[0]["外联备注"], "同意合作")


class ConcurrencyTest(unittest.TestCase):
    def test_concurrent_records_all_land(self) -> None:
        ledger = ReceiptLedger()

        def worker(n: int) -> None:
            ledger.record(f"e{n}", "sent")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(ledger.latest_by_event()), 30)
        self.assertEqual(ledger.summary()["by_state"]["sent"], 30)


if __name__ == "__main__":
    unittest.main()
