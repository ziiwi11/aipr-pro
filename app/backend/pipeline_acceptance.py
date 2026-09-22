from __future__ import annotations

import re


def validate_candidate_count(actual: int, target: int) -> int:
    actual_count = max(0, int(actual or 0))
    target_count = max(1, int(target or 1))
    if actual_count < target_count:
        raise ValueError(f"candidate_count_below_target:{actual_count}/{target_count}")
    return actual_count


def allocate_shop_targets(total: int, shops: int) -> list[int]:
    total_count = max(0, int(total or 0))
    shop_count = max(1, int(shops or 1))
    base, remainder = divmod(total_count, shop_count)
    return [base + (1 if index < remainder else 0) for index in range(shop_count)]


def source_pool_target(target: int, require_contact: bool) -> int:
    target_count = max(1, int(target or 1))
    return min(5000, target_count * 3 if require_contact else target_count)


def remaining_shop_target(total: int, other_shop_count: int) -> int:
    return max(0, int(total or 0) - max(0, int(other_shop_count or 0)))


def creator_name_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()
