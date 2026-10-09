"""Small vendorable client; all credentials and switches remain outside application code."""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import time
import sys
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT = Path(os.environ.get("JEV_CONFIG_DIR") or Path.home() / ".config/jev-integration")


def settings(app):
    path = ROOT / (app + ".json")
    try:
        loaded = json.loads(path.read_text()) if path.exists() else {}
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}


def decision_enabled(app):
    return enabled(app) and settings(app).get("decision_mode") is True


def enabled(app):
    if os.environ.get("JEV_INTEGRATION") == "0":
        return False
    path = ROOT / "enabled-apps"
    try:
        return path.exists() and app in path.read_text().splitlines()
    except OSError:
        return False


def decide(payload, app, timeout=25, allow_fallback=True, local_only=False, max_attempts=3):
    if not enabled(app):
        raise RuntimeError("jev_integration_disabled")
    config = settings(app)
    cloud = config.get("backend") == "cloud" and not local_only
    token = (os.environ.get("AIPR_JEV_API_KEY") or config.get("api_key", "")) if cloud else (ROOT / "token").read_text().strip()
    if not token:
        raise RuntimeError("jev_missing_api_key")
    payload = dict(payload)
    if cloud:
        payload["model"] = config.get("model") or "jev-latest"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token,
               "X-Jev-App": app, "X-Jev-Allow-Fallback": "1" if allow_fallback else "0"}
    if local_only:
        headers["X-Jev-Backend"] = "local"
    endpoint = "https://api.typesafe.ai/v1/systemone" if cloud else "http://127.0.0.1:8771/v1/systemone"
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    started = time.monotonic()
    attempts = max(1, min(3, int(max_attempts)))
    for attempt in range(attempts):
        attempt_started = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                result = json.load(response)
            if cloud:
                record_usage(app, result, attempt=attempt+1, elapsed_ms=round((time.monotonic()-attempt_started)*1000), model=payload.get("model"))
                result["integration"] = {"backend": "jev-cloud", "elapsed_ms": round((time.monotonic()-started)*1000), "abstentions": []}
            return result
        except urllib.error.HTTPError as exc:
            if cloud:
                record_usage(app, {}, outcome="http_error", http_status=exc.code, attempt=attempt+1, elapsed_ms=round((time.monotonic()-attempt_started)*1000), model=payload.get("model"))
            if not (exc.code in (408, 429) or 500 <= exc.code < 600) or attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            retry_after = exc.headers.get('Retry-After') if exc.headers else None
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(delay, parsedate_to_datetime(retry_after).timestamp() - time.time())
                    except (ValueError, TypeError, OverflowError):
                        pass
            time.sleep(delay)
        except (OSError, ValueError) as exc:
            if cloud:
                record_usage(app, {}, outcome="invalid_response" if isinstance(exc, ValueError) else "network_error", attempt=attempt+1, elapsed_ms=round((time.monotonic()-attempt_started)*1000), model=payload.get("model"))
            raise
    raise RuntimeError("jev_request_failed")


def review_route(response, question, default="uncertain"):
    metadata = response.get("integration") or {}
    for abstention in metadata.get("abstentions", []):
        if abstention.get("question") == question:
            return abstention.get("suggested_route", default)
    return None


def record_usage(app, response, *, outcome="success", http_status=None, attempt=1, elapsed_ms=None, model=None):
    # Never persist credentials, prompts, creator identities or exception bodies.
    if app != "aipr-pro":
        return
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    safe_usage = {key: value for key, value in usage.items()
                  if key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens", "cached_tokens")
                  and isinstance(value, int) and not isinstance(value, bool) and value >= 0}
    task = os.environ.get("AIPR_TASK_ID", "")
    task = task if re.fullmatch(r"[a-zA-Z0-9_-]{1,120}", task) else ""
    safe_model = response.get("model") or model
    safe_model = safe_model if isinstance(safe_model, str) and re.fullmatch(r"jev-[a-z0-9.-]{1,60}", safe_model) else None
    record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "app": app,
              "task_id": task, "model": safe_model, "usage": safe_usage,
              "usage_available": bool(safe_usage), "billed_amount": None,
              "outcome": outcome if outcome in ("success", "http_error", "network_error", "invalid_response") else "unknown",
              "http_status": http_status if isinstance(http_status, int) and 100 <= http_status <= 599 else None,
              "attempt": attempt if isinstance(attempt, int) and 1 <= attempt <= 3 else 1,
              "elapsed_ms": elapsed_ms if isinstance(elapsed_ms, int) and elapsed_ms >= 0 else None}
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with (ROOT / "usage-ledger.ndjson").open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(record, ensure_ascii=False) + "\n")
        # A durable latest outcome survives history truncation and application restarts.
        status_path = ROOT / "account-status.json"
        temp = status_path.with_suffix(".tmp")
        temp.write_text(json.dumps({key: record[key] for key in ("recorded_at", "outcome", "http_status", "model")}), encoding="utf-8")
        temp.replace(status_path)
        (ROOT / "usage-ledger-error.json").unlink(missing_ok=True)
    except OSError:
        # Do not retry a billed request because local bookkeeping failed.
        try:
            (ROOT / "usage-ledger-error.json").write_text(json.dumps({"recorded_at":record["recorded_at"],"error":"local_usage_write_failed"}), encoding="utf-8")
        except OSError:
            pass
        print("jev_usage_record_failed: 本机用量记录无法写入，云端调用结果已保留，不重试付费请求", file=sys.stderr)
