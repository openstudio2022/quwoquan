#!/usr/bin/env python3
"""Verify five-domain object-level generated Remote API integration evidence.

Coverage is derived from the committed ContractGraph. The baseline stores only
per-domain count floors; object and test paths remain ContractGraph-owned.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.domain_remote_api_integration import (  # noqa: E402
    GOVERNED_DOMAINS,
    discover_cases,
    evidence_counts,
    validate_cases,
)


BASELINE_PATH = (
    ROOT
    / "quwoquan_ops"
    / "policies"
    / "gates"
    / "app_domain_remote_api_integration_baseline.json"
)
BASELINE_SCHEMA = "app-domain-remote-api-integration-baseline"
RULE_ID = "app-domain-remote-api-integration-ratchet"
COUNT_FIELDS = (
    "coveredObjectCount",
    "appTestFileCount",
    "serviceTestFileCount",
)


def load_baseline() -> dict:
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if document.get("schema") != BASELINE_SCHEMA:
        raise ValueError(f"baseline schema mismatch: {document.get('schema')!r}")
    if document.get("ruleId") != RULE_ID:
        raise ValueError(f"baseline ruleId mismatch: {document.get('ruleId')!r}")
    domains = document.get("domains")
    if not isinstance(domains, dict):
        raise ValueError("baseline domains must be an object")
    return document


def evaluate(counts: dict[str, dict[str, int]], baseline: dict) -> list[str]:
    failures: list[str] = []
    recorded = baseline.get("domains") or {}
    unknown = sorted(set(recorded) - set(GOVERNED_DOMAINS))
    missing = sorted(set(GOVERNED_DOMAINS) - set(recorded))
    failures += [f"baseline 含未知 domain: {item}" for item in unknown]
    failures += [f"baseline 缺少 domain: {item}" for item in missing]
    for domain in GOVERNED_DOMAINS:
        floor = recorded.get(domain)
        if not isinstance(floor, dict):
            continue
        for field in COUNT_FIELDS:
            minimum = int(floor.get(field, -1))
            if minimum < 1:
                failures.append(f"{domain}: baseline 缺少正数 {field}")
                continue
            current = int(counts[domain][field])
            if current < minimum:
                failures.append(
                    f"{domain}: {field} 下降 {current} < 基线 {minimum}"
                )
    return failures


def write_baseline(counts: dict[str, dict[str, int]]) -> None:
    try:
        payload = load_baseline()
    except FileNotFoundError:
        payload = {
            "_governance": {
                "owner": "cloud-contract-governance",
                "reason": "五域对象级 generated Remote API integration 证据只增不减",
                "expires_when": "本棘轮完全并入 ContractGraph object evidence 门禁",
            },
            "schema": BASELINE_SCHEMA,
            "ruleId": RULE_ID,
            "domains": {},
        }
    recorded = payload.setdefault("domains", {})
    for domain, current in counts.items():
        previous = recorded.get(domain)
        if isinstance(previous, dict):
            for field in COUNT_FIELDS:
                old_value = int(previous.get(field, 0))
                if int(current[field]) < old_value:
                    raise RuntimeError(
                        f"{domain}: 拒绝降低 {field} 基线 "
                        f"{current[field]} < {old_value}"
                    )
        recorded[domain] = dict(current)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def current_evidence() -> tuple[dict[str, dict[str, int]], list[str]]:
    cases, discovery_issues = discover_cases(ROOT)
    validated, validation_issues = validate_cases(ROOT, cases)
    return evidence_counts(validated), [*discovery_issues, *validation_issues]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="仅接受实测覆盖增加，不得吸收下降",
    )
    args = parser.parse_args(argv)
    try:
        counts, source_issues = current_evidence()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            f"verify_app_domain_remote_api_integration: GATE_BLOCK: {error}",
            file=sys.stderr,
        )
        return 2
    if source_issues:
        print("verify_app_domain_remote_api_integration: BLOCK", file=sys.stderr)
        for issue in source_issues:
            print(f"  {issue}", file=sys.stderr)
        print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
        return 1
    if args.update_baseline:
        try:
            write_baseline(counts)
        except (RuntimeError, ValueError) as error:
            print(
                f"verify_app_domain_remote_api_integration: GATE_BLOCK: {error}",
                file=sys.stderr,
            )
            return 2
        print(
            "verify_app_domain_remote_api_integration: wrote baseline -> "
            f"{BASELINE_PATH}"
        )
        print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
        return 0
    try:
        baseline = load_baseline()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(
            f"verify_app_domain_remote_api_integration: BLOCK: {error}",
            file=sys.stderr,
        )
        return 2
    failures = evaluate(counts, baseline)
    if failures:
        print("verify_app_domain_remote_api_integration: BLOCK", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
        return 1
    print(
        "verify_app_domain_remote_api_integration: "
        f"OK ({len(GOVERNED_DOMAINS)} domains)"
    )
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
