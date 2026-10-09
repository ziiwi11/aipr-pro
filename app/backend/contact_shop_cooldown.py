"""Persist shop-specific cooldowns, retaining unidentified legacy restrictions."""
import json
import time
from pathlib import Path


def cooldown_path(out, shop=''):
    return Path(out) / (f'.contact_rate_limit_until_{shop}' if shop in ('A', 'B') else '.contact_rate_limit_until')


def read_until(path):
    try:
        return float(path.read_text())
    except (OSError, ValueError):
        return 0.0


def shop_cooldown_until(out, shop):
    out = Path(out)
    own = read_until(cooldown_path(out, shop))
    legacy = read_until(cooldown_path(out))
    if legacy <= time.time():
        return own
    # Old workers marked all shops. Only narrow this when a saved response
    # proves which shop actually received the platform restriction.
    evidence = set()
    for lane in ('A', 'B'):
        files = sorted(out.glob(f'ui_contact_icon_retry_{lane}_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            continue
        try:
            rows = json.loads(files[0].read_text()).get('candidates', [])
        except (OSError, ValueError):
            continue
        for row in rows:
            message = str(row.get('ui_contact_message') or '')
            if row.get('ui_contact_probe_status') == 'rate_limited' and ('请求过于频繁' in message or '稍后再试' in message):
                if float(row.get('ui_contact_rate_limit_until') or 0) >= legacy - 601:
                    evidence.add(lane)
    if not evidence or shop in evidence:
        return max(own, legacy)
    return own
