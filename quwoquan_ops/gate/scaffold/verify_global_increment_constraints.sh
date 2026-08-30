#!/usr/bin/env bash
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] global increment constraints"

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path.cwd()
scan_files = [root / "AGENTS.md", root / "specs/feature-tree/README.md"]
scan_files.extend((root / ".cursor/commands").glob("*.md"))
scan_files.extend((root / ".cursor/rules").glob("*.mdc"))
# 阶段语义与角色清单已迁到 Cursor/Codex 共享层，退役词汇必须同样在这里阻断
scan_files.extend((root / ".agents/skills").rglob("*.md"))

forbidden_terms = (
    r"\bL1_capability\b", r"\bL2_feature\b", r"\bL2_journey\b",
    r"\bL3_scenario\b", r"\bL4_(?:detail|story|object_task)\b", r"\bL5_\w+\b",
)
forbidden_paths = (
    "specs/feature-tree/tree_index.yaml", "specs/feature-tree/journey_scenario_registry.yaml",
    "specs/l1_index.yaml", "specs/engineering_directory_manifest.yaml", "specs/changelog",
    "specs/gates", "docs/outstanding_risks_backlog.md",
    "specs/00_AGENT_MASTER_SPEC.md", "specs/00_MASTER_DEVELOPMENT_FLOW.md",
    "docs/agent_context_contract.md", "docs/agent_command_simulation_matrix.md",
    "docs/codex_workflow.md", "docs/commercial_maturity_master_plan.md",
    "docs/functional_module_commercial_maturity_matrix.md",
    "quwoquan_ops/policies/config-release/reports",
    "quwoquan_ops/policies/config-release/runbook.md",
    "quwoquan_ops/policies/config-release/high_risk_fields.yaml",
    "quwoquan_ops/policies/gates/contract_graph_commercial_failure_baseline.json",
    "quwoquan_ops/policies/gates/lib_test_only_symbols_allowlist.yaml",
    "quwoquan_ops/policies/gates/ios_native_surface_allowlist.yaml",
    "quwoquan_ops/policies/gates/lib_platform_check_allowlist.yaml",
    "quwoquan_ops/policies/gates/page_abc_governance_allowlist.yaml",
)
violations: list[str] = []
for path in scan_files:
    if not path.is_file():
        violations.append(f"missing {path.relative_to(root)}")
        continue
    text = path.read_text(encoding="utf-8")
    for pattern in forbidden_terms:
        for match in re.finditer(pattern, text):
            violations.append(f"{path.relative_to(root)}:{text.count(chr(10), 0, match.start()) + 1}: retired term {match.group(0)}")

for rel in forbidden_paths:
    if (root / rel).exists():
        violations.append(f"forbidden global ledger exists: {rel}")

standard = (root / "specs/feature-tree/README.md").read_text(encoding="utf-8")
for term in ("L1 Domain Service", "L2 Business Capability", "L3 Story", "UAT", "DOM", "SIT", "GWT", "local_contract", "api_integration", "user_acceptance", "OPEN"):
    if term not in standard:
        violations.append(f"feature-tree README missing {term}")

if violations:
    print("[verify] FAIL: global increment constraints regressed", file=sys.stderr)
    for item in violations:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)
print("[verify] OK: directory-native feature and test vocabulary")
PY
