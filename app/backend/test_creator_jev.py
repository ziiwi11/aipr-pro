"""JEV 内容复核集成测试

覆盖：
- enabled 判定的三条路径（环境变量禁用 / 白名单未列 / 正常）
- review 在禁用时返回 {enabled: False} 且不抛错
- review 缺少内容或规则时返回 uncertain
- review 在服务不可用时降级（不抛错、保留原审核）
- advisory 字段不改变准入（admission_changed / auto_send_allowed 恒为 False）
- review_route 的解析逻辑
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creator_jev  # noqa: E402
import jev_local_client  # noqa: E402


FULL_CREATOR = {
    "profile_text": "专注护肤好物分享",
    "douyin_content_text": "秋冬面霜测评",
    "content_evidence": ["面霜测评", "真实上脸"],
    "content_evidence_reviewed": True,
    "category": "美妆/个护家清",
}

FULL_RULES = {
    "name": "宫草集萃七子霜",
    "product_name": "七子霜",
    "brief": "达人需真人出镜口播30-60秒",
    "category": "美妆个护",
}


class EnabledTest(unittest.TestCase):
    def test_env_var_zero_disables(self) -> None:
        with mock.patch.dict(os.environ, {"JEV_INTEGRATION": "0"}):
            self.assertFalse(jev_local_client.enabled("aipr-pro"))

    def test_unknown_app_not_enabled(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JEV_INTEGRATION", None)
            self.assertFalse(jev_local_client.enabled("definitely-not-an-app"))

    def test_whitelisted_app_enabled(self) -> None:
        """若配置目录存在且包含该 app，则启用。"""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JEV_INTEGRATION", None)
            root = jev_local_client.ROOT
            if not (root / "enabled-apps").exists():
                self.skipTest("本机未配置 JEV（enabled-apps 不存在）")
            apps = (root / "enabled-apps").read_text().splitlines()
            if "aipr-pro" not in apps:
                self.skipTest("aipr-pro 不在白名单")
            self.assertTrue(jev_local_client.enabled("aipr-pro"))


class ReviewDisabledTest(unittest.TestCase):
    def test_review_returns_disabled_without_raising(self) -> None:
        with mock.patch.dict(os.environ, {"JEV_INTEGRATION": "0"}):
            result = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(result, {"enabled": False})

    def test_decide_raises_when_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"JEV_INTEGRATION": "0"}):
            with self.assertRaises(RuntimeError):
                jev_local_client.decide({"state": {}, "questions": {}}, "aipr-pro")


class ReviewMissingInputTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(creator_jev, "enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        creator_jev._cache.clear()

    def test_missing_content_returns_uncertain(self) -> None:
        result = creator_jev.review({}, FULL_RULES, "aipr-pro")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["route"], "uncertain")
        self.assertFalse(result["admission_changed"])

    def test_missing_rules_returns_uncertain(self) -> None:
        result = creator_jev.review(FULL_CREATOR, {}, "aipr-pro")
        self.assertEqual(result["route"], "uncertain")

    def test_advisory_flags_always_safe(self) -> None:
        """无论输入如何，advisory 三标志必须保持安全值。"""
        for creator, rules in (({}, {}), (FULL_CREATOR, {}), ({}, FULL_RULES)):
            r = creator_jev.review(creator, rules, "aipr-pro")
            self.assertTrue(r["advisory_only"])
            self.assertFalse(r["admission_changed"])
            self.assertFalse(r["auto_send_allowed"])


class ReviewServiceFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(creator_jev, "enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        creator_jev._cache.clear()

    def test_service_unavailable_degrades_gracefully(self) -> None:
        with mock.patch.object(
            creator_jev, "decide", side_effect=OSError("connection refused")
        ):
            result = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["route"], "uncertain")
        self.assertIn("不可用", result.get("reason", ""))
        self.assertFalse(result["admission_changed"])

    def test_invalid_route_degrades_gracefully(self) -> None:
        bad = {"answers": {"content_fit": {"choice": "not-a-valid-route", "confidence": 0.9}}}
        with mock.patch.object(creator_jev, "decide", return_value=bad):
            result = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(result["route"], "uncertain")

    def test_low_confidence_becomes_uncertain(self) -> None:
        low = {"answers": {"content_fit": {"choice": "supported", "confidence": 0.3}}}
        with mock.patch.object(creator_jev, "decide", return_value=low):
            result = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(result["route"], "uncertain")


class ReviewSuccessTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(creator_jev, "enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        creator_jev._cache.clear()

    def test_supported_route_passes_through(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": 0.88}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok):
            result = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(result["route"], "supported")
        self.assertAlmostEqual(result["confidence"], 0.88)
        self.assertFalse(result["admission_changed"])

    def test_result_is_cached(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": 0.9}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok) as m:
            creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
            creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(m.call_count, 1, "第二次应命中缓存")


class ReviewRouteTest(unittest.TestCase):
    def test_returns_suggested_route(self) -> None:
        resp = {"integration": {"abstentions": [
            {"question": "content_fit", "suggested_route": "review_conflict"}
        ]}}
        self.assertEqual(
            jev_local_client.review_route(resp, "content_fit"), "review_conflict"
        )

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(jev_local_client.review_route({}, "content_fit"))
        self.assertIsNone(
            jev_local_client.review_route({"integration": {"abstentions": []}}, "content_fit")
        )


class PayloadShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(creator_jev, "enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        creator_jev._cache.clear()

    def test_payload_contains_only_allowed_fields(self) -> None:
        captured = {}

        def fake_decide(payload, app, **kwargs):
            captured["payload"] = payload
            return {"answers": {"content_fit": {"choice": "uncertain", "confidence": 0.1}}}

        with mock.patch.object(creator_jev, "decide", side_effect=fake_decide):
            creator_jev.review(
                {**FULL_CREATOR, "buyin_contact_phone": "13800138000", "fans": 99999},
                FULL_RULES,
                "aipr-pro",
            )

        content = captured["payload"]["state"]["content"]
        # 联系方式与粉丝数不得进入 JEV 请求
        self.assertNotIn("buyin_contact_phone", content)
        self.assertNotIn("fans", content)
        self.assertIn("profile_text", content)


if __name__ == "__main__":
    unittest.main()
