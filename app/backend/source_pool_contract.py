from __future__ import annotations

import re
from typing import Any


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_only_pool_ready(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate a source-only replenishment pool before downstream browser work.

    Regular/legacy payloads retain their existing contract.  A source-only
    replenishment payload must be the collector's atomically completed pool,
    not a resumable checkpoint or a payload whose claimed count exceeds the
    rows actually present.
    """
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    if _compact(strategy.get("strategyPurpose")) != "replenishment-source-only":
        return True, "legacy_or_regular_source"

    candidates = [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
    try:
        declared_count = int(payload.get("candidate_count") or 0)
        target_count = int(payload.get("target_count") or 0)
    except (TypeError, ValueError):
        return False, "invalid_source_pool_counts"

    if _compact(payload.get("status")) != "ready":
        return False, "source_pool_status_not_ready"
    if payload.get("complete") is not True:
        return False, "source_pool_not_complete"
    if target_count <= 0:
        return False, "source_pool_target_missing"
    if declared_count < target_count:
        return False, "source_pool_declared_count_below_target"
    if len(candidates) < target_count:
        return False, "source_pool_rows_below_target"
    return True, "ready"
