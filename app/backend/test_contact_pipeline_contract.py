from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contact_pipeline_contract import (
    build_profile_url,
    copy_if_distinct,
    merge_contact_candidates,
    profile_content_ready,
)


class ContactPipelineContractTest(unittest.TestCase):
    def test_build_profile_url_uses_buyin_uid(self) -> None:
        url = build_profile_url("v2_author_uid")

        self.assertIn("daren-profile?uid=v2_author_uid", url)
        self.assertIn("author_type=1", url)

    def test_build_profile_url_includes_author_level_when_known(self) -> None:
        url = build_profile_url("v2_author_uid", 3)

        self.assertIn("author_level=3", url)

    def test_merge_preserves_creator_and_adds_plain_contacts(self) -> None:
        base = [{"identity": "creator-1", "nickname": "A", "shop": "A"}]
        updates = [{
            "identity": "creator-1",
            "nickname": "A",
            "buyin_contact_wechat": "wx_a",
            "buyin_contact_phone": "13800000000",
        }]

        merged = merge_contact_candidates(base, updates)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["shop"], "A")
        self.assertEqual(merged[0]["buyin_contact_wechat"], "wx_a")
        self.assertEqual(merged[0]["buyin_contact_phone"], "13800000000")

    def test_copy_if_distinct_does_not_copy_a_file_onto_itself(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "result.json"
            source.write_text("{}", encoding="utf-8")

            copied = copy_if_distinct(source, source)

            self.assertFalse(copied)
            self.assertEqual(source.read_text(encoding="utf-8"), "{}")

    def test_profile_content_ready_rejects_navigation_only_shell(self) -> None:
        self.assertFalse(profile_content_ready("首页 推商品 找达人 管合作 看数据 消息 通知 设置"))
        self.assertTrue(profile_content_ready("达人自主披露联系方式，你可点击小眼睛查看详细规则"))


if __name__ == "__main__":
    unittest.main()
