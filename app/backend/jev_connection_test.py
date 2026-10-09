"""One bounded synthetic inference, invoked by the desktop model test button."""
import json
import re
import time
import urllib.error
from jev_local_client import decide


def run_test(call=decide):
    started = time.monotonic()
    result = {"ok": False, "scope": "single_synthetic_inference", "attemptLimit": 1}
    try:
        response = call({"state": {"connection_test_value": 1}, "questions": {
            "connection_test": {"type": "noul", "instructions": "Is connection_test_value equal to 1?"}
        }}, "aipr-pro", timeout=20, max_attempts=1)
        answer = response.get("answers", {}).get("connection_test", {})
        value = answer.get("noul")
        valid = answer.get("type") == "noul" and isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
        result["ok"] = valid and value >= 0.5
        result["message"] = "模型调用成功，合成样例判断通过" if result["ok"] else "接口返回成功，但样例结果未通过校验"
        model = response.get("model")
        if isinstance(model, str) and re.fullmatch(r"jev-[a-z0-9.-]{1,60}", model):
            result["model"] = model
        usage = response.get("usage") or {}
        result["usage"] = {k: v for k, v in usage.items() if k in ("input_tokens", "output_tokens") and isinstance(v, int) and not isinstance(v, bool) and v >= 0}
    except urllib.error.HTTPError as exc:
        result.update(httpStatus=exc.code, message=f"模型调用失败：HTTP {exc.code}，请检查账户、额度或权限")
    except Exception:
        # Never serialize exceptions: they may contain headers or credentials.
        result["message"] = "测试失败：请检查网络、配置及系统凭据解密权限"
    result["elapsedMs"] = round((time.monotonic() - started) * 1000)
    return result


if __name__ == "__main__":
    print(json.dumps(run_test(), ensure_ascii=False))
