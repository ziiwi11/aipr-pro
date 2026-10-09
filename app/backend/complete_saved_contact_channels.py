"""Software worker: revisit saved delivery without changing its creator/evidence pool."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from contact_shop_cooldown import shop_cooldown_until
from datetime import datetime
from atomic_json_io import atomic_write_json
from audit_strict_contact_highwater import _assert_strict_invariants, merged_audit_rules
from contact_pipeline_contract import creator_identity, contact_totals
from creator_delivery_contract import canonicalize_contact_fields, contact_identity_values, normalize_contact_value


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def retain_unique_supplements(originals, updates, rules):
    original_by_id = {creator_identity(row): row for row in originals}
    reserved = {normalize_contact_value(v) for v in rules.get('excludeContacts', [])}
    for row in originals:
        reserved.update(contact_identity_values(row))
    output = []
    for update in updates:
        old = original_by_id[creator_identity(update)]
        row = canonicalize_contact_fields({**old, **update})
        old = canonicalize_contact_fields(old)
        owned = contact_identity_values(old)
        rejected = []
        for channel, aliases in (
            ('wechat', ('buyin_contact_wechat', 'cart_contact_wechat', 'wechat', '微信')),
            ('phone', ('buyin_contact_phone', 'cart_contact_phone', 'phone', '手机号')),
            ('email', ('buyin_contact_email', 'cart_contact_email', 'email', '邮箱')),
        ):
            original_value = next((old.get(key) for key in aliases if old.get(key)), '')
            if original_value:
                for key in aliases:
                    if key in row or key in old:
                        row[key] = original_value
            value = next((row.get(key) for key in aliases if row.get(key)), '')
            normalized = normalize_contact_value(value)
            if normalized and normalized not in owned and normalized in reserved:
                rejected.append(channel)
                for key in aliases:
                    row[key] = old.get(key, '')
            elif normalized:
                reserved.add(normalized)
        # Contact-only updates must retain the original evidence and Jev decision.
        for key, value in old.items():
            if not key.startswith(('ui_contact_', 'cart_contact_', 'buyin_contact_', 'ui_add_library_')):
                row[key] = value
        if any(marker in str(row.get('ui_contact_message') or '') for marker in ('主推类目不属于店铺类目', '本周仅支持')):
            row['ui_contact_channels_status'] = 'category_not_matched'
        row['ui_contact_supplement_duplicate_channels'] = rejected
        text = '；'.join(f'{label}:{next((row.get(k) for k in keys if row.get(k)), "")}' for label, keys in (
            ('微信', ('buyin_contact_wechat', 'cart_contact_wechat')),
            ('手机', ('buyin_contact_phone', 'cart_contact_phone')),
            ('邮箱', ('buyin_contact_email', 'cart_contact_email')),
        ) if any(row.get(k) for k in keys))
        row['cart_contact_text'] = row['buyin_contact_text'] = text
        output.append(row)
    return output


def main():
    p = argparse.ArgumentParser()
    for name in ('input', 'strategy', 'out-dir', 'task-id', 'task-name', 'shop-a', 'shop-b'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--robot-queue', default='')
    p.add_argument('--delay-ms', default='3200')
    args = p.parse_args()
    out = Path(args.out_dir)
    source = json.loads(Path(args.input).read_text())
    originals = source['candidates']
    rules = merged_audit_rules(source['strategy'], {})
    # Completion can revisit older batches: reserve the current saved contacts
    # of every other batch, including batches collected after this one.
    historical = set(rules.get('excludeContacts', []))
    for snapshot in out.parent.glob('*/aipr_strict_contact_highwater.json'):
        if snapshot.parent == out:
            continue
        other = json.loads(snapshot.read_text())
        for creator in other.get('candidates', []):
            historical.update(contact_identity_values(creator))
    rules['excludeContacts'] = sorted(historical)
    source['strategy'] = {**source['strategy'], 'excludeContacts': sorted(historical)}
    _assert_strict_invariants(originals, rules)
    while True:
        available = ['A', 'B']
        probes = sorted(out.glob('two_shop_login_probe_*.json'), key=lambda path: path.stat().st_mtime)
        if probes:
            try:
                shops = json.loads(probes[-1].read_text()).get('shops', {})
                verified = [lane for lane in available if shops.get(lane, {}).get('merchant_logged_in') is True and shops.get(lane, {}).get('buyin_ready') is True]
                if verified:
                    available = verified
            except (OSError, ValueError):
                pass
        remaining = min(shop_cooldown_until(out, lane) for lane in available) - time.time()
        if remaining <= 0:
            break
        emit({'status': 'contact_cooldown_wait', 'message': '可用店铺正在冷却，软件等待后自动续跑', 'remaining_seconds': round(remaining)})
        time.sleep(min(45, remaining))
    before = set(out.glob('aipr_creator_contacts_*.json'))
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name('scrape_buyin_profile_contact_icons_cdp.py')),
        '--input', args.input, '--out-dir', args.out_dir, '--shop-a', args.shop_a,
        '--shop-b', args.shop_b, '--delay-ms', args.delay_ms, '--complete-contact-channels'])
    paths = sorted(set(out.glob('aipr_creator_contacts_*.json')) - before, key=lambda f: f.stat().st_mtime)
    if not paths:
        raise SystemExit(proc.returncode or 9)
    collected = json.loads(paths[-1].read_text())
    updates = collected['candidates']
    if {creator_identity(row) for row in updates} != {creator_identity(row) for row in originals}:
        raise RuntimeError('completion_creator_pool_changed')
    baseline_path = out / 'aipr_contact_channels_baseline.json'
    original_contacts = json.loads(baseline_path.read_text())['candidates'] if baseline_path.exists() else originals
    rows = retain_unique_supplements(original_contacts, updates, rules)
    audit = _assert_strict_invariants(rows, rules)
    result = {**source, 'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'candidates': rows, 'audit': audit}
    # Preserve the original pool in an immutable baseline across resumed runs.
    baseline = out / 'aipr_contact_channels_baseline.json'
    if not baseline.exists():
        atomic_write_json(baseline, source)
    atomic_write_json(Path(args.input), result)
    totals = contact_totals(rows)
    checked = sum(bool(row.get('ui_contact_channels_checked_at')) for row in rows)
    emit({'status': 'contact_collection_finished', 'output': args.input, 'candidate_count': len(rows),
        'plain_contact_count': totals['plain'], 'wechat_contact_count': totals['wechat'],
        'phone_contact_count': totals['phone'], 'email_contact_count': totals['email'],
        'channels_checked_count': checked})
    command = [sys.executable, str(Path(__file__).with_name('finalize_creator_delivery.py')),
        '--input', args.input, '--strategy', args.strategy, '--out-dir', args.out_dir,
        '--task-id', args.task_id, '--task-name', args.task_name, '--require-strict-highwater']
    if args.robot_queue:
        command.extend(['--robot-queue', args.robot_queue])
    final = subprocess.run(command)
    incomplete = checked < len(rows) or any(row.get('ui_contact_channels_status') in ('partial', 'rate_limited', 'daily_quota_exhausted') for row in rows)
    if incomplete:
        emit({'status': 'contact_channels_incomplete', 'message': '联系方式补全尚未结束，已保存进度', 'checked': checked, 'total': len(rows)})
    raise SystemExit(final.returncode or proc.returncode or (10 if incomplete else 0))


if __name__ == '__main__':
    main()
