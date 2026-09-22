from __future__ import annotations

import unittest

from prepare_osmana_evidence_queue import build_pending_queue


class PrepareOsmanaQueueTest(unittest.TestCase):
    def test_deduplicates_and_excludes_completed_evidence(self) -> None:
        pools = [
            {"candidates": [{"identity": "a", "nickname": "甲", "source_keywords": ["塑身裤"], "shop": "A"}]},
            {"candidates": [
                {"identity": "a", "nickname": "甲", "source_keywords": ["文胸"], "shop": "B"},
                {"identity": "b", "nickname": "乙", "source_keywords": ["内衣"], "shop": "B"},
            ]},
        ]
        completed = [{"candidates": [{"identity": "a", "buyin_product_evidence_reviewed": True}]}]

        result = build_pending_queue(pools, completed)

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["identity"], "b")

    def test_merges_source_keywords_for_unique_candidate(self) -> None:
        pools = [
            {"candidates": [{"identity": "a", "source_keywords": ["塑身裤"], "shop": "A"}]},
            {"candidates": [{"identity": "a", "source_keywords": ["文胸"], "shop": "B"}]},
        ]
        result = build_pending_queue(pools, [])
        self.assertEqual(result["candidates"][0]["source_keywords"], ["塑身裤", "文胸"])

    def test_deduplicates_different_encrypted_ids_for_same_public_douyin_id(self) -> None:
        pools = [{"candidates": [
            {"identity": "encrypted-a", "douyin_id": "public-1", "source_keywords": ["165/90"], "shop": "B"},
            {"identity": "encrypted-b", "douyin_id": "public-1", "source_keywords": ["165/100"], "shop": "B"},
        ]}]

        result = build_pending_queue(pools, [])

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["source_keywords"], ["165/90", "165/100"])

    def test_excludes_public_account_completed_under_another_encrypted_id(self) -> None:
        pools = [{"candidates": [
            {"identity": "new-encrypted", "douyin_id": "public-1", "shop": "B"},
        ]}]
        completed = [{"candidates": [
            {"identity": "old-encrypted", "douyin_id": "public-1", "buyin_product_evidence_reviewed": True},
        ]}]

        result = build_pending_queue(pools, completed)

        self.assertEqual(result["candidate_count"], 0)

    def test_excludes_every_creator_in_prior_delivery_even_without_review_flags(self) -> None:
        pools = [{"candidates": [
            {"identity": "new-a", "douyin_id": "kept", "shop": "B"},
            {"identity": "new-b", "douyin_id": "already-delivered", "shop": "B"},
        ]}]
        prior_deliveries = [{"candidates": [
            {"identity": "old-b", "douyin_id": "already-delivered"},
        ]}]

        result = build_pending_queue(pools, [], prior_deliveries)

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["douyin_id"], "kept")
        self.assertEqual(result["prior_delivery_excluded_count"], 1)


if __name__ == "__main__":
    unittest.main()
