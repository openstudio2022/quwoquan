#!/usr/bin/env python3
"""Require retired orchestration directories and references to be physically absent."""
from __future__ import annotations

from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
RETIRED_PATHS = (
    "content/source/research/scale_source_pool.py",
    "content/source/research/handler_cli.py",
    "content/homepage",
    "content/post",
    "content/review",
    "content/release/canonical/publish_execution.py",
    "content/release/canonical/pool_precheck.py",
    "content/release/canonical/pool_inspection.py",
    "content/release/canonical/semantic_wave_dispatch.py",
    "content/release/canonical/supply_chain_drill.py",
)
FORBIDDEN_IMPORTS = (
    "content.execution.planning", "content.execution.campaign", "content.execution.source_pool",
    "content.execution.runtime_state", "content.execution.stage_reports", "content.execution.model_contract",
)


def architecture_issues() -> list[str]:
    issues = [f"retired path still exists: {rel}" for rel in RETIRED_PATHS if (SCRIPTS_ROOT / rel).exists()]
    for root_name in ("content/source", "content/release", "verify", "core"):
        root = SCRIPTS_ROOT / root_name
        if not root.is_dir(): continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path.name in {"verify_script_architecture.py", "verify_public_cli_live_import_zero.py"}:
                continue
            for token in FORBIDDEN_IMPORTS:
                if token in text:
                    issues.append(f"{path.relative_to(SCRIPTS_ROOT)}: retired import {token}")
    return issues


def main() -> int:
    issues = architecture_issues()
    if issues:
        print("[verify script-architecture] FAIL")
        for issue in issues: print(f"  - {issue}")
        return 1
    print("[verify script-architecture] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
