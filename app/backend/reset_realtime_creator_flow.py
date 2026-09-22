from __future__ import annotations

import argparse
import json
from pathlib import Path

from realtime_creator_flow import RealtimeCreatorFlowStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset selected realtime flow records for a verified retry.")
    parser.add_argument("flow")
    parser.add_argument("--state", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--reset-reason", required=True)
    args = parser.parse_args()

    store = RealtimeCreatorFlowStore(Path(args.flow).resolve())
    identities = [
        str(record.get("identity") or "")
        for record in store.rows()
        if str(record.get("state") or "") == args.state
        and (not args.reason or str(record.get("reason") or "") == args.reason)
    ]
    reset = store.reset_for_retry(identities, reason=args.reset_reason)
    print(json.dumps({"status": "realtime_flow_reset", "reset_count": reset}, ensure_ascii=False))


if __name__ == "__main__":
    main()
