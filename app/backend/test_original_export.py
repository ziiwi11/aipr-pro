from __future__ import annotations

import unittest

import openpyxl

from export_original_format_with_contacts import append_unmatched_rows


class OriginalExportTest(unittest.TestCase):
    def test_appends_new_creator_using_original_headers(self) -> None:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "内容排序池"
        sheet.append(["品牌达人名单"])
        sheet.append([])
        sheet.append([
            "品牌来源", "来源类型", "达人昵称", "主页身份ID", "抖音主页", "综合评分", "等级",
            "精选联盟状态", "抖店精确挂车等级", "联系方式", "联系方式来源", "联系方式状态",
            "建议报价", "报价依据", "数据状态", "品牌/内容证据", "下一步", "微信", "手机号",
        ])
        sheet.row_dimensions[3].height = 44
        row = {
            "达人昵称": "新达人",
            "主页身份ID": "creator-1",
            "抖音主页": "https://douyin.example/1",
            "综合评分": 92,
            "推荐结论": "推荐建联",
            "达人等级": "LV3",
            "明文联系方式": "微信:wx1；手机:13800000000",
            "联系方式来源": "buyin_profile_ui_contact_icon",
            "联系方式状态": "已获取明文",
            "建议报价": 650,
            "推荐理由": "证据完整",
            "验证结论": "主页与内容已验证",
            "内容证据": "真人口播",
            "微信": "wx1",
            "手机号": "13800000000",
        }

        appended = append_unmatched_rows(workbook, [row], "测试品牌", set())

        self.assertEqual(appended, 1)
        self.assertEqual(sheet.cell(4, 3).value, "新达人")
        self.assertEqual(sheet.cell(4, 18).value, "wx1")
        self.assertEqual(sheet.cell(4, 19).value, "13800000000")
        self.assertEqual(sheet.row_dimensions[4].height, 44)


if __name__ == "__main__":
    unittest.main()
