"""Small vendorable client; all credentials and switches remain outside application code."""
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path.home() / ".config/jev-integration"


def enabled(app):
    if os.environ.get("JEV_INTEGRATION") == "0":
        return False
    path = ROOT / "enabled-apps"
    return path.exists() and app in path.read_text().splitlines()


def decide(payload, app, timeout=25, allow_fallback=True, local_only=False):
    if not enabled(app):
        raise RuntimeError("jev_integration_disabled")
    token = (ROOT / "token").read_text().strip()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token,
               "X-Jev-App": app, "X-Jev-Allow-Fallback": "1" if allow_fallback else "0"}
    if local_only:
        headers["X-Jev-Backend"] = "local"
    request = urllib.request.Request("http://127.0.0.1:8771/v1/systemone", data=json.dumps(payload).encode(), headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        return json.load(response)


def review_route(response, question, default="uncertain"):
    metadata = response.get("integration") or {}
    for abstention in metadata.get("abstentions", []):
        if abstention.get("question") == question:
            return abstention.get("suggested_route", default)
    return None
