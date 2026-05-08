#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.request import Request, urlopen


def fetch_json(url: str, method: str = "GET") -> dict[str, Any]:
    request = Request(url, method=method, data=b"" if method == "POST" else None)
    with urlopen(request, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--scan-type", choices=["fast", "deep"], default="deep")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    submit = fetch_json(f"https://api.portscan.com/v1/{args.scan_type}", method="POST")
    print(json.dumps({"submitted": submit}, ensure_ascii=False))

    deadline = time.time() + args.timeout_seconds
    result: dict[str, Any] | None = None
    while time.time() < deadline:
        result = fetch_json(f"https://api.portscan.com/v1/{args.scan_type}")
        status = str(result.get("status", ""))
        print(
            json.dumps(
                {
                    "poll": {
                        "status": status,
                        "chunks_complete": result.get("chunks_complete"),
                        "total_chunks": result.get("total_chunks"),
                    }
                },
                ensure_ascii=False,
            )
        )
        if status in {"complete", "failed", "none"}:
            break
        time.sleep(10)

    if result is None:
        raise SystemExit("port scan result unavailable")

    open_ports = [int(item.get("port")) for item in result.get("ports_open", []) if item.get("port") is not None]
    summary = {
        "ip": result.get("ip"),
        "scanType": args.scan_type,
        "status": result.get("status"),
        "port": args.port,
        "isOpen": args.port in open_ports,
        "openPorts": open_ports,
        "result": result,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
