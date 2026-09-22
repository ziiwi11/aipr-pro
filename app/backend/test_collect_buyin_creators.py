from __future__ import annotations

import unittest

from collect_buyin_creators_cdp import create_realtime_review_page, process_new_candidate_identities


class FakeProcessor:
    def __init__(self):
        self.calls: list[str] = []

    def process(self, _context, _page, candidate):
        self.calls.append(candidate["identity"])
        return {**candidate, "realtime_flow_state": "listed"}


class RealtimeCollectorIntegrationTests(unittest.TestCase):
    def test_reuses_embedded_browse_page_when_context_cannot_create_target(self) -> None:
        browse_page = object()

        class EmbeddedContext:
            def new_page(self):
                raise RuntimeError("Target.createTarget: Not supported")

        review_page, shared = create_realtime_review_page(EmbeddedContext(), browse_page)

        self.assertIs(review_page, browse_page)
        self.assertTrue(shared)

    def test_uses_dedicated_review_page_when_context_supports_it(self) -> None:
        review_page = object()

        class NormalContext:
            def new_page(self):
                return review_page

        selected, shared = create_realtime_review_page(NormalContext(), object())

        self.assertIs(selected, review_page)
        self.assertFalse(shared)

    def test_processes_only_new_identities_in_discovery_order(self) -> None:
        output = {
            "existing": {"identity": "existing"},
            "new-1": {"identity": "new-1"},
            "new-2": {"identity": "new-2"},
        }
        processor = FakeProcessor()

        result = process_new_candidate_identities(
            output,
            ["new-1", "new-2"],
            processor,
            context=object(),
            page=object(),
        )

        self.assertEqual(processor.calls, ["new-1", "new-2"])
        self.assertEqual(result, {"processed": 2, "paused": False})
        self.assertNotIn("realtime_flow_state", output["existing"])
        self.assertEqual(output["new-1"]["realtime_flow_state"], "listed")

    def test_single_rate_limit_does_not_pause_but_daily_quota_does(self) -> None:
        """单次 rate_limited 只跳过该达人；daily_quota_exhausted 立即暂停。"""

        class RateLimitedProcessor(FakeProcessor):
            def process(self, _context, _page, candidate):
                self.calls.append(candidate["identity"])
                return {
                    **candidate,
                    "realtime_flow_state": "contact_revealing",
                    "realtime_flow_reason": "rate_limited",
                }

        output = {"new-1": {"identity": "new-1"}, "new-2": {"identity": "new-2"}}
        processor = RateLimitedProcessor()
        result = process_new_candidate_identities(
            output, ["new-1", "new-2"], processor, context=object(), page=object(),
        )
        # 两次都是 rate_limited，未达连续 3 次阈值 → 不暂停
        self.assertEqual(processor.calls, ["new-1", "new-2"])
        self.assertEqual(result, {"processed": 2, "paused": False})

        class QuotaProcessor(FakeProcessor):
            def process(self, _context, _page, candidate):
                self.calls.append(candidate["identity"])
                return {
                    **candidate,
                    "realtime_flow_state": "contact_revealing",
                    "realtime_flow_reason": "daily_quota_exhausted",
                }

        output2 = {"new-1": {"identity": "new-1"}, "new-2": {"identity": "new-2"}}
        processor2 = QuotaProcessor()
        result2 = process_new_candidate_identities(
            output2, ["new-1", "new-2"], processor2, context=object(), page=object(),
        )
        # 每日额度耗尽 → 立即暂停
        self.assertEqual(processor2.calls, ["new-1"])
        self.assertEqual(result2, {"processed": 1, "paused": True})


if __name__ == "__main__":
    unittest.main()
