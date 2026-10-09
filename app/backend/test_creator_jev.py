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
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "enabled-apps").write_text("aipr-pro\n")
                with mock.patch.object(jev_local_client, "ROOT", root):
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

    def test_observed_titles_replace_platform_profile_noise(self) -> None:
        with mock.patch.object(creator_jev, "decide", return_value={
            "answers": {"content_fit": {"choice": "supported", "confidence": .9}}
        }) as decide:
            creator_jev.review({**FULL_CREATOR, "recent_titles": ["保湿面霜使用体验"],
                                "recent_products": ["保湿面霜"]}, FULL_RULES, "aipr-pro")
        content = decide.call_args.args[0]["state"]["content"]
        self.assertEqual(content["recent_titles"], ["保湿面霜使用体验"])
        self.assertEqual(content["recent_products"], ["保湿面霜"])
        self.assertNotIn("profile_text", content)
        self.assertNotIn("content_evidence", content)

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

    def test_http_status_is_preserved_without_response_body_or_credentials(self):
        import urllib.error
        for code in (402, 429, 503):
            with mock.patch.object(creator_jev, 'decide', side_effect=urllib.error.HTTPError(
                    'https://api.typesafe.ai/v1/systemone', code, 'private-server-message', {}, None)):
                result = creator_jev.review(FULL_CREATOR, FULL_RULES, 'aipr-pro')
            self.assertEqual(result['http_status'], code)
            self.assertEqual(result['action_required'], code == 402)
            self.assertEqual(result['retryable'], code != 402)
            self.assertEqual(result['route'], 'uncertain')
            self.assertNotIn('private-server-message', json.dumps(result))

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

    def test_large_audit_keeps_earlier_judgments_after_256_rows(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": .9}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok) as request:
            for i in range(300):
                creator_jev.review({**FULL_CREATOR, "douyin_content_text": f"护肤作品{i}"}, FULL_RULES, "aipr-pro")
            creator_jev.review({**FULL_CREATOR, "douyin_content_text": "护肤作品0"}, FULL_RULES, "aipr-pro")
        self.assertEqual(request.call_count, 300)

    def test_cache_reuses_unchanged_evidence_during_long_audit(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": .9}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok) as request, mock.patch.object(creator_jev.time, "monotonic", return_value=100):
            creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        with mock.patch.object(creator_jev, "decide", return_value=ok) as second, mock.patch.object(creator_jev.time, "monotonic", return_value=800):
            creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(second.call_count, 0)

    def test_persisted_judgment_survives_process_cache_reset(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": .9}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok) as request:
            first = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
            creator_jev._cache.clear()
            second = creator_jev.review({**FULL_CREATOR, "jev_analysis": first}, FULL_RULES, "aipr-pro")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(second["route"], "supported")
        self.assertFalse(second["auto_send_allowed"])

    def test_discovery_category_change_reuses_same_content_policy_but_real_requirement_change_does_not(self):
        ok = {"answers":{"content_fit":{"choice":"supported","confidence":.9}}}
        with mock.patch.object(creator_jev,"decide",return_value=ok) as call:
            first=creator_jev.review(FULL_CREATOR,FULL_RULES,"aipr-pro")
            creator_jev._cache.clear()
            row={**FULL_CREATOR,"jev_analysis":first}
            switched={**FULL_RULES,"category":"个护家清","contentFitCategory":"美妆个护"}
            result=creator_jev.review(row,switched,"aipr-pro")
            self.assertEqual(call.call_count,1)
            self.assertEqual(result["route"],"supported")
            creator_jev.review(row,{**switched,"brief":"仅接受具体唇妆作品"},"aipr-pro")
            self.assertEqual(call.call_count,2)

    def test_platform_video_alias_reuses_saved_judgment_without_paid_call(self):
        ok = {"answers":{"content_fit":{"choice":"supported","confidence":.9}}}
        original={**FULL_RULES,"contentType":"短视频"}
        with mock.patch.object(creator_jev,"decide",return_value=ok) as call:
            first=creator_jev.review(FULL_CREATOR,original,"aipr-pro")
            creator_jev._cache.clear()
            with mock.patch.dict(os.environ, {"AIPR_JEV_SAVED_ONLY":"1"}):
                result=creator_jev.review({**FULL_CREATOR,"jev_analysis":first},
                    {**original,"contentType":"视频达人"},"aipr-pro")
            self.assertEqual(call.call_count,1)
            self.assertEqual(result["route"],"supported")
            self.assertFalse(result["auto_send_allowed"])

    def test_changed_evidence_rules_or_policy_requires_new_judgment(self) -> None:
        ok = {"answers": {"content_fit": {"choice": "supported", "confidence": .9}}}
        with mock.patch.object(creator_jev, "decide", return_value=ok) as request:
            first = creator_jev.review(FULL_CREATOR, FULL_RULES, "aipr-pro")
            row = {**FULL_CREATOR, "jev_analysis": first}
            creator_jev.review({**row, "douyin_content_text": "运动训练"}, FULL_RULES, "aipr-pro")
            creator_jev.review(row, {**FULL_RULES, "brief": "仅接受唇部测评"}, "aipr-pro")
            with mock.patch.object(creator_jev, "settings", return_value={"confidence_threshold": .99}):
                result = creator_jev.review(row, FULL_RULES, "aipr-pro")
        self.assertEqual(request.call_count, 4)
        self.assertEqual(result["route"], "uncertain")


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

class PresentationEvidenceTest(unittest.TestCase):
    def test_titles_or_avatar_do_not_prove_real_person(self):
        with mock.patch.object(creator_jev, 'enabled', return_value=True), mock.patch.object(creator_jev, 'decide') as call:
            result = creator_jev.review({'recent_titles':['真人试用唇蜜'], 'bio':'真人测评'}, {'category':'美妆个护','contentPresentation':'real_person'}, 'aipr-pro')
            self.assertEqual(result['route'], 'uncertain')
            self.assertIn('出镜方式证据', result['reason'])
            call.assert_not_called()

class LegacyPresentationCompatibilityTest(unittest.TestCase):
    def test_unlimited_new_fields_preserve_old_judgment(self):
        response={'answers':{'content_fit':{'choice':'supported','confidence':0.9}}}
        creator_jev._cache.clear()
        with mock.patch.object(creator_jev,'enabled',return_value=True), mock.patch.object(creator_jev,'settings',return_value={}), mock.patch.object(creator_jev,'decide',return_value=response) as call:
            creator={'recent_titles':['保湿护肤日常分享']}
            rules={'category':'美妆个护'}
            first=creator_jev.review(creator,rules,'compatibility-test')
            self.assertEqual(first['judgment_version'],'content-fit-2026-10-02-v1')
            creator_jev._cache.clear()
            second=creator_jev.review({**creator,'jev_analysis':first},{**rules,'creatorType':'不限内容类型','contentPresentation':'any'},'compatibility-test')
            self.assertEqual(second['evidence_sha256'],first['evidence_sha256'])
            self.assertEqual(call.call_count,1)
