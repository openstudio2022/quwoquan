"""Gate content-supply production contracts to one canonical source.

This module is imported by `qwq-data verify single-contract-source`.  It is not
an executable business entrypoint.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"

SCAN_PATHS = [
    DATA_ROOT / "schema/execution",
    DATA_ROOT / "schema/content",
    DATA_ROOT / "schema/release",
    DATA_ROOT / "scripts/content",
    DATA_ROOT / "scripts/core/content_plan.py",
    DATA_ROOT / "scripts/core/command_packet.py",
    DATA_ROOT / "scripts/verify/verify_content_execution_production.py",
    DATA_ROOT / "scripts/verify/handler.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"object_job_v\d+", re.IGNORECASE),
    re.compile(r"AgentResultEnvelopeV\d+"),
    re.compile(r"GateVerdictV\d+"),
    re.compile(r"TokenLedgerV\d+"),
    re.compile(r"ObjectJobV\d+"),
    re.compile(r"separated_v\d+", re.IGNORECASE),
    re.compile(
        r"quwoquan\.(?:content_supply\.task|content_supply\.prep_report|content_supply\.delta_plan|"
        r"object_job|agent_result_envelope|gate_verdict|token_ledger|download_repair)/\d+"
    ),
    re.compile(r"quwoquan_data\.batch_manifest/\d+"),
    re.compile(r"quwoquan\.batch\.manifest/\d+"),
    re.compile(r"quwoquan\.download_repair\.old"),
    re.compile(r"quwoquan\.data\.packet\.v\d+"),
    re.compile(r"quwoquan_data\.content_plan_packet/\d+"),
    re.compile(r"quwoquan_data\.fanout_run_matrix/\d+"),
    re.compile("payloadAllowlist" + "Version"),
    re.compile(r"\bcontent[-_ ]supply\b[^\n]*(?:\bv1\b|\bv2\b)", re.IGNORECASE),
]


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for path in SCAN_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.is_file())
    return files


def main() -> int:
    issues: list[str] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT)
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                issues.append(f"{rel}:{line}: forbidden versioned content-supply contract marker: {match.group(0)!r}")

    payload = {"passed": not issues, "gate": "single_contract_source", "issues": issues[:200]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if issues:
        return 1
    return 0
