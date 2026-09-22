from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from embedded_cdp import connect_shop
from migrate_candidate_pool_to_realtime import candidate_identity, candidate_rows, migrate_candidate_rows
from realtime_creator_flow import RealtimeCreatorFlowStore, compact, is_terminal_state
from realtime_creator_processor import RealtimeCreatorProcessor


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def pending_candidate_rows(
    rows: list[dict[str, Any]], store: RealtimeCreatorFlowStore
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for source in rows:
        identity = candidate_identity(source)
        if not identity:
            continue
        record = store.get(identity)
        if record and is_terminal_state(record.get("state")):
            continue
        row = dict(record.get("row") or source) if record else dict(source)
        row["identity"] = identity
        pending.append(row)
    return pending


def process_pending_rows(
    rows: list[dict[str, Any]],
    processor: RealtimeCreatorProcessor,
    sessions: dict[str, tuple[Any, Any]],
) -> dict[str, int | bool]:
    processed = 0
    paused = False
    available = next(iter(sessions.values()), None)
    if available is None:
        raise RuntimeError("no_healthy_embedded_shop_session")
    for row in rows:
        shop = compact(row.get("shop")).upper()
        context, page = sessions.get(shop, available)
        updated = processor.process(context, page, row)
        processed += 1
        flow = getattr(processor, "flow", None)
        summary = flow.summary() if flow is not None else {}
        emit({
            "status": "realtime_creator_processed",
            "identity": candidate_identity(row),
            "shop": shop,
            "state": updated.get("realtime_flow_state"),
            "reason": updated.get("realtime_flow_reason"),
            **summary,
        })
        reason = compact(updated.get("realtime_flow_reason")).lower()
        if reason in {"rate_limited", "daily_quota_exhausted"}:
            paused = True
            break
    return {
        "processed": processed,
        "paused": paused,
        "remaining": max(0, len(rows) - processed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process candidate creators one at a time through evidence, authorized plaintext contact, and strict listing."
    )
    parser.add_argument("source")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--historical-strategy")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    rows = candidate_rows(json.loads(source.read_text(encoding="utf-8")))
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    historical_strategy = {}
    if args.historical_strategy:
        historical_strategy = json.loads(
            Path(args.historical_strategy).resolve().read_text(encoding="utf-8")
        )
    output_dir = Path(args.out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    flow_path = output_dir / "aipr_realtime_creator_flow.json"
    migration = migrate_candidate_rows(rows, flow_path)
    processor = RealtimeCreatorProcessor(
        output_dir=output_dir,
        strategy=strategy,
        historical_strategy=historical_strategy,
    )
    pending = pending_candidate_rows(rows, processor.flow)
    emit({"status": "realtime_backlog_started", **migration, "pending_count": len(pending)})
    if not pending:
        emit({"status": "realtime_backlog_finished", **processor.flow.summary()})
        return

    requested = [
        compact(value).upper()
        for value in strategy.get("activeShops") or ["A", "B"]
        if compact(value).upper() in {"A", "B"}
    ]
    endpoints = {"A": args.shop_a, "B": args.shop_b}
    sessions: dict[str, tuple[Any, Any]] = {}
    browsers: list[Any] = []
    with sync_playwright() as playwright:
        for shop in requested:
            try:
                browser, context, embedded_page = connect_shop(
                    playwright.chromium, endpoints[shop], timeout=15000
                )
                embedded_page.set_default_timeout(15000)
                browsers.append(browser)
                sessions[shop] = (context, embedded_page)
            except Exception as exc:
                emit({"status": "realtime_shop_unavailable", "shop": shop, "message": compact(exc)[:300]})
        result = process_pending_rows(pending, processor, sessions)
        emit({
            "status": "realtime_backlog_paused" if result["paused"] else "realtime_backlog_finished",
            **result,
            **processor.flow.summary(),
        })
        # The embedded browser belongs to AIPR Pro. Deliberately do not close it.
        _ = browsers
    if result["paused"]:
        raise SystemExit(9)


if __name__ == "__main__":
    main()
