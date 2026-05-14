#!/usr/bin/env python3
"""校验助手 beta 报告是否证明真实模型与搜索链路。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_MARKERS = {
    "fake_web_search",
    "mock_search",
    "ScenarioMockAssistantRepository",
    "alphaMockStream",
    "DeterministicModelProvider",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify assistant beta real model/search evidence report."
    )
    parser.add_argument("report", help="JSON report path")
    parser.add_argument("--log", action="append", default=[], help="Extra log file to scan")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"BLOCK: report not found: {report_path}", file=sys.stderr)
        return 1

    data = json.loads(report_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if data.get("status") == "gate_block":
        print(data.get("failureReason", "GATE_BLOCK: assistant beta real chain blocked"))
        return 2
    if data.get("status") != "passed":
        failures.append("report.status must be passed")

    beta_runs = [run for run in data.get("runs", []) if run.get("env") == "beta"]
    if not beta_runs:
        failures.append("missing beta run")

    for run in beta_runs:
        command_text = " ".join(str(item) for item in run.get("command", []))
        if "APP_DATA_SOURCE=remote" not in command_text:
            failures.append("beta command must include APP_DATA_SOURCE=remote")
        if run.get("gatewayBaseUrl", "") == "":
            failures.append("beta run must include gatewayBaseUrl")

    evidence = data.get("realChainEvidence", {})
    validate_real_chain_evidence(evidence, failures)

    combined = json.dumps(data, ensure_ascii=False)
    for log_path in [Path(item) for item in args.log]:
        if log_path.is_file():
            combined += "\n" + log_path.read_text(encoding="utf-8", errors="replace")
        else:
            failures.append(f"log not found: {log_path}")

    for marker in FORBIDDEN_MARKERS:
        if marker in combined:
            failures.append(f"forbidden beta fake/mock marker found: {marker}")

    if failures:
        print("assistant beta real chain report 校验失败:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("assistant beta real chain report: OK")
    return 0


def validate_real_chain_evidence(evidence: Any, failures: list[str]) -> None:
    if not isinstance(evidence, dict):
        failures.append("missing realChainEvidence object")
        return
    required = {
        "runIds": list,
        "turnIds": list,
        "seedRefs": list,
        "toolCalls": list,
        "searchProvider": str,
        "modelProvider": str,
        "answerFragments": list,
    }
    for key, typ in required.items():
        value = evidence.get(key)
        if not isinstance(value, typ) or (isinstance(value, (list, str)) and not value):
            failures.append(f"realChainEvidence.{key} is required")
    if evidence.get("searchProvider", "").startswith(("fake", "mock")):
        failures.append("searchProvider must be real, not fake/mock")
    if evidence.get("modelProvider", "").startswith(("fake", "mock", "deterministic")):
        failures.append("modelProvider must be real, not fake/mock/deterministic")


if __name__ == "__main__":
    raise SystemExit(main())
