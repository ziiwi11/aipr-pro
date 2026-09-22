from __future__ import annotations

import unittest

from prepare_osmana_contact_queue import build_contact_queue


class PrepareOsmanaContactQueueTest(unittest.TestCase):
    def test_keeps_only_product_and_content_verified_candidates(self) -> None:
        rows = [
            {"identity": "a", "douyin_id": "same-public", "content_evidence_reviewed": True, "visual_persona_verified": True, "osmana_evaluation": {"underwear_product_sales_low": 25000}},
            {"identity": "b", "content_evidence_reviewed": False, "osmana_evaluation": {"underwear_product_sales_low": 25000}},
            {"identity": "c", "content_evidence_reviewed": True, "osmana_evaluation": {"underwear_product_sales_low": 9999}},
            {"identity": "d", "content_evidence_reviewed": True, "visual_persona_verified": False, "osmana_evaluation": {"underwear_product_sales_low": 25000}},
            {"identity": "e", "douyin_id": "same-public", "content_evidence_reviewed": True, "visual_persona_verified": True, "osmana_evaluation": {"underwear_product_sales_low": 25000}},
        ]
        result = build_contact_queue(rows, 10000)
        self.assertEqual([row["identity"] for row in result], ["a"])

    def test_can_prepare_previsual_contact_probe_queue(self) -> None:
        rows = [{
            "identity": "pending-visual",
            "content_evidence_reviewed": True,
            "visual_persona_verified": False,
            "osmana_evaluation": {"underwear_product_sales_low": 25000},
        }]

        result = build_contact_queue(rows, 10000, require_visual=False)

        self.assertEqual([row["identity"] for row in result], ["pending-visual"])


if __name__ == "__main__":
    unittest.main()
