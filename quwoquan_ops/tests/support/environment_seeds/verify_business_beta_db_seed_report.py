#!/usr/bin/env python3
"""校验业务对象 beta 报告是否证明数据库/缓存 seed 与 remote 读取。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_DOMAINS = ("content", "chat", "circle")
FORBIDDEN_MARKERS = (
    "ContentMockData",
    "ChatMockData",
    "CircleMockData",
    "PrototypeMockData",
    "MockContentRepository",
    "MockChatRepository",
    "MockCircleRepository",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify business beta DB/cache seed evidence report."
    )
    parser.add_argument("report", help="JSON report path")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"BLOCK: report not found: {report_path}", file=sys.stderr)
        return 1

    data = json.loads(report_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append("report.status must be passed")

    validate_domains(data.get("domains"), failures)
    validate_app_beta_runs(data.get("appBetaRuns"), failures)

    raw = json.dumps(data, ensure_ascii=False)
    for marker in FORBIDDEN_MARKERS:
        if marker in raw:
            failures.append(f"forbidden Dart mock marker found in beta report: {marker}")

    if failures:
        print("business beta DB seed report 校验失败:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("business beta DB seed report: OK")
    return 0


def validate_domains(domains: Any, failures: list[str]) -> None:
    if not isinstance(domains, dict):
        failures.append("missing domains object")
        return
    for domain in REQUIRED_DOMAINS:
        item = domains.get(domain)
        if not isinstance(item, dict):
            failures.append(f"missing domains.{domain}")
            continue
        if not item.get("seedRefs"):
            failures.append(f"domains.{domain}.seedRefs is required")
        if not item.get("resetScope"):
            failures.append(f"domains.{domain}.resetScope is required")
        if not item.get("targetStore"):
            failures.append(f"domains.{domain}.targetStore is required")
        inserted = item.get("insertedCount")
        if not isinstance(inserted, int) or inserted <= 0:
            failures.append(f"domains.{domain}.insertedCount must be > 0")
        endpoints = item.get("verifiedEndpoints")
        if not isinstance(endpoints, list) or not endpoints:
            failures.append(f"domains.{domain}.verifiedEndpoints is required")


def validate_app_beta_runs(runs: Any, failures: list[str]) -> None:
    if not isinstance(runs, list) or not runs:
        failures.append("appBetaRuns is required")
        return
    for idx, run in enumerate(runs):
        if not isinstance(run, dict):
            failures.append(f"appBetaRuns[{idx}] must be object")
            continue
        if run.get("dataSource") != "remote":
            failures.append(f"appBetaRuns[{idx}].dataSource must be remote")
        if not run.get("gatewayBaseUrl"):
            failures.append(f"appBetaRuns[{idx}].gatewayBaseUrl is required")
        if not run.get("httpEvidence"):
            failures.append(f"appBetaRuns[{idx}].httpEvidence is required")


if __name__ == "__main__":
    raise SystemExit(main())
