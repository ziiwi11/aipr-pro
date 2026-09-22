from __future__ import annotations

import unittest

from import_osmana_verified_legacy_sources import convert_legacy_candidate


class ImportOsmanaVerifiedLegacySourcesTest(unittest.TestCase):
    def test_maps_lv2_pure_short_video_creator_with_plain_contact(self) -> None:
        row = {
            "nickname": "梨形身材穿搭",
            "buyin_uid": "encrypted-uid",
            "buyin_account_id": "123456789",
            "cart_talent_level": "LV2",
            "buyin_main_sale_type": "纯短视频",
            "buyin_contact_wechat": "shape_test",
            "buyin_contact_phone": "13800138000",
            "source_keywords": ["提臀裤", "真人试穿"],
        }

        converted = convert_legacy_candidate(row, "A")

        self.assertEqual(converted["talent_level"], "LV2")
        self.assertEqual(converted["douyin_id"], "123456789")
        self.assertEqual(converted["buyin_contact_wechat"], "shape_test")
        self.assertIn("uid=encrypted-uid", converted["buyin_profile_url"])

    def test_rejects_lv1_live_or_missing_plain_contact(self) -> None:
        base = {
            "nickname": "测试达人",
            "buyin_uid": "encrypted-uid",
            "cart_talent_level": "LV2",
            "buyin_main_sale_type": "纯短视频",
            "buyin_contact_wechat": "shape_test",
        }
        for update in (
            {"cart_talent_level": "LV1"},
            {"buyin_main_sale_type": "直播为主"},
            {"buyin_contact_wechat": "", "buyin_contact_phone": ""},
        ):
            self.assertIsNone(convert_legacy_candidate({**base, **update}, "A"))

    def test_rejects_male_child_and_maternity_sources(self) -> None:
        base = {
            "buyin_uid": "encrypted-uid",
            "cart_talent_level": "LV3",
            "buyin_main_sale_type": "纯短视频",
            "buyin_contact_wechat": "shape_test",
        }
        for nickname in ("男士内裤测评", "女童安全裤", "孕妇哺乳内衣"):
            self.assertIsNone(convert_legacy_candidate({**base, "nickname": nickname}, "B"))

    def test_maps_chinese_delivery_row_when_sale_type_will_be_reverified(self) -> None:
        row = {
            "达人昵称": "精致穿搭达人",
            "抖音号/账号ID": "public-douyin",
            "精选联盟主页": "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=encrypted-chinese",
            "达人等级": "LV3",
            "微信": "wechat_ready",
            "手机": "13900139000",
        }

        converted = convert_legacy_candidate(row, "B", allow_unknown_sale_type=True)

        self.assertEqual(converted["buyin_uid"], "encrypted-chinese")
        self.assertEqual(converted["nickname"], "精致穿搭达人")
        self.assertEqual(converted["douyin_id"], "public-douyin")
        self.assertEqual(converted["buyin_contact_wechat"], "wechat_ready")
        self.assertEqual(converted["main_sale_type"], "")


if __name__ == "__main__":
    unittest.main()
