"""从候选数据中提取 JEV 所需的近期作品标题

背景：JEV 的判定质量依赖 `recent_titles`，但候选数据里该字段为空，
导致大量 uncertain（实测 82.5%）。

实际内容藏在 `content_evidence` 里，包含两类：
  1. 达人作品标题（含话题标签、口语化表达）
  2. 带货商品名（品牌 + 规格 + 功效词）

两者对内容匹配复核都有价值，但需要分开标注，避免模型误判。

用法：
    from jev_evidence import enrich_for_jev
    enriched = enrich_for_jev(candidate)
    # enriched["recent_titles"] / enriched["recent_sample_size"] 已填充
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 明显不是作品标题的行（平台字段、店铺名、状态词）
NOISE_PREFIXES = (
    "平台", "达人简介", "关联企业", "签约机构", "达人抖音主页",
    "带货评价", "评价分", "带货效果", "合作履约", "沟通态度",
)

NOISE_EXACT = {
    "带货效果最好", "详情", "-", "暂无关联企业", "暂无",
    "在线沟通", "添加达人库", "高", "中", "低",
}

# 商品名特征：含规格/型号/功效词
PRODUCT_HINTS = re.compile(
    r"(旗舰店|专营店|官方|正品|\d+\s*(ml|g|片|抽|支|瓶|袋|盒|件|套))"
    r"|(特惠|活动|优惠|包邮|DB\s*\w+)"
)

# 作品标题特征：话题标签、感叹、口语化
TITLE_HINTS = re.compile(r"[#＃][^\s#]+|[！!]{1,}|[？?]$|～|~")


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def classify_line(line: str) -> str:
    """把一行内容分类为 title / product / noise。"""
    text = _compact(line)
    if not text or text in NOISE_EXACT:
        return "noise"
    if any(text.startswith(p) for p in NOISE_PREFIXES):
        return "noise"
    if len(text) < 8:
        return "noise"
    # 商品名通常没有话题标签
    has_tag = bool(TITLE_HINTS.search(text))
    looks_product = bool(PRODUCT_HINTS.search(text)) and not has_tag
    if looks_product:
        return "product"
    if has_tag or len(text) >= 20:
        return "title"
    return "noise"


def extract_titles(evidence: Iterable[Any], limit: int = 12) -> list[str]:
    """从 content_evidence 提取作品标题。"""
    out: list[str] = []
    for item in evidence or []:
        if classify_line(str(item)) == "title":
            text = _compact(item)
            if text not in out:
                out.append(text)
        if len(out) >= limit:
            break
    return out


def extract_products(evidence: Iterable[Any], limit: int = 8) -> list[str]:
    """从 content_evidence 提取带货商品名。"""
    out: list[str] = []
    for item in evidence or []:
        if classify_line(str(item)) == "product":
            text = _compact(item)
            if text not in out:
                out.append(text)
        if len(out) >= limit:
            break
    return out


def extract_bio(profile_text: str) -> str:
    """从 profile_text 提取「达人简介：」后的内容。"""
    text = _compact(profile_text)
    match = re.search(r"达人简介[:：]\s*(.+?)(?:\s*(?:关联企业|签约机构|其他信息|带货评价|$))", text)
    if match:
        return match.group(1).strip()[:500]
    return ""


def enrich_for_jev(candidate: dict[str, Any]) -> dict[str, Any]:
    """为 JEV 调用补齐证据字段（不修改原候选）。

    只填空缺字段，已有值不覆盖。
    """
    out = dict(candidate)

    evidence = candidate.get("content_evidence") or []
    titles = extract_titles(evidence)
    products = extract_products(evidence)

    if not out.get("recent_titles") and titles:
        out["recent_titles"] = titles
    if not out.get("recent_sample_size"):
        out["recent_sample_size"] = len(titles)

    # bio / signature 从 profile_text 提取
    if not out.get("bio"):
        bio = extract_bio(str(candidate.get("profile_text") or ""))
        if bio:
            out["bio"] = bio

    # 商品名放进 content_evidence 的补充字段（JEV 会读 content_evidence）
    if products and not out.get("recent_products"):
        out["recent_products"] = products

    return out


def enrich_many(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_for_jev(c) for c in candidates if isinstance(c, dict)]


def summarize_enrichment(original: Iterable[dict[str, Any]], enriched: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """对比补齐前后的字段填充率（供验证用）。"""
    orig = [c for c in original if isinstance(c, dict)]
    enr = [c for c in enriched if isinstance(c, dict)]
    n = min(len(orig), len(enr))
    if n == 0:
        return {"count": 0}

    def filled(rows: list[dict[str, Any]], key: str) -> int:
        return sum(1 for r in rows if r.get(key))

    return {
        "count": n,
        "before": {
            "recent_titles": filled(orig[:n], "recent_titles"),
            "bio": filled(orig[:n], "bio"),
            "recent_sample_size": filled(orig[:n], "recent_sample_size"),
        },
        "after": {
            "recent_titles": filled(enr[:n], "recent_titles"),
            "bio": filled(enr[:n], "bio"),
            "recent_sample_size": filled(enr[:n], "recent_sample_size"),
        },
    }
