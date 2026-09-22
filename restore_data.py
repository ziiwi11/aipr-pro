#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


KIT_DIR = Path(__file__).resolve().parent
PAYLOAD_DIR = KIT_DIR / "migration-data"
USER_DATA = Path.home() / "Library" / "Application Support" / "AIPR Pro 达人运营系统"
PATH_KEYS = {
    "outputDir",
    "deliveryPath",
    "queuePath",
    "originalWorkbookPath",
    "strategyPath",
    "robotQueuePath",
    "lastContactPath",
    "lastDeliveryPath",
}


def convert_windows_path(value: str, home: Path | None = None) -> str:
    if not value:
        return value
    normalized = value.replace("\\", "/")
    match = re.match(r"^[A-Za-z]:/Users/[^/]+/Documents(?:/(.*))?$", normalized)
    if match:
        suffix = match.group(1) or ""
        return str((home or Path.home()) / "Documents" / suffix)
    return value


def rewrite_paths(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {item_key: rewrite_paths(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [rewrite_paths(item, key) for item in value]
    if isinstance(value, str) and (key in PATH_KEYS or re.match(r"^[A-Za-z]:\\", value)):
        return convert_windows_path(value)
    return value


def backup_existing() -> Path | None:
    existing = [USER_DATA / "tasks", USER_DATA / "integrations"]
    if not any(path.exists() for path in existing):
        return None
    backup = USER_DATA / "migration-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=True)
    for path in existing:
        if path.exists():
            shutil.copytree(path, backup / path.name, dirs_exist_ok=True)
    return backup


def restore_json_tree(source: Path, destination: Path) -> int:
    if not source.exists():
        return 0
    count = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            target.write_text(json.dumps(rewrite_paths(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            shutil.copy2(path, target)
        count += 1
    return count


def main() -> int:
    USER_DATA.mkdir(parents=True, exist_ok=True)
    backup = backup_existing()
    restored = 0
    restored += restore_json_tree(PAYLOAD_DIR / "tasks", USER_DATA / "tasks")
    restored += restore_json_tree(PAYLOAD_DIR / "integrations", USER_DATA / "integrations")
    print(f"已恢复 {restored} 个数据文件。")
    if backup:
        print(f"原数据备份：{backup}")
    print("浏览器登录目录未迁移；请在 Mac 中重新登录两个抖店账号。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
