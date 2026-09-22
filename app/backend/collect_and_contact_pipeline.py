from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from console_io import configure_utf8_stdout
from cdp_session_hygiene import prune_automation_pages
from creator_delivery_contract import requires_underwear_product_evidence
from contact_pipeline_contract import terminal_contact_failure
from pipeline_acceptance import source_pool_target, validate_candidate_count


configure_utf8_stdout()


REPLENISHMENT_KEYWORDS = (
    "收腹提臀裤", "女士塑形裤", "高腰收腹裤", "无痕塑形裤", "塑形裤测评",
    "内衣试穿", "提臀裤试穿", "塑身衣试穿", "女士内衣测评", "产后塑形",
    "妈妈臀塑形", "臀凹陷塑形", "收腹裤测评", "塑身裤穿搭",
)

LOW_POOL_KEYWORDS = (
    "内衣好物", "女士穿搭", "女装穿搭", "服饰测评", "内衣测评", "收腹内裤",
    "无痕裤", "无痕内裤", "塑形好物", "身材管理", "瑜伽裤穿搭", "打底裤测评",
    "安全裤测评", "居家内衣", "高腰内裤", "提臀内裤", "内衣分享", "服饰好物",
)

LOW_POOL_ROUND_KEYWORDS = (
    (
        "塑形连体衣", "美体塑形", "高腰提臀", "无痕收腹", "产后收腹裤", "塑形打底裤",
    ),
    (
        "提臀瑜伽裤", "高腰瑜伽裤", "鲨鱼裤测评", "收腹鲨鱼裤", "提臀打底裤", "女士美体裤",
    ),
    (
        "塑身连体衣", "无痕美体衣", "腰腹塑形", "臀型管理", "内衣真人试穿", "塑形裤真人测评",
    ),
)


BEAUTY_REPLENISHMENT_KEYWORDS = (
    "唇部精华", "润唇精华", "唇膜测评", "唇油测评", "淡唇纹", "改善唇色",
    "嘴唇起皮", "口红卡纹", "护唇好物", "唇部护理", "美妆好物", "护肤测评",
)

BEAUTY_LOW_POOL_KEYWORDS = (
    "润唇", "唇膜", "唇油", "唇蜜", "唇部保养", "唇部抗老", "唇色暗沉",
    "嘟嘟唇", "精致妆容", "口红试色", "美妆测评", "护肤分享", "居家变美",
    "真人口播美妆", "唇部产品测评", "干唇护理", "淡化唇纹", "不粘杯唇蜜",
)

PLATFORM_PAUSE_MARKERS = (
    "platform_paused", "请求过于频繁", "访问过于频繁", "访问频繁", "稍后再试", "安全验证", "验证码",
)


def candidate_identity_values(candidate: dict) -> set[str]:
    return {
        str(candidate.get(key) or "").strip()
        for key in ("identity", "buyin_uid", "douyin_id", "author_id", "sec_uid")
        if str(candidate.get(key) or "").strip()
    }


def platform_pause_event(event: dict) -> bool:
    status = str(event.get("status") or "").strip().lower()
    message = str(event.get("message") or "").strip().lower()
    return (
        status in {"rate_limited", "platform_paused"}
        or status.endswith("_rate_limited")
        or any(marker.lower() in message for marker in PLATFORM_PAUSE_MARKERS)
    )


def beauty_strategy(strategy: dict | None) -> bool:
    current = strategy or {}
    haystack = " ".join([
        str(current.get("category") or ""),
        str(current.get("brief") or ""),
        *[str(item) for item in current.get("keywords") or []],
    ])
    return any(term in haystack for term in ("美妆", "护肤", "唇", "口红", "润唇"))


def extend_replenishment_keywords(keywords: list[str], strategy: dict | None = None) -> list[str]:
    extra = BEAUTY_REPLENISHMENT_KEYWORDS if beauty_strategy(strategy) else REPLENISHMENT_KEYWORDS
    return list(dict.fromkeys([*keywords, *extra]))


def extend_low_pool_keywords(
    keywords: list[str],
    round_index: int = 1,
    strategy: dict | None = None,
) -> list[str]:
    if beauty_strategy(strategy):
        return list(dict.fromkeys([*keywords, *BEAUTY_LOW_POOL_KEYWORDS]))
    extra: list[str] = list(LOW_POOL_KEYWORDS)
    completed_groups = max(0, min(len(LOW_POOL_ROUND_KEYWORDS), int(round_index or 1) - 1))
    for group in LOW_POOL_ROUND_KEYWORDS[:completed_groups]:
        extra.extend(group)
    return list(dict.fromkeys([*keywords, *extra]))


def should_replenish_source_pool(actual: int, target: int, round_index: int, max_rounds: int) -> bool:
    return int(actual or 0) < int(target or 0) and int(round_index) < int(max_rounds)


def contact_quota_exhausted_shops(events: list[dict]) -> list[str]:
    event = next(
        (item for item in reversed(events) if item.get("status") == "contact_daily_quota_exhausted"),
        {},
    )
    return [str(shop) for shop in event.get("shops") or [] if str(shop)]


def merge_candidate_sources(base_payload: dict, extra_payloads: list[dict], excluded: set[str]) -> dict:
    pool: dict[str, dict] = {}
    for source in [base_payload, *extra_payloads]:
        for row in source.get("candidates") or []:
            identity = str(row.get("identity") or "").strip()
            if not identity or candidate_identity_values(row) & excluded:
                continue
            if identity not in pool:
                pool[identity] = dict(row)
                continue
            current = pool[identity]
            for key, value in row.items():
                if current.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    current[key] = value
    return {
        **base_payload,
        "status": "ready",
        "candidate_count": len(pool),
        "candidates": list(pool.values()),
    }


def load_verified_candidate_seed(output_dir: Path, excluded: set[str]) -> dict | None:
    seed_path = output_dir / "aipr_verified_candidate_seed.json"
    if not seed_path.exists():
        return None
    try:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    candidates = []
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        identity = str(row.get("identity") or row.get("buyin_uid") or row.get("douyin_id") or "").strip()
        evaluation = row.get("osmana_evaluation") if isinstance(row.get("osmana_evaluation"), dict) else {}
        if identity and not (candidate_identity_values(row) & excluded) and evaluation.get("qualified"):
            candidates.append(dict(row))
    if not candidates:
        return None
    return {"status": "ready", "candidate_count": len(candidates), "candidates": candidates}


def load_historical_contact_candidates(task_root: Path, current_output: Path, excluded: set[str]) -> list[dict]:
    contacts: dict[str, dict] = {}
    delivered = set(excluded)
    current_highwater = current_output / "aipr_contact_highwater.json"
    if current_highwater.exists():
        try:
            payload = json.loads(current_highwater.read_text(encoding="utf-8"))
            for row in payload.get("candidates") or []:
                if not isinstance(row, dict) or row.get("precontact_qualified") is not True:
                    continue
                identity = str(row.get("identity") or "").strip()
                has_plain = any(row.get(key) for key in (
                    "buyin_contact_wechat", "cart_contact_wechat", "buyin_contact_phone", "cart_contact_phone",
                    "buyin_contact_email", "cart_contact_email",
                ))
                if identity and has_plain:
                    contacts[identity] = dict(row)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    for path in task_root.glob("task-*/aipr_final_delivery_*.json"):
        if path.parent.resolve() == current_output.resolve():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        for row in payload.get("rows") or payload.get("candidates") or []:
            if isinstance(row, dict):
                identity = str(
                    row.get("identity") or row.get("主页身份ID") or row.get("identity_id") or ""
                ).strip()
                if identity:
                    delivered.add(identity)
    for identity in delivered:
        contacts.pop(identity, None)
    paths = sorted(task_root.glob("task-*/aipr_creator_contacts_*.json"), key=lambda item: item.stat().st_mtime)
    for path in paths:
        if path.parent.resolve() == current_output.resolve():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        for row in payload.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            identity = str(row.get("identity") or "").strip()
            has_plain = any(row.get(key) for key in (
                "buyin_contact_wechat", "cart_contact_wechat", "buyin_contact_phone", "cart_contact_phone",
                "buyin_contact_email", "cart_contact_email",
            ))
            if identity and identity not in delivered and has_plain:
                contacts[identity] = dict(row)
    return [contacts[identity] for identity in sorted(contacts)]


def should_reuse_historical_contacts(strategy: dict) -> bool:
    """Historical contacts are opt-in so a fresh task cannot silently reuse old creators."""
    return strategy.get("reuseHistoricalContacts") is True


def resolve_evidence_lanes_per_shop(strategy: dict) -> int:
    raw = strategy.get("evidenceLanesPerShop")
    if raw is None:
        return 4
    try:
        return max(1, min(4, int(raw)))
    except (TypeError, ValueError):
        return 4


def resolve_max_replenishment_rounds(strategy: dict) -> int:
    raw = strategy.get("maxReplenishmentRounds")
    if raw is None:
        return 16
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 16


def build_replenishment_exclusions(candidates: list[dict], existing: set[str] | None = None) -> set[str]:
    exclusions = set(existing or set())
    for row in candidates:
        identity = str(row.get("identity") or "").strip()
        has_plain = any(row.get(key) for key in (
            "buyin_contact_wechat", "cart_contact_wechat", "buyin_contact_phone", "cart_contact_phone",
            "buyin_contact_email", "cart_contact_email",
        ))
        interrupted_before_icon_probe = bool(
            row.get("precontact_qualified") is True
            and row.get("buyin_public_intro_checked")
            and not row.get("ui_contact_probe_at")
            and not terminal_contact_failure(row)
        )
        if identity and not (
            (row.get("precontact_qualified") is True and has_plain)
            or interrupted_before_icon_probe
        ):
            exclusions.add(identity)
    return exclusions


def restore_replenishment_state(strategy: dict, contact_payload: dict) -> dict:
    restored = dict(strategy)
    prior_strategy = contact_payload.get("strategy") or {}
    candidates = [row for row in contact_payload.get("candidates") or [] if isinstance(row, dict)]
    inherited_exclusions = {
        str(item).strip()
        for item in [
            *(strategy.get("excludeIdentities") or []),
            *(prior_strategy.get("excludeIdentities") or []),
        ]
        if str(item).strip()
    }
    if requires_underwear_product_evidence(strategy):
        unverified_identities = {
            str(row.get("identity") or "").strip()
            for row in candidates
            if str(row.get("identity") or "").strip()
            and "buyin_product_evidence_reviewed" not in row
            and "products_30d" not in row
            and not str(row.get("osmana_evidence_status") or "").strip()
        }
        inherited_exclusions.difference_update(unverified_identities)
        candidates = [
            row for row in candidates
            if str(row.get("identity") or "").strip() not in unverified_identities
        ]
    restored["excludeIdentities"] = sorted(build_replenishment_exclusions(
        candidates,
        inherited_exclusions,
    ))
    restored["keywords"] = list(dict.fromkeys([
        *[str(item).strip() for item in strategy.get("keywords") or [] if str(item).strip()],
        *[str(item).strip() for item in prior_strategy.get("keywords") or [] if str(item).strip()],
    ]))
    prior_round = max(
        int(strategy.get("replenishmentRound") or 0),
        int(prior_strategy.get("replenishmentRound") or 0),
    )
    if prior_round:
        restored["replenishmentRound"] = prior_round
    return restored


def resumable_collection_pool(output_dir: Path, strategy: dict) -> dict | None:
    path = output_dir / "aipr_buyin_creator_pool_similar.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    prior_strategy = payload.get("strategy") or {}
    current_exclusions = {str(item).strip() for item in strategy.get("excludeIdentities") or [] if str(item).strip()}
    prior_exclusions = {str(item).strip() for item in prior_strategy.get("excludeIdentities") or [] if str(item).strip()}
    current_keywords = {str(item).strip() for item in strategy.get("keywords") or [] if str(item).strip()}
    prior_keywords = {str(item).strip() for item in prior_strategy.get("keywords") or [] if str(item).strip()}
    candidate_count = len([item for item in payload.get("candidates") or [] if isinstance(item, dict)])
    target_count = max(1, int(strategy.get("targetCount") or 1))
    if (
        payload.get("status") != "ready"
        or candidate_count <= 0
        or current_exclusions != prior_exclusions
        or current_keywords != prior_keywords
    ):
        return None
    return {"output": str(path), "candidate_count": candidate_count}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def recover_completed_collection(highwater_path: Path, strategy: dict) -> dict | None:
    try:
        payload = json.loads(highwater_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    candidates = [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
    candidate_count = len(candidates)
    target = source_pool_target(
        int(strategy.get("targetCount") or 1),
        bool(strategy.get("requireContact")),
    )
    if payload.get("status") != "ready" or candidate_count < target:
        return None
    return {
        "status": "collection_finished",
        "output": str(highwater_path),
        "candidate_count": candidate_count,
        "recovered_from_highwater": True,
        "message": "采集连接无进展，已从完整高水位候选池自动恢复",
    }


def run_stream(
    command: list[str],
    idle_timeout_seconds: float = 0,
    recover_on_idle: Callable[[], dict | None] | None = None,
) -> tuple[int, list[dict]]:
    events: list[dict] = []
    pause_streak = 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    output_queue: queue.Queue[str | None] = queue.Queue()
    stderr_chunks: list[str] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output_queue.put(line)
        output_queue.put(None)

    def read_stderr() -> None:
        if process.stderr is not None:
            stderr_chunks.extend(process.stderr.readlines())

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    while True:
        try:
            line = output_queue.get(timeout=idle_timeout_seconds if idle_timeout_seconds > 0 else None)
        except queue.Empty:
            recovered = recover_on_idle() if recover_on_idle else None
            if not recovered:
                continue
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            emit(recovered)
            events.append(recovered)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            return 0, events
        if line is None:
            break
        clean = line.strip()
        if not clean:
            continue
        print(clean, flush=True)
        try:
            event = json.loads(clean)
            events.append(event)
            if platform_pause_event(event):
                # 偶发 rate_limited 是单次频次抖动，子进程内部已能跳过该达人继续；
                # 只有连续 3 次才判定为平台真限制并终止整棵进程树。
                pause_streak += 1
                if pause_streak < 3:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
                emit({
                    "status": "pipeline_platform_paused",
                    "source_status": event.get("status", ""),
                    "message": event.get("message", "平台限制，已停止整个采集进程树"),
                })
                return 9, events
        except json.JSONDecodeError:
            pass
    code = process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    stderr = "".join(stderr_chunks)
    if stderr.strip():
        emit({"status": "worker_stderr", "message": stderr.strip()[-1200:]})
    return code, events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    parser.add_argument("--delay-ms", type=int, default=3200)
    parser.add_argument("--task-id", default="brand-task")
    parser.add_argument("--task-name", default="品牌达人任务")
    parser.add_argument("--original-workbook", default="")
    parser.add_argument("--robot-queue", default="")
    args = parser.parse_args()

    backend = Path(__file__).resolve().parent
    collector = backend / "collect_buyin_creators_cdp.py"
    contacts = backend / "scrape_buyin_profile_contact_icons_cdp.py"
    verifier = backend / "verify_creator_evidence_cdp.py"
    buyin_evidence = backend / "verify_osmana_buyin_evidence_cdp.py"
    douyin_evidence = backend / "verify_osmana_douyin_content_cdp.py"
    finalizer = backend / "finalize_creator_delivery.py"
    similar_collector = backend / "collect_osmana_similar_cdp.py"
    strategy_path = Path(args.strategy).resolve()
    output_dir = Path(args.out_dir).resolve()
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    if requires_underwear_product_evidence(strategy):
        strategy.setdefault("minimumUnderwearProductSales", int(strategy.get("minimumMonthlySales") or 10000))
        strategy.setdefault("minimumLevel", min([int(item) for item in strategy.get("creatorLevels") or [2]]))
        # Body measurements were explicitly removed from this brand's brief.
        strategy.setdefault("requireBodyMeasurements", False)
        strategy.setdefault("requireShapewearContent", False)
        strategy.setdefault("requirePlainContact", True)
    contact_highwater = output_dir / "aipr_contact_highwater.json"
    if contact_highwater.exists():
        try:
            strategy = restore_replenishment_state(
                strategy,
                json.loads(contact_highwater.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    max_rounds = resolve_max_replenishment_rounds(strategy)

    active_shops = [
        str(shop).upper()
        for shop in strategy.get("activeShops") or ["A"]
        if str(shop).upper() in {"A", "B"}
    ]
    endpoints = {"A": args.shop_a, "B": args.shop_b}
    for shop in active_shops:
        endpoint = endpoints[shop]
        try:
            emit({"status": "cdp_session_cleaned", "shop": shop, "closed_pages": prune_automation_pages(endpoint)})
        except Exception as exc:
            emit({"status": "cdp_session_cleanup_warning", "shop": shop, "message": str(exc)[:300]})

    similar_attempted = False
    emit({"status": "pipeline_started", "message": "达人与联系方式同步采集已启动"})
    for round_index in range(1, max_rounds + 1):
        strategy_path.write_text(json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8")
        emit({"status": "pipeline_round_started", "round": round_index, "max_rounds": max_rounds})
        excluded = {str(item).strip() for item in strategy.get("excludeIdentities") or [] if str(item).strip()}
        verified_seed = load_verified_candidate_seed(output_dir, excluded)
        collection: dict = {}
        resumed = None
        if verified_seed and verified_seed["candidate_count"] >= int(strategy.get("targetCount") or 1):
            verified_seed["strategy"] = strategy
            seed_resume_output = output_dir / "aipr_verified_candidate_resume_pool.json"
            seed_resume_output.write_text(json.dumps(verified_seed, ensure_ascii=False, indent=2), encoding="utf-8")
            collect_code = 0
            collection = {
                "status": "collection_finished",
                "output": str(seed_resume_output),
                "candidate_count": verified_seed["candidate_count"],
                "verified_seed_only": True,
            }
            emit({
                "status": "verified_candidate_seed_resumed",
                "candidate_count": verified_seed["candidate_count"],
                "target_count": strategy.get("targetCount", 0),
                "message": "已验证未交付候选足以完成目标，跳过重复采集与重复内容复核",
            })
        else:
            resumed = resumable_collection_pool(output_dir, strategy)
        if not collection.get("verified_seed_only") and resumed:
            collect_code = 0
            collection = {"status": "collection_finished", **resumed}
            similar_attempted = True
            emit({"status": "collection_resumed", **resumed})
        elif not collection.get("verified_seed_only"):
            collect_code, events = run_stream([
                sys.executable, str(collector),
                "--strategy", str(strategy_path),
                "--out-dir", str(output_dir),
                "--shop-a", args.shop_a,
                "--shop-b", args.shop_b,
            ], idle_timeout_seconds=90, recover_on_idle=lambda: recover_completed_collection(
                output_dir / "aipr_collection_highwater.json",
                strategy,
            ))
            collection = next((event for event in reversed(events) if event.get("status") == "collection_finished"), None)
        if collect_code or not collection or not collection.get("output"):
            emit({"status": "pipeline_error", "message": "达人采集未生成可用候选池"})
            raise SystemExit(collect_code or 2)
        actual_count = int(collection.get("candidate_count", 0) or 0)
        target_count = int(strategy.get("targetCount", 500) or 500)
        if actual_count < target_count and not similar_attempted and contact_highwater.exists():
            similar_attempted = True
            similar_payloads: list[dict] = []
            for shop, endpoint in (("A", args.shop_a), ("B", args.shop_b)):
                _code, similar_events = run_stream([
                    sys.executable, str(similar_collector),
                    "--input", str(contact_highwater),
                    "--endpoint", endpoint,
                    "--shop", shop,
                    "--out-dir", str(output_dir),
                    "--strategy", str(strategy_path),
                    "--seed-limit", "40",
                    "--change-rounds", "3",
                    "--target-count", str(max(target_count * 2, 150)),
                    "--cross-shop-seeds",
                ])
                event = next((item for item in reversed(similar_events) if item.get("status") == "osmana_similar_finished"), None)
                if event and event.get("output"):
                    try:
                        similar_payloads.append(json.loads(Path(event["output"]).read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        pass
            base_payload = json.loads(Path(collection["output"]).read_text(encoding="utf-8"))
            excluded = {str(item).strip() for item in strategy.get("excludeIdentities") or [] if str(item).strip()}
            combined = merge_candidate_sources(base_payload, similar_payloads, excluded)
            # Never let a low-yield similar query replace a larger collection high-water.
            for existing_highwater_path in (
                output_dir / "aipr_collection_highwater.json",
                output_dir / "aipr_contact_highwater.json",
                output_dir / "aipr_evidence_highwater.json",
            ):
                if not existing_highwater_path.exists():
                    continue
                try:
                    existing_highwater = json.loads(existing_highwater_path.read_text(encoding="utf-8"))
                    if len(existing_highwater.get("candidates") or []) > len(combined.get("candidates") or []):
                        combined = existing_highwater
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
            combined["candidate_count"] = len(combined.get("candidates") or [])
            combined["strategy"] = strategy
            similar_output = output_dir / "aipr_buyin_creator_pool_similar.json"
            similar_output.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
            (output_dir / "aipr_collection_highwater.json").write_text(
                json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            collection["output"] = str(similar_output)
            collection["candidate_count"] = combined["candidate_count"]
            actual_count = combined["candidate_count"]
            emit({
                "status": "similar_source_finished",
                "candidate_count": actual_count,
                "target_count": target_count,
                "source_count": len(similar_payloads),
            })
        if should_replenish_source_pool(actual_count, target_count, round_index, max_rounds):
            replenishment_round = max(
                round_index,
                int(strategy.get("replenishmentRound") or 0) + 1,
            )
            strategy["keywords"] = extend_low_pool_keywords([
                str(item).strip() for item in strategy.get("keywords") or [] if str(item).strip()
            ], round_index=replenishment_round, strategy=strategy)
            strategy["replenishmentRound"] = replenishment_round
            strategy_path.write_text(json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8")
            emit({
                "status": "source_pool_replenishing",
                "round": round_index,
                "candidate_count": actual_count,
                "target_count": target_count,
                "keyword_count": len(strategy["keywords"]),
                "message": "候选池不足，已自动扩展同类目关键词继续补充",
            })
            # Allow the next replenishment round to query a fresh similar pool.
            similar_attempted = False
            continue
        try:
            validate_candidate_count(actual_count, target_count)
        except ValueError as exc:
            emit({"status": "pipeline_error", "message": str(exc), "stage": "collection"})
            raise SystemExit(6)

        base_payload = json.loads(Path(collection["output"]).read_text(encoding="utf-8"))
        excluded = {str(item).strip() for item in strategy.get("excludeIdentities") or [] if str(item).strip()}
        verified_seed = load_verified_candidate_seed(output_dir, excluded)
        if verified_seed:
            base_payload = merge_candidate_sources(base_payload, [verified_seed], excluded)
            base_payload["strategy"] = strategy
            seed_output = output_dir / "aipr_buyin_creator_pool_with_verified_seed.json"
            seed_output.write_text(json.dumps(base_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            collection["output"] = str(seed_output)
            collection["candidate_count"] = base_payload["candidate_count"]
            emit({
                "status": "verified_candidate_seed_merged",
                "seed_count": verified_seed["candidate_count"],
                "candidate_count": base_payload["candidate_count"],
                "message": "已复用未交付且具备完整单品、内容与联系方式证据的候选高水位",
            })
        historical_contacts = (
            load_historical_contact_candidates(output_dir.parent, output_dir, excluded)
            if should_reuse_historical_contacts(strategy)
            else []
        )
        if historical_contacts:
            combined = merge_candidate_sources(base_payload, [{"candidates": historical_contacts}], excluded)
            combined["strategy"] = strategy
            history_output = output_dir / "aipr_buyin_creator_pool_with_history.json"
            history_output.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
            collection["output"] = str(history_output)
            collection["candidate_count"] = combined["candidate_count"]
            emit({
                "status": "historical_contact_source_merged",
                "historical_contact_count": len(historical_contacts),
                "candidate_count": combined["candidate_count"],
                "message": "已引入未交付历史联系人，仍按当前任务规则重新核验",
            })

        if collection.get("verified_seed_only"):
            evidence_code = 0
            evidence = {"status": "evidence_finished", "output": collection["output"]}
            emit({
                "status": "evidence_highwater_reused",
                "candidate_count": collection["candidate_count"],
                "message": "候选均已有单品、短视频、画面与主页证据，跳过重复复核",
            })
        else:
            emit({"status": "evidence_stage_started", "message": "开始验证精选联盟主页与抖音内容证据"})
            evidence_code, evidence_events = run_stream([
                sys.executable, str(verifier),
                "--input", str(collection["output"]),
                "--out-dir", str(output_dir),
                "--shop-a", args.shop_a,
                "--shop-b", args.shop_b,
                "--lanes-per-shop", str(resolve_evidence_lanes_per_shop(strategy)),
                "--keywords-json", json.dumps(strategy.get("keywords") or [], ensure_ascii=False),
            ])
            evidence = next((event for event in reversed(evidence_events) if event.get("status") == "evidence_finished"), None)
            if evidence_code or not evidence or not evidence.get("output"):
                emit({"status": "pipeline_error", "message": "主页与内容证据阶段未生成结果"})
                raise SystemExit(evidence_code or 3)

        contact_input = evidence["output"]
        if requires_underwear_product_evidence(strategy):
            emit({"status": "osmana_buyin_evidence_started", "message": "开始核验精选联盟内衣单品近30天短视频销售额"})
            buyin_code, buyin_events = run_stream([
                sys.executable, str(buyin_evidence),
                "--input", str(contact_input),
                "--strategy", str(strategy_path),
                "--out-dir", str(output_dir),
                "--shop-a", args.shop_a,
                "--shop-b", args.shop_b,
                "--delay-ms", str(max(1500, args.delay_ms // 2)),
            ])
            buyin_finished = next((event for event in reversed(buyin_events) if event.get("status") == "osmana_buyin_evidence_finished"), None)
            if buyin_code or not buyin_finished or not buyin_finished.get("output"):
                emit({"status": "pipeline_error", "stage": "osmana_buyin_evidence", "message": "精选联盟单品销售额证据阶段失败"})
                raise SystemExit(buyin_code or 3)
            contact_input = buyin_finished["output"]
            for shop in active_shops:
                endpoint = args.shop_a if shop == "A" else args.shop_b
                emit({"status": "osmana_douyin_evidence_started", "shop": shop, "message": "开始核验抖音主页、真人短视频和非直播证据"})
                douyin_code, douyin_events = run_stream([
                    sys.executable, str(douyin_evidence),
                    "--input", str(contact_input),
                    "--strategy", str(strategy_path),
                    "--out-dir", str(output_dir),
                    "--endpoint", endpoint,
                    "--shop", shop,
                    "--delay-ms", str(max(1800, args.delay_ms)),
                ])
                douyin_finished = next((event for event in reversed(douyin_events) if event.get("status") == "osmana_douyin_finished"), None)
                if douyin_code or not douyin_finished or not douyin_finished.get("output"):
                    emit({"status": "pipeline_error", "stage": "osmana_douyin_evidence", "shop": shop, "message": "抖音内容证据阶段失败"})
                    raise SystemExit(douyin_code or 3)
                contact_input = douyin_finished["output"]
        exhausted_contact_shops: list[str] = []
        if strategy.get("requireContact") is False:
            contact_output = contact_input
            contact_code = 0
            emit({"status": "contact_collection_skipped", "message": "本任务未要求联系方式"})
        else:
            emit({
                "status": "contact_collection_started",
                "candidate_count": collection.get("candidate_count", 0),
                "message": "证据复核完成，候选达人进入联系方式慢速采集",
            })
            contact_code, contact_events = run_stream([
                sys.executable, str(contacts),
                "--input", str(contact_input),
                "--out-dir", str(output_dir),
                "--delay-ms", str(max(3000, args.delay_ms)),
                "--shop-a", args.shop_a,
                "--shop-b", args.shop_b,
            ])
            contact = next((event for event in reversed(contact_events) if event.get("status") == "contact_collection_finished"), None)
            if not contact or not contact.get("output"):
                emit({"status": "pipeline_error", "message": "联系方式阶段未生成可合并结果"})
                raise SystemExit(contact_code or 4)
            contact_output = contact["output"]
            exhausted_contact_shops = contact_quota_exhausted_shops(contact_events)

        finalize_command = [
            sys.executable, str(finalizer),
            "--input", str(contact_output),
            "--strategy", str(strategy_path),
            "--out-dir", str(output_dir),
            "--task-id", args.task_id,
            "--task-name", args.task_name,
        ]
        if args.original_workbook:
            finalize_command.extend(["--original-workbook", args.original_workbook])
        if args.robot_queue:
            finalize_command.extend(["--robot-queue", args.robot_queue])
        finalize_code, finalize_events = run_stream(finalize_command)
        delivery = next((event for event in reversed(finalize_events) if event.get("status") == "delivery_ready"), None)
        if delivery:
            emit({"status": "pipeline_finished", "contact_stage": "finished", "delivery": delivery.get("output"), "code": contact_code})
            raise SystemExit(contact_code)

        incomplete = next((event for event in reversed(finalize_events) if event.get("status") == "delivery_incomplete"), None)
        if incomplete and exhausted_contact_shops:
            emit({
                "status": "pipeline_waiting_for_contact_quota",
                "shops": exhausted_contact_shops,
                "qualified_count": incomplete.get("qualified_count", 0),
                "target_count": incomplete.get("target_count", strategy.get("targetCount", 0)),
                "message": "查看达人联系方式次数已达上限，当前高水位已保存，等待额度恢复或新店铺登录后继续",
            })
            raise SystemExit(9)
        if not incomplete or round_index >= max_rounds:
            emit({"status": "pipeline_error", "message": "最终交付阶段失败", "round": round_index})
            raise SystemExit(finalize_code or 5)
        contact_payload = json.loads(Path(contact_output).read_text(encoding="utf-8"))
        existing_exclusions = {str(item).strip() for item in strategy.get("excludeIdentities") or [] if str(item).strip()}
        exclusions = build_replenishment_exclusions(contact_payload.get("candidates") or [], existing_exclusions)
        strategy["excludeIdentities"] = sorted(exclusions)
        strategy["keywords"] = extend_replenishment_keywords(
            [str(item).strip() for item in strategy.get("keywords") or [] if str(item).strip()],
            strategy=strategy,
        )
        strategy["replenishmentRound"] = round_index
        strategy_path.write_text(json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8")
        emit({
            "status": "delivery_replenishing",
            "round": round_index,
            "qualified_count": incomplete.get("qualified_count", 0),
            "target_count": incomplete.get("target_count", strategy.get("targetCount", 0)),
            "excluded_count": len(exclusions),
            "message": "合规联系人不足，已保留高水位并自动补充精准达人来源",
        })

    raise SystemExit(5)


if __name__ == "__main__":
    main()
