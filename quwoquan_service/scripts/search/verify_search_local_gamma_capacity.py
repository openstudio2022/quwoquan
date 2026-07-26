#!/usr/bin/env python3
"""R-S06-S-1 local-gamma capacity/repeatability verifier.

该脚本只验证 local-gamma 能验证的部分：

- search-service / ES / Redis 栈健康；
- local 单节点 ES 拓扑、索引文档数、yellow/green 状态原因；
- 小型 warm/cold/mixed/feedback 并发压测（复用 search_load_benchmark.py）；
- 同 query repeatability golden（单节点）；
- 已有故障/回滚演练证据是否存在。

重要：local-gamma 在 Apple Silicon/Colima 上可能是 linux/amd64 单节点模拟 ES，
不能替代 prod-sim/真集群 measured 容量。脚本会把结论写成
`r_s06_s1_closed_by_local_gamma=false`，避免误关 backlog。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = Path(os.environ.get("QWQ_OUTPUT_ROOT", ROOT / ".qwq_output"))
DEFAULT_OUT = (
    OUTPUT_ROOT
    / "env"
    / "gamma"
    / "observability"
    / "search-capacity"
    / "search_r_s06_s1_local_gamma_report.json"
)
DEFAULT_LOAD_DIR = OUTPUT_ROOT / "env" / "gamma" / "observability" / "search-load" / "local-gamma"
DEFAULT_ROLLBACK_JSON = (
    OUTPUT_ROOT
    / "env"
    / "gamma"
    / "observability"
    / "search-rollback"
    / "search_rollback_rehearsal_report.json"
)
DEFAULT_ROLLBACK_MARKDOWN = (
    OUTPUT_ROOT / "env" / "gamma" / "runs" / "search_rollback_rehearsal.md"
)
SEARCH_BASE = "http://127.0.0.1:19280"
ES_BASE = "http://127.0.0.1:19430"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], timeout: int = 120) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "exit_code": proc.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-3000:],
    }


def http_json(url: str, timeout: float = 5.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
            return {"ok": True, "status": resp.status, "payload": payload}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return {"ok": False, "status": exc.code, "payload": raw[:500]}
    except Exception as exc:
        return {"ok": False, "status": None, "error": f"{type(exc).__name__}: {exc}"}


def post_search(query: str = "成都", limit: int = 5) -> dict:
    body = json.dumps(
        {
            "query": query,
            "mode": "result",
            "objectTypes": ["article", "entity", "location"],
            "limit": limit,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        SEARCH_BASE + "/search",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-User-Id": "fixture_user_current",
            "X-Session-Id": "local-gamma-capacity",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            hits = payload.get("hits") or []
            return {
                "ok": True,
                "status": resp.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "hit_count": len(hits),
                "top_keys": [
                    f"{h.get('target') or h.get('objectType')}:{h.get('objectId')}"
                    for h in hits
                ],
                "provider": (payload.get("provenance") or {}).get("provider"),
                "rankingVersion": payload.get("rankingVersion"),
                "experimentBucket": payload.get("experimentBucket"),
            }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_load(out_dir: Path, duration: int, concurrency: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "quwoquan_service/scripts/search/search_load_benchmark.py"),
        "--base-url",
        SEARCH_BASE,
        "--duration-sec",
        str(duration),
        "--concurrency",
        str(concurrency),
        "--out-dir",
        str(out_dir),
        "--scenario",
        "all",
    ]
    return run(cmd, timeout=max(180, duration * 8))


def load_latest_json(out_dir: Path) -> dict | None:
    files = sorted(out_dir.glob("search_load_all_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    with files[-1].open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    data["_source"] = str(files[-1])
    return data


def repeatability(query: str, attempts: int) -> dict:
    rows = [post_search(query=query) for _ in range(attempts)]
    keys = [r.get("top_keys") for r in rows if r.get("ok")]
    first = keys[0] if keys else []
    mismatches = [
        {"index": i, "top_keys": k}
        for i, k in enumerate(keys)
        if k != first
    ]
    buckets = sorted({r.get("experimentBucket") for r in rows if r.get("ok")})
    return {
        "query": query,
        "attempts": attempts,
        "ok_count": len(keys),
        "first_top_keys": first,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:10],
        "experiment_buckets": buckets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--duration", type=int, default=6)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--repeat", type=int, default=25)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    load_dir = DEFAULT_LOAD_DIR

    report: dict = {
        "kind": "search_r_s06_s1_local_gamma_capacity",
        "env": "local-gamma",
        "started_at": now(),
        "r_s06_s1_closed_by_local_gamma": False,
        "scope_statement": {
            "can_verify": [
                "local stack health",
                "single-node ES topology/index state",
                "small local warm/cold/mixed/feedback load behavior",
                "single-node repeatability",
                "failure/rollback evidence presence",
            ],
            "cannot_replace": [
                "prod-sim/real-cluster measured RPS/P95/P99",
                "multi-data-node shard/replica sizing",
                "multi-replica preference validation",
                "production filesystem cache/heap/GC/threadpool saturation point",
            ],
        },
        "inputs": {
            "search_base": SEARCH_BASE,
            "es_base": ES_BASE,
            "duration": args.duration,
            "concurrency": args.concurrency,
            "repeat": args.repeat,
        },
    }

    report["stackctl_verify"] = run(
        [
            sys.executable,
            "quwoquan_ops/cli/stackctl.py",
            "verify",
            "--env",
            "gamma",
            "--kind",
            "all",
            "--profile",
            "release",
        ],
        timeout=180,
    )
    report["search_healthz"] = http_json(SEARCH_BASE + "/healthz")
    report["es_health"] = http_json(ES_BASE + "/_cluster/health?pretty=false")
    report["es_indices"] = http_json(ES_BASE + "/_cat/indices/quwoquan_objects?format=json&bytes=b")
    report["es_shards"] = http_json(ES_BASE + "/_cat/shards/quwoquan_objects?format=json")
    report["es_thread_pool_search"] = http_json(ES_BASE + "/_cat/thread_pool/search?format=json")
    report["baseline_probe"] = post_search("成都")

    report["load_run"] = run_load(load_dir, args.duration, args.concurrency)
    report["load_summary"] = load_latest_json(load_dir)
    report["repeatability"] = repeatability("成都", args.repeat)

    rollback_json = DEFAULT_ROLLBACK_JSON
    rollback_md = DEFAULT_ROLLBACK_MARKDOWN
    report["rollback_evidence"] = {
        "json_exists": rollback_json.exists(),
        "json_path": str(rollback_json),
        "md_exists": rollback_md.exists(),
        "md_path": str(rollback_md),
    }

    checks = {
        "stackctl_verify_ok": report["stackctl_verify"]["exit_code"] == 0,
        "search_health_ok": report["search_healthz"].get("status") == 200,
        "baseline_search_ok": report["baseline_probe"].get("ok") is True,
        "load_script_ok": report["load_run"]["exit_code"] == 0,
        "repeatability_zero_mismatch": (
            report["repeatability"]["ok_count"] == args.repeat
            and report["repeatability"]["mismatch_count"] == 0
        ),
        "rollback_evidence_present": rollback_json.exists() and rollback_md.exists(),
    }
    report["checks"] = checks
    report["local_gamma_result"] = "passed" if all(checks.values()) else "failed"
    report["finished_at"] = now()

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({
        "out": str(out_path),
        "local_gamma_result": report["local_gamma_result"],
        "r_s06_s1_closed_by_local_gamma": False,
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if report["local_gamma_result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
