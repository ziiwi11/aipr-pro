import unittest
from pathlib import Path

from contact_icons_single import select_contact_targets
from scrape_buyin_profile_contact_icons_cdp import contact_source_pool_ready, daily_quota_exhausted_shops


class ContactParallelTest(unittest.TestCase):
    def test_contact_runner_rejects_partial_replenishment_source(self):
        payload = {
            "status": "checkpoint",
            "complete": False,
            "candidate_count": 1,
            "target_count": 2,
            "strategy": {"strategyPurpose": "replenishment-source-only"},
            "candidates": [{"identity": "1"}],
        }
        self.assertEqual(
            contact_source_pool_ready(payload),
            (False, "source_pool_status_not_ready"),
        )

    def test_contact_runner_accepts_complete_replenishment_source(self):
        payload = {
            "status": "ready",
            "complete": True,
            "candidate_count": 2,
            "target_count": 2,
            "strategy": {"strategyPurpose": "replenishment-source-only"},
            "candidates": [{"identity": "1"}, {"identity": "2"}],
        }
        self.assertEqual(contact_source_pool_ready(payload), (True, "ready"))

    def test_contact_runner_does_not_emit_started_before_source_gate(self):
        source = Path(__file__).with_name("scrape_buyin_profile_contact_icons_cdp.py").read_text(encoding="utf-8")
        gate = source.index("source_ready, source_reason = contact_source_pool_ready(source_payload)")
        started = source.index('emit({"status": "started"')
        self.assertLess(gate, started)

    def test_two_shop_contact_runner_is_parallel(self):
        source = Path(__file__).with_name("scrape_buyin_profile_contact_icons_cdp.py").read_text(encoding="utf-8")
        self.assertIn("ThreadPoolExecutor(max_workers=2)", source)
        self.assertIn("contact_shop_preflight", source)
        self.assertIn("max_workers=max(1, len(active_shops))", source)
        self.assertIn("executor.submit(run_shop, shop, endpoints[shop]) for shop in active_shops", source)

    def test_contact_runner_resumes_from_contact_highwater(self):
        source = Path(__file__).with_name("scrape_buyin_profile_contact_icons_cdp.py").read_text(encoding="utf-8")
        self.assertIn("load_contact_highwater(output_dir, source_payload)", source)
        self.assertIn("save_contact_highwater(output_dir, result)", source)
        self.assertIn('"qualified_plain_contact_count"', source)
        self.assertIn("qualified_totals = contact_totals(qualified_candidates)", source)

    def test_contact_icons_only_receive_verified_creators_for_the_shop(self):
        rows = [
            {"identity": "a1", "shop": "A", "content_evidence_reviewed": True, "precontact_qualified": True},
            {"identity": "a2", "shop": "A", "content_evidence_reviewed": True, "precontact_qualified": False},
            {"identity": "b1", "shop": "B", "content_evidence_reviewed": True, "precontact_qualified": True},
            {"identity": "a3", "shop": "A", "content_evidence_reviewed": True, "precontact_qualified": True, "buyin_contact_wechat": "kept"},
        ]
        selected = select_contact_targets(rows, "A", 0)
        self.assertEqual([row["identity"] for row in selected], ["a1"])

    def test_reports_shops_that_exhausted_daily_contact_quota(self):
        results = [
            ("A", [{"ui_contact_probe_status": "daily_quota_exhausted"}]),
            ("B", [{"ui_contact_probe_status": "revealed"}]),
        ]
        self.assertEqual(daily_quota_exhausted_shops(results), ["A"])

    def test_recently_rate_limited_creators_move_behind_fresh_creators(self):
        base = {"shop": "A", "content_evidence_reviewed": True, "precontact_qualified": True}
        rows = [
            {**base, "identity": "retry", "ui_contact_probe_status": "rate_limited", "ui_contact_probe_at": "2026-08-02T01:00:00"},
            {**base, "identity": "fresh"},
        ]
        self.assertEqual([row["identity"] for row in select_contact_targets(rows, "A", 0)], ["fresh", "retry"])

    def test_worker_logs_contact_presence_without_plaintext_values(self):
        source = Path(__file__).with_name("contact_icons_single.py").read_text(encoding="utf-8")
        progress_block = source.split('"status": "contact_revealed" if has_plain(current)', 1)[1]
        progress_block = progress_block.split("if len(processed) % 10", 1)[0]
        self.assertIn('"has_wechat"', progress_block)
        self.assertIn('"has_phone"', progress_block)
        self.assertIn('"has_email"', progress_block)
        self.assertNotIn('"wechat":', progress_block)
        self.assertNotIn('"phone":', progress_block)

    def test_worker_stops_on_frequency_control_without_in_process_retry(self):
        source = Path(__file__).with_name("contact_icons_single.py").read_text(encoding="utf-8")
        rate_limit_block = source.split('if current.get("ui_contact_probe_status") == "rate_limited":', 1)[1]
        rate_limit_block = rate_limit_block.split("except PlaywrightTimeoutError", 1)[0]
        self.assertIn('"status": "contact_platform_paused"', rate_limit_block)
        self.assertNotIn("page.wait_for_timeout", rate_limit_block)
        self.assertNotIn("for retry_index", rate_limit_block)


if __name__ == "__main__":
    unittest.main()
