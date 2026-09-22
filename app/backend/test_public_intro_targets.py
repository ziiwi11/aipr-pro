import unittest

from scrape_buyin_public_intro_contacts_cdp import extract_intro_contact, select_targets


class PublicIntroTargetsTest(unittest.TestCase):
    def test_selects_only_the_requested_shop_and_skips_plain_contacts(self):
        rows = [
            {"identity": "1", "shop": "A", "buyin_profile_url": "a", "content_evidence_reviewed": True},
            {"identity": "2", "shop": "B", "buyin_profile_url": "b", "content_evidence_reviewed": True},
            {"identity": "3", "shop": "A", "buyin_profile_url": "c", "content_evidence_reviewed": True, "buyin_contact_wechat": "kept_contact"},
            {"identity": "4", "shop": "A", "buyin_profile_url": "d", "content_evidence_reviewed": False},
        ]
        self.assertEqual([row["identity"] for row in select_targets(rows, "A", 0)], ["1"])

    def test_invalid_placeholder_does_not_block_icon_reveal(self):
        rows = [{
            "identity": "1",
            "shop": "A",
            "buyin_profile_url": "a",
            "content_evidence_reviewed": True,
            "buyin_contact_wechat": "同手机号",
        }]

        self.assertEqual([row["identity"] for row in select_targets(rows, "A", 0)], ["1"])

    def test_extracts_contact_from_stored_profile_without_browser_navigation(self):
        row = {"profile_text": "达人简介 商务合作：demo_contact 概览 场景分析"}
        from scrape_buyin_public_intro_contacts_cdp import apply_stored_profile_contact
        self.assertTrue(apply_stored_profile_contact(row))
        self.assertEqual(row["buyin_contact_wechat"], "demo_contact")
        self.assertEqual(row["buyin_contact_source"], "buyin_profile_public_intro_cached")

    def test_extracts_common_creator_cooperation_labels(self):
        cases = {
            "🈴：haohaosw66（备注来意）": "haohaosw66",
            "小助理：yugezzx": "yugezzx",
            "商务：Dashan_iGo": "Dashan_iGo",
            "如果有问题可以找我zixunpifu2": "zixunpifu2",
            "🫧shuxingxing246 (辛苦备注": "shuxingxing246",
        }
        for intro, expected in cases.items():
            with self.subTest(intro=intro):
                self.assertEqual(extract_intro_contact(intro)[0], expected)

    def test_does_not_treat_masked_platform_labels_as_plain_contact(self):
        self.assertEqual(extract_intro_contact("达人手机号：*********** 达人微信号：***********"), ("", "", ""))

    def test_reuses_previously_cached_intro_when_profile_text_is_absent(self):
        from scrape_buyin_public_intro_contacts_cdp import apply_stored_profile_contact
        row = {"buyin_public_intro": "🈴：cached_creator（备注品牌） 达人微信号：***********"}
        self.assertTrue(apply_stored_profile_contact(row))
        self.assertEqual(row["buyin_contact_wechat"], "cached_creator")


if __name__ == "__main__":
    unittest.main()
