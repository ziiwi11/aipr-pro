"""ROI 转化看板

参照 InfluenceX 的 server/roi-dashboard.js（MIT），适配 AIPR Pro 的达人采集链路。

漏斗设计（包含式，保证单调递减）：
    候选达人 → 已验证 → 已揭示联系方式 → 已交付

每个阶段包含下一个：已交付的达人必然也算已验证、候选。

用法：
    from roi_dashboard import build_roi
    report = build_roi(candidates, task_meta={...})
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rate(numerator: int, denominator: int) -> str:
    """百分比字符串，保留一位小数（与 InfluenceX 一致）。"""
    if denominator <= 0:
        return "0.0"
    return f"{numerator / denominator * 100:.1f}"


def _has_contact(row: dict[str, Any]) -> bool:
    values = [row.get(key) for key in ("buyin_contact_phone", "buyin_contact_wechat", "cart_contact_phone", "cart_contact_wechat", "buyin_contact_email", "cart_contact_email", "phone", "wechat", "email", "手机号", "微信", "邮箱")]
    return any(str(value or "").strip() and not any(marker in str(value) for marker in ("*", "•", "隐藏", "未授权", "待获取", "待补", "暂无", "不可见")) for value in values)


def _is_verified(row: dict[str, Any]) -> bool:
    return row.get("content_evidence_reviewed") is True


def _is_qualified(row: dict[str, Any]) -> bool:
    return row.get("precontact_qualified") is True


def _is_delivered(row: dict[str, Any]) -> bool:
    """已进入交付名单（有推荐结论且非淘汰）。"""
    if "_delivered" in row:
        return row["_delivered"] is True
    decision = str(row.get("推荐结论") or row.get("decision") or "")
    if decision:
        return "推荐" in decision
    return bool(row.get("delivered") or row.get("_delivered"))


def build_funnel(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """构建包含式漏斗。

    每个阶段包含下一个，保证单调递减，便于前端绘制漏斗图。
    """
    items = [r for r in rows if isinstance(r, dict)]
    total = len(items)

    verified = sum(1 for r in items if _is_verified(r))
    qualified = sum(1 for r in items if _is_verified(r) and _is_qualified(r))
    revealed = sum(1 for r in items if _is_verified(r) and _has_contact(r))
    delivered = sum(1 for r in items if _is_verified(r) and _has_contact(r) and _is_delivered(r))

    return {
        "candidates": total,
        "verified": verified,
        "qualified": qualified,
        "revealed": revealed,
        "delivered": delivered,
        "rates": {
            "verify_rate": _rate(verified, total),
            "qualify_rate": _rate(qualified, verified),
            "reveal_rate": _rate(revealed, qualified),
            "deliver_rate": _rate(delivered, revealed),
            "end_to_end_rate": _rate(delivered, total),
        },
    }


def build_contact_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = [r for r in rows if isinstance(r, dict)]
    phone = sum(1 for r in items if r.get("buyin_contact_phone") or r.get("cart_contact_phone"))
    wechat = sum(1 for r in items if r.get("buyin_contact_wechat") or r.get("cart_contact_wechat"))
    email = sum(1 for r in items if r.get("buyin_contact_email"))
    any_contact = sum(1 for r in items if _has_contact(r))
    only_phone = sum(
        1 for r in items
        if (r.get("buyin_contact_phone") or r.get("cart_contact_phone"))
        and not (r.get("buyin_contact_wechat") or r.get("cart_contact_wechat"))
    )
    only_wechat = sum(
        1 for r in items
        if (r.get("buyin_contact_wechat") or r.get("cart_contact_wechat"))
        and not (r.get("buyin_contact_phone") or r.get("cart_contact_phone"))
    )
    both = sum(
        1 for r in items
        if (r.get("buyin_contact_phone") or r.get("cart_contact_phone"))
        and (r.get("buyin_contact_wechat") or r.get("cart_contact_wechat"))
    )
    return {
        "with_contact": any_contact,
        "phone": phone,
        "wechat": wechat,
        "email": email,
        "only_phone": only_phone,
        "only_wechat": only_wechat,
        "both_phone_and_wechat": both,
        "contact_rate": _rate(any_contact, len(items)),
    }


def build_level_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        level = str(r.get("talent_level") or r.get("达人等级") or "").strip()
        if not level:
            continue
        out[level] = out.get(level, 0) + 1
    return dict(sorted(out.items()))


def build_category_breakdown(rows: Iterable[dict[str, Any]], limit: int = 10) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw = str(r.get("category") or "")
        if not raw:
            continue
        head = raw.split("/")[0].strip()
        if head:
            counts[head] = counts.get(head, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return dict(ordered)


def build_risk_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """统计风控相关状态（用于评估稳定性）。"""
    markers = ("请求过于频繁", "稍后再试", "访问频繁", "安全验证", "次数已达上限")
    out = {"rate_limited": 0, "not_revealed": 0, "failed": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        blob = json.dumps(r, ensure_ascii=False)
        if any(m in blob for m in markers):
            out["rate_limited"] += 1
        status = str(r.get("ui_contact_probe_status") or "")
        if status == "clicked_not_revealed":
            out["not_revealed"] += 1
        if status in ("exception", "timeout"):
            out["failed"] += 1
    return out


def _parse_jev(raw: Any) -> dict[str, Any] | None:
    """解析交付行里的 Jev内容复核（可能是 JSON 字符串或 dict）。"""
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def build_jev_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """统计 JEV 内容复核的结论分布。

    route 三种取值：
      supported       — 作品证据支持当前项目内容方向
      review_conflict — 作品与项目要求有明确冲突证据
      uncertain       — 证据不足或无法确认（默认与降级值）

    注意：这是 advisory 数据，不代表准入结论。
    """
    items = [r for r in rows if isinstance(r, dict)]
    total = len(items)
    enabled = 0
    routes: dict[str, int] = {}
    confidences: list[float] = []
    backends: dict[str, int] = {}
    cloud_errors = 0

    for row in items:
        jev = _parse_jev(row.get("Jev内容复核") or row.get("jev_analysis"))
        if not jev or not jev.get("enabled"):
            continue
        enabled += 1
        route = str(jev.get("route") or "unknown")
        routes[route] = routes.get(route, 0) + 1
        conf = jev.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(float(conf))
        integration = jev.get("integration")
        if isinstance(integration, dict):
            backend = str(integration.get("backend") or "unknown")
            backends[backend] = backends.get(backend, 0) + 1
            if integration.get("cloud_error"):
                cloud_errors += 1

    def rate(n: int, d: int) -> str:
        return f"{n / d * 100:.1f}" if d > 0 else "0.0"

    return {
        "enabled": enabled,
        "coverage_rate": rate(enabled, total),
        "routes": routes,
        "supported_rate": rate(routes.get("supported", 0), enabled),
        "conflict_rate": rate(routes.get("review_conflict", 0), enabled),
        "uncertain_rate": rate(routes.get("uncertain", 0), enabled),
        "confidence": {
            "count": len(confidences),
            "min": round(min(confidences), 2) if confidences else None,
            "max": round(max(confidences), 2) if confidences else None,
            "avg": round(sum(confidences) / len(confidences), 2) if confidences else None,
        },
        "backends": backends,
        "cloud_errors": cloud_errors,
    }


def build_roi(
    rows: Iterable[dict[str, Any]],
    task_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成完整 ROI 报告。

    task_meta 可选字段：
      - name / id：任务标识
      - budget：预算（用于成本估算）
      - cost_per_reveal：单次联系方式揭示的估算成本
      - elapsed_minutes：本次运行耗时（用于速率）
    """
    items = [r for r in rows if isinstance(r, dict)]
    meta = dict(task_meta or {})
    funnel = build_funnel(items)
    contacts = build_contact_breakdown(items)

    budget = float(meta.get("budget") or 0)
    cost_per_reveal = float(meta.get("cost_per_reveal") or 0)
    revealed = funnel["revealed"]
    delivered = funnel["delivered"]

    spent = cost_per_reveal * revealed if cost_per_reveal else 0.0
    elapsed = float(meta.get("elapsed_minutes") or 0)

    roi = {
        "budget": budget,
        "estimated_spent": round(spent, 2),
        "budget_remaining": round(max(0.0, budget - spent), 2) if budget else None,
        "budget_utilization": f"{(spent / budget * 100):.1f}" if budget > 0 else None,
        "cost_per_revealed_contact": round(spent / revealed, 2) if revealed and spent else None,
        "cost_per_delivered": round(spent / delivered, 2) if delivered and spent else None,
    }

    throughput = None
    if elapsed > 0:
        throughput = {
            "elapsed_minutes": round(elapsed, 1),
            "reveals_per_minute": round(revealed / elapsed, 2) if revealed else 0.0,
            "seconds_per_reveal": round(elapsed * 60 / revealed, 1) if revealed else None,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": {
            "id": meta.get("id") or "",
            "name": meta.get("name") or "",
        },
        "funnel": funnel,
        "contacts": contacts,
        "levels": build_level_breakdown(items),
        "categories": build_category_breakdown(items),
        "risk": build_risk_breakdown(items),
        "jev": build_jev_breakdown(items),
        "roi": roi,
        "throughput": throughput,
    }


def format_roi_text(report: dict[str, Any]) -> str:
    """渲染为可读文本（供 CLI 输出）。"""
    f = report["funnel"]
    c = report["contacts"]
    r = report["roi"]
    lines = [
        f"ROI 报告 · {report['task'].get('name') or '(未命名任务)'}",
        f"生成时间：{report['generated_at']}",
        "",
        "【转化漏斗】",
        f"  候选达人      {f['candidates']:>6}",
        f"  已验证        {f['verified']:>6}   {f['rates']['verify_rate']}%",
        f"  预接触合格    {f['qualified']:>6}   {f['rates']['qualify_rate']}%",
        f"  已揭示联系方式 {f['revealed']:>6}   {f['rates']['reveal_rate']}%",
        f"  已交付        {f['delivered']:>6}   {f['rates']['deliver_rate']}%",
        f"  端到端转化    {f['rates']['end_to_end_rate']}%",
        "",
        "【联系方式】",
        f"  有联系方式    {c['with_contact']:>6}   {c['contact_rate']}%",
        f"  手机          {c['phone']:>6}",
        f"  微信          {c['wechat']:>6}",
        f"  仅手机        {c['only_phone']:>6}",
        f"  仅微信        {c['only_wechat']:>6}",
        f"  两者都有      {c['both_phone_and_wechat']:>6}",
    ]
    if report.get("levels"):
        lines += ["", "【等级分布】"]
        for level, n in report["levels"].items():
            lines.append(f"  {level:<12}  {n:>6}")
    if report.get("categories"):
        lines += ["", "【类目分布 Top】"]
        for cat, n in report["categories"].items():
            lines.append(f"  {cat[:14]:<16}{n:>6}")
    jev = report.get("jev") or {}
    if jev.get("enabled"):
        lines += [
            "",
            "【JEV 内容复核】（advisory，不影响准入）",
            f"  覆盖          {jev['enabled']:>6}   {jev['coverage_rate']}%",
            f"  supported     {jev['routes'].get('supported', 0):>6}   {jev['supported_rate']}%",
            f"  uncertain     {jev['routes'].get('uncertain', 0):>6}   {jev['uncertain_rate']}%",
            f"  conflict      {jev['routes'].get('review_conflict', 0):>6}   {jev['conflict_rate']}%",
        ]
        conf = jev.get("confidence") or {}
        if conf.get("avg") is not None:
            lines.append(f"  置信度均值    {conf['avg']}（{conf['min']} ~ {conf['max']}）")
        if jev.get("backends"):
            lines.append(f"  后端          {jev['backends']}")

    risk = report.get("risk") or {}
    if any(risk.values()):
        lines += [
            "",
            "【风控状态】",
            f"  触发限流      {risk.get('rate_limited', 0):>6}",
            f"  未揭示        {risk.get('not_revealed', 0):>6}",
            f"  失败          {risk.get('failed', 0):>6}",
        ]
    if any(v for v in r.values() if v not in (None, 0, 0.0)):
        lines += [
            "",
            "【成本】",
            f"  预算          {r['budget']}",
            f"  估算花费      {r['estimated_spent']}",
            f"  单联系人成本  {r['cost_per_revealed_contact']}",
            f"  单交付成本    {r['cost_per_delivered']}",
        ]
    if report.get("throughput"):
        t = report["throughput"]
        lines += [
            "",
            "【速率】",
            f"  耗时          {t['elapsed_minutes']} 分钟",
            f"  每分钟揭示    {t['reveals_per_minute']}",
            f"  每次揭示耗时  {t['seconds_per_reveal']} 秒",
        ]
    return "\n".join(lines)


def main() -> int:
    import argparse
    import glob
    from pathlib import Path

    ap = argparse.ArgumentParser(description="生成 ROI 转化报告")
    ap.add_argument("--input", required=True, help="候选/交付 JSON（含 candidates 数组）")
    ap.add_argument("--out", default="", help="输出 JSON 路径（可选）")
    ap.add_argument("--name", default="", help="任务名称")
    ap.add_argument("--budget", type=float, default=0)
    ap.add_argument("--cost-per-reveal", type=float, default=0)
    ap.add_argument("--elapsed-minutes", type=float, default=0)
    args = ap.parse_args()

    paths = glob.glob(args.input)
    if not paths:
        print(json.dumps({"status": "error", "message": f"no file matches {args.input}"},
                         ensure_ascii=False))
        return 1

    payload = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    rows = payload.get("candidates") or payload.get("rows") or []

    report = build_roi(rows, {
        "id": payload.get("task_id") or "",
        "name": args.name or payload.get("task_id") or "",
        "budget": args.budget,
        "cost_per_reveal": args.cost_per_reveal,
        "elapsed_minutes": args.elapsed_minutes,
    })

    print(format_roi_text(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ JSON 已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def build_export_roi(candidates, selected, task_meta=None):
    """Use actual export selection rather than an earlier recommendation flag."""
    def identity(row):
        for field in ("identity", "buyin_uid", "douyin_id", "id", "主页身份ID"):
            if row.get(field):
                return ("id", str(row[field]))
        return ("row", json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
    selected_keys = {identity(row) for row in selected if isinstance(row, dict)}
    items = [{**row, "_delivered": identity(row) in selected_keys} for row in candidates if isinstance(row, dict)]
    report = build_roi(items, task_meta)
    report["export"] = {"selected_count": len(selected_keys), "candidate_scope": "saved_input_candidates", "sent_count": None}
    return report
