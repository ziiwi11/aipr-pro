import json
import tempfile
import unittest
from pathlib import Path

from contact_highwater import load_contact_highwater, save_contact_highwater


class ContactHighWaterTest(unittest.TestCase):
    def test_resume_merges_existing_plain_contact_into_fresh_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            previous = {
                "candidates": [
                    {"identity": "kept", "nickname": "A", "content_evidence_reviewed": True, "buyin_contact_wechat": "wx_kept"},
                    {"identity": "removed", "nickname": "Old", "content_evidence_reviewed": True, "buyin_contact_wechat": "wx_old"},
                ]
            }
            (output_dir / "aipr_creator_contacts_20260718_120000.json").write_text(
                json.dumps(previous, ensure_ascii=False), encoding="utf-8"
            )
            fresh = {
                "status": "ready",
                "candidates": [
                    {"identity": "kept", "nickname": "A", "content_evidence_reviewed": True},
                    {"identity": "new", "nickname": "B", "content_evidence_reviewed": True},
                ],
            }

            resumed = load_contact_highwater(output_dir, fresh)

            self.assertEqual(len(resumed["candidates"]), 2)
            self.assertEqual(resumed["candidates"][0]["buyin_contact_wechat"], "wx_kept")
            self.assertNotIn("removed", [row["identity"] for row in resumed["candidates"]])

    def test_resume_never_restores_stale_evidence_or_qualification_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            output_dir = Path(folder)
            previous = {
                "candidates": [{
                    "identity": "kept",
                    "content_evidence_reviewed": True,
                    "evidence_contract_version": 1,
                    "evidence_status": "verified",
                    "douyin_homepage": "https://www.douyin.com/old",
                    "precontact_qualified": True,
                    "buyin_contact_wechat": "wx_kept",
                }]
            }
            (output_dir / "aipr_contact_highwater.json").write_text(
                json.dumps(previous, ensure_ascii=False), encoding="utf-8"
            )
            fresh = {
                "status": "ready",
                "candidates": [{
                    "identity": "kept",
                    "content_evidence_reviewed": False,
                    "evidence_contract_version": 4,
                    "evidence_status": "content_unverified",
                    "douyin_homepage": "https://www.douyin.com/fresh",
                    "precontact_qualified": False,
                }],
            }

            resumed = load_contact_highwater(output_dir, fresh)
            candidate = resumed["candidates"][0]

            self.assertEqual(candidate["buyin_contact_wechat"], "wx_kept")
            self.assertFalse(candidate["content_evidence_reviewed"])
            self.assertEqual(candidate["evidence_contract_version"], 4)
            self.assertEqual(candidate["evidence_status"], "content_unverified")
            self.assertEqual(candidate["douyin_homepage"], "https://www.douyin.com/fresh")
            self.assertFalse(candidate["precontact_qualified"])

    def test_save_writes_stable_contact_highwater_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save_contact_highwater(Path(folder), {"candidates": [{"identity": "1"}]})
            self.assertEqual(path.name, "aipr_contact_highwater.json")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
