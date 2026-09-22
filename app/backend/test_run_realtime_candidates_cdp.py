from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from realtime_creator_flow import RealtimeCreatorFlowStore
from run_realtime_candidates_cdp import pending_candidate_rows, process_pending_rows


class FakeProcessor:
    def __init__(self, pause_identity: str = ""):
        self.calls: list[str] = []
        self.pause_identity = pause_identity

    def process(self, _context, _page, row):
        self.calls.append(row["identity"])
        if row["identity"] == self.pause_identity:
            return {
                **row,
                "realtime_flow_state": "contact_revealing",
                "realtime_flow_reason": "rate_limited",
            }
        return {**row, "realtime_flow_state": "listed", "realtime_flow_reason": ""}


class RealtimeCandidateRunnerTests(unittest.TestCase):
    def test_pending_rows_skip_terminal_and_preserve_source_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RealtimeCreatorFlowStore(Path(directory) / "flow.json")
            store.record("done", "unsuitable", {"identity": "done"})
            store.record("pending", "discovered", {"identity": "pending"})
            rows = [
                {"identity": "done", "shop": "A"},
                {"identity": "pending", "shop": "B"},
                {"identity": "new", "shop": "A"},
            ]

            pending = pending_candidate_rows(rows, store)

            self.assertEqual([row["identity"] for row in pending], ["pending", "new"])

    def test_processes_one_by_one_and_stops_immediately_on_platform_pause(self) -> None:
        processor = FakeProcessor(pause_identity="second")
        sessions = {
            "A": (object(), object()),
            "B": (object(), object()),
        }
        rows = [
            {"identity": "first", "shop": "A"},
            {"identity": "second", "shop": "B"},
            {"identity": "third", "shop": "A"},
        ]

        result = process_pending_rows(rows, processor, sessions)

        self.assertEqual(processor.calls, ["first", "second"])
        self.assertEqual(result, {"processed": 2, "paused": True, "remaining": 1})

    def test_missing_shop_falls_back_to_available_session(self) -> None:
        processor = FakeProcessor()
        sessions = {"A": (object(), object())}

        result = process_pending_rows(
            [{"identity": "one", "shop": "B"}], processor, sessions
        )

        self.assertEqual(processor.calls, ["one"])
        self.assertEqual(result["processed"], 1)


if __name__ == "__main__":
    unittest.main()
