"""ROI 转化看板测试

覆盖：
- 漏斗的包含式递减（每阶段 ⊆ 上一阶段）
- 转化率计算
- 联系方式分类（仅手机/仅微信/两者）
- 等级与类目分布
- 风控状态统计
- 成本估算
- 速率计算
- 边界：空输入、缺字段
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from roi_dashboard import (  # noqa: E402
    build_category_breakdown,
    build_jev_breakdown,
    build_contact_breakdown,
    build_funnel,
    build_level_breakdown,
    build_risk_breakdown,
    build_roi,
    format_roi_text,
)


def verified(**kw):
    base = {
        "identity": "x",
        "content_evidence_reviewed": True,
        "precontact_qualified": True,
        "buyin_contact_phone": "13800138000",
        "talent_level": "LV2",
        "category": "个护家清/食品饮料",
        "推荐结论": "推荐建联",
    }
    base.update(kw)
    return base


class FunnelTest(unittest.TestCase):
    def test_empty_input(self) -> None:
        f = build_funnel([])
        self.assertEqual(f["candidates"], 0)
        self.assertEqual(f["verified"], 0)
        self.assertEqual(f["rates"]["verify_rate"], "0.0")

    def test_monotonic_decreasing(self) -> None:
        """漏斗必须单调递减（包含式设计）。"""
        rows = [
            verified(),
            verified(),
            verified(buyin_contact_phone=""),
            verified(precontact_qualified=False),
            {"identity": "y"},  # 未验证
        ]
        f = build_funnel(rows)
        self.assertGreaterEqual(f["candidates"], f["verified"])
        self.assertGreaterEqual(f["verified"], f["qualified"])
        self.assertGreaterEqual(f["qualified"], f["revealed"])
        self.assertGreaterEqual(f["revealed"], f["delivered"])

    def test_counts(self) -> None:
        rows = [
            verified(),                                      # 全通过
            verified(),                                      # 全通过
            verified(buyin_contact_phone=""),                # 无联系方式
            verified(content_evidence_reviewed=False),       # 未验证
        ]
        f = build_funnel(rows)
        self.assertEqual(f["candidates"], 4)
        self.assertEqual(f["verified"], 3)
        self.assertEqual(f["qualified"], 3)
        self.assertEqual(f["revealed"], 2)
        self.assertEqual(f["delivered"], 2)

    def test_delivered_requires_recommendation(self) -> None:
        rows = [verified(推荐结论="淘汰")]
        f = build_funnel(rows)
        self.assertEqual(f["revealed"], 1)
        self.assertEqual(f["delivered"], 0)

    def test_rates_format(self) -> None:
        rows = [verified(), verified(), verified(), verified(buyin_contact_phone="")]
        f = build_funnel(rows)
        self.assertEqual(f["rates"]["verify_rate"], "100.0")
        self.assertEqual(f["rates"]["reveal_rate"], "75.0")


class ContactBreakdownTest(unittest.TestCase):
    def test_classification(self) -> None:
        rows = [
            verified(),                                                    # 仅手机
            verified(buyin_contact_phone="", buyin_contact_wechat="wx1"),   # 仅微信
            verified(buyin_contact_wechat="wx2"),                           # 两者
            {"identity": "z"},                                              # 无
        ]
        c = build_contact_breakdown(rows)
        self.assertEqual(c["with_contact"], 3)
        self.assertEqual(c["phone"], 2)
        self.assertEqual(c["wechat"], 2)
        self.assertEqual(c["only_phone"], 1)
        self.assertEqual(c["only_wechat"], 1)
        self.assertEqual(c["both_phone_and_wechat"], 1)
        self.assertEqual(c["contact_rate"], "75.0")

    def test_cart_contact_aliases(self) -> None:
        """cart_* 字段也应被识别。"""
        rows = [{"identity": "a", "cart_contact_phone": "139"}]
        c = build_contact_breakdown(rows)
        self.assertEqual(c["with_contact"], 1)
        self.assertEqual(c["phone"], 1)


class BreakdownTest(unittest.TestCase):
    def test_levels_sorted(self) -> None:
        rows = [verified(talent_level="LV2"), verified(talent_level="LV1"),
                verified(talent_level="LV1"), verified(talent_level="")]
        self.assertEqual(build_level_breakdown(rows), {"LV1": 2, "LV2": 1})

    def test_levels_accepts_chinese_field(self) -> None:
        rows = [{"达人等级": "LV3"}]
        self.assertEqual(build_level_breakdown(rows), {"LV3": 1})

    def test_categories_use_head_and_limit(self) -> None:
        rows = [verified(category="个护家清/食品饮料")] * 3 + [verified(category="美妆/个护家清")] * 1
        cats = build_category_breakdown(rows, limit=5)
        self.assertEqual(cats.get("个护家清"), 3)
        self.assertEqual(cats.get("美妆"), 1)


class RiskBreakdownTest(unittest.TestCase):
    def test_detects_rate_limit_marker(self) -> None:
        rows = [verified(ui_contact_probe_status="clicked_not_revealed",
                         ui_contact_message="请求过于频繁，请稍后再试")]
        r = build_risk_breakdown(rows)
        self.assertEqual(r["rate_limited"], 1)
        self.assertEqual(r["not_revealed"], 1)

    def test_counts_failures(self) -> None:
        rows = [verified(ui_contact_probe_status="exception"),
                verified(ui_contact_probe_status="timeout")]
        r = build_risk_breakdown(rows)
        self.assertEqual(r["failed"], 2)

    def test_clean_rows_report_zero(self) -> None:
        r = build_risk_breakdown([verified()])
        self.assertEqual(r, {"rate_limited": 0, "not_revealed": 0, "failed": 0})


class RoiTest(unittest.TestCase):
    def test_cost_estimates(self) -> None:
        rows = [verified()] * 10
        report = build_roi(rows, {"budget": 1000, "cost_per_reveal": 5})
        r = report["roi"]
        self.assertEqual(r["estimated_spent"], 50.0)
        self.assertEqual(r["budget_remaining"], 950.0)
        self.assertEqual(r["budget_utilization"], "5.0")
        self.assertEqual(r["cost_per_revealed_contact"], 5.0)

    def test_no_budget_yields_none(self) -> None:
        report = build_roi([verified()], {})
        self.assertIsNone(report["roi"]["budget_remaining"])
        self.assertIsNone(report["roi"]["cost_per_revealed_contact"])

    def test_throughput(self) -> None:
        rows = [verified()] * 10
        report = build_roi(rows, {"elapsed_minutes": 5})
        t = report["throughput"]
        self.assertEqual(t["reveals_per_minute"], 2.0)
        self.assertEqual(t["seconds_per_reveal"], 30.0)

    def test_no_elapsed_yields_none(self) -> None:
        report = build_roi([verified()], {})
        self.assertIsNone(report["throughput"])

    def test_report_shape(self) -> None:
        report = build_roi([verified()], {"name": "t"})
        for key in ("generated_at", "task", "funnel", "contacts", "levels",
                    "categories", "risk", "roi", "throughput"):
            self.assertIn(key, report)

    def test_empty_rows_safe(self) -> None:
        report = build_roi([], {})
        self.assertEqual(report["funnel"]["candidates"], 0)
        self.assertEqual(report["contacts"]["with_contact"], 0)


class TextRenderTest(unittest.TestCase):
    def test_renders_without_error(self) -> None:
        report = build_roi([verified()] * 3, {"name": "测试", "budget": 100,
                                              "cost_per_reveal": 2, "elapsed_minutes": 1})
        text = format_roi_text(report)
        self.assertIn("转化漏斗", text)
        self.assertIn("联系方式", text)
        self.assertIn("测试", text)

    def test_renders_empty_report(self) -> None:
        text = format_roi_text(build_roi([], {}))
        self.assertIn("转化漏斗", text)




class JevBreakdownTest(unittest.TestCase):
    def _jev(self, route="uncertain", conf=0.5, backend="jev-cloud", enabled=True):
        return json.dumps({
            "enabled": enabled, "advisory_only": True, "needs_review": True,
            "admission_changed": False, "auto_send_allowed": False,
            "route": route, "confidence": conf,
            "integration": {"backend": backend, "cloud_error": None},
        }, ensure_ascii=False)

    def test_empty(self) -> None:
        j = build_jev_breakdown([])
        self.assertEqual(j["enabled"], 0)
        self.assertEqual(j["coverage_rate"], "0.0")

    def test_no_jev_field(self) -> None:
        j = build_jev_breakdown([{"identity": "a"}])
        self.assertEqual(j["enabled"], 0)

    def test_counts_routes(self) -> None:
        rows = [
            {"Jev内容复核": self._jev("supported", 0.9)},
            {"Jev内容复核": self._jev("supported", 0.8)},
            {"Jev内容复核": self._jev("uncertain", 0.3)},
            {"Jev内容复核": self._jev("review_conflict", 0.7)},
        ]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["enabled"], 4)
        self.assertEqual(j["routes"]["supported"], 2)
        self.assertEqual(j["routes"]["uncertain"], 1)
        self.assertEqual(j["routes"]["review_conflict"], 1)
        self.assertEqual(j["supported_rate"], "50.0")
        self.assertEqual(j["conflict_rate"], "25.0")

    def test_accepts_dict_form(self) -> None:
        """Jev内容复核 也可能是 dict（非 JSON 字符串）。"""
        rows = [{"Jev内容复核": {"enabled": True, "route": "supported", "confidence": 0.9}}]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["enabled"], 1)
        self.assertEqual(j["routes"]["supported"], 1)

    def test_ignores_disabled_and_malformed(self) -> None:
        rows = [
            {"Jev内容复核": self._jev(enabled=False)},
            {"Jev内容复核": "not json"},
            {"Jev内容复核": ""},
            {"Jev内容复核": None},
        ]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["enabled"], 0)

    def test_confidence_stats(self) -> None:
        rows = [
            {"Jev内容复核": self._jev("uncertain", 0.2)},
            {"Jev内容复核": self._jev("uncertain", 0.6)},
            {"Jev内容复核": self._jev("uncertain", 0.4)},
        ]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["confidence"]["min"], 0.2)
        self.assertEqual(j["confidence"]["max"], 0.6)
        self.assertEqual(j["confidence"]["avg"], 0.4)

    def test_backend_breakdown(self) -> None:
        rows = [
            {"Jev内容复核": self._jev(backend="jev-cloud")},
            {"Jev内容复核": self._jev(backend="local")},
            {"Jev内容复核": self._jev(backend="jev-cloud")},
        ]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["backends"], {"jev-cloud": 2, "local": 1})

    def test_coverage_rate(self) -> None:
        rows = [{"Jev内容复核": self._jev()}, {"identity": "no-jev"}]
        j = build_jev_breakdown(rows)
        self.assertEqual(j["coverage_rate"], "50.0")

    def test_included_in_build_roi(self) -> None:
        report = build_roi([{"Jev内容复核": self._jev("supported")}], {})
        self.assertIn("jev", report)
        self.assertEqual(report["jev"]["enabled"], 1)

    def test_text_renders_jev_section(self) -> None:
        report = build_roi([{"Jev内容复核": self._jev("supported")}], {})
        text = format_roi_text(report)
        self.assertIn("JEV", text)


if __name__ == "__main__":
    unittest.main()
