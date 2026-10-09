"""Apply software-recorded manual contact revisions to a new delivery only."""
import json
from pathlib import Path

def read_corrections(filename, task_id):
    if not filename or not Path(filename).exists():
        return []
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if data.get("schema") != "qianxun-contact-corrections-v1" or data.get("taskId") != task_id or not isinstance(data.get("records"), list):
        raise ValueError("contact_corrections_task_or_schema_invalid")
    return data["records"]

def apply_corrections(rows, records):
    latest = {str(r["creatorId"]): r for r in records}
    result = []
    for row in rows:
        record = latest.get(str(row.get("identity") or row.get("主页身份ID") or row.get("buyin_uid") or row.get("douyin_id") or row.get("id") or ""))
        current = dict(row)
        if record:
            after = record["after"]
            for channel, chinese in (("wechat", "微信"), ("phone", "手机号"), ("email", "邮箱")):
                for key in ("buyin_contact_"+channel, "cart_contact_"+channel, channel, chinese):
                    current[key] = str(after.get(channel) or "").strip()
            plain = current["wechat"] or current["phone"] or current["email"]
            if not plain:
                raise ValueError("contact_correction_requires_plaintext")
            for key in ("plain_contact", "contact", "联系方式", "明文联系方式"):
                current[key] = plain
            current["buyin_contact_source"] = record["source"]
            current["contact_corrected_at"] = record["recordedAt"]
            current["contact_correction_revision"] = record["revision"]
        result.append(current)
    return result
