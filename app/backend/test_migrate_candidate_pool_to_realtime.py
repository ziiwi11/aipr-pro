from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from migrate_candidate_pool_to_realtime import migrate_candidate_rows
from realtime_creator_flow import RealtimeCreatorFlowStore


class CandidatePoolMigrationTests(unittest.TestCase):
    def test_contact_visible_candidates_are_not_counted_as_plaintext_or_listed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            flow_path = Path(directory) / "aipr_realtime_creator_flow.json"
            rows = [
                {"identity": "creator-1", "contact_visible": True, "buyin_contact_visible": True},
                {"identity": "creator-2", "contact_visible": True, "buyin_contact_visible": True},
            ]

            summary = migrate_candidate_rows(rows, flow_path)
            store = RealtimeCreatorFlowStore(flow_path)

            self.assertEqual(summary["migrated_count"], 2)
            self.assertEqual(store.summary()["discovered_count"], 2)
            self.assertEqual(store.summary()["plaintext_count"], 0)
            self.assertEqual(store.summary()["listed_count"], 0)

    def test_migration_is_idempotent_and_keeps_terminal_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            flow_path = Path(directory) / "aipr_realtime_creator_flow.json"
            migrate_candidate_rows([{"identity": "creator-1", "nickname": "first"}], flow_path)
            store = RealtimeCreatorFlowStore(flow_path)
            store.record("creator-1", "unsuitable", {"identity": "creator-1"}, reason="review_failed")

            summary = migrate_candidate_rows(
                [{"identity": "creator-1", "nickname": "replacement"}], flow_path
            )

            self.assertEqual(summary["migrated_count"], 0)
            self.assertEqual(summary["skipped_count"], 1)
            self.assertEqual(RealtimeCreatorFlowStore(flow_path).get("creator-1")["state"], "unsuitable")

    def test_reads_candidates_from_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "candidates.json"
            source.write_text(
                json.dumps({"candidates": [{"identity": "creator-1"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            payload = json.loads(source.read_text(encoding="utf-8"))

            summary = migrate_candidate_rows(
                payload["candidates"], Path(directory) / "aipr_realtime_creator_flow.json"
            )

            self.assertEqual(summary["migrated_count"], 1)


if __name__ == "__main__":
    unittest.main()
