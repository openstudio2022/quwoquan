#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[verify] global increment constraints"

python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path.cwd()
scan_files = [root / "specs/00_MASTER_DEVELOPMENT_FLOW.md"]
scan_files.extend((root / ".cursor/commands").glob("*.md"))
scan_files.extend((root / ".cursor/rules").glob("*.mdc"))

for path in scan_files:
    if not path.exists():
        print(f"[verify] FAIL: missing {path.relative_to(root)}", file=sys.stderr)
        sys.exit(1)

forbidden = [
    r"\bL1_capability\b",
    r"\bL2_feature\b",
    r"\bL2_journey\b",
    r"\bL3_scenario\b",
    r"\bplan\.yaml\b",
    r"\btasks\.md\b",
    r"\bplan slice\b",
    r"\bplan slices\b",
    r"\bjourney_acceptance\b",
    r"\bscenario_acceptance\b",
]

violations: list[str] = []
for path in sorted(scan_files):
    text = path.read_text(encoding="utf-8")
    for pattern in forbidden:
        for match in re.finditer(pattern, text):
            line_no = text.count("\n", 0, match.start()) + 1
            rel = path.relative_to(root)
            violations.append(f"{rel}:{line_no}: forbidden retired term {match.group(0)!r}")

required_master_terms = [
    "L1_domain_service",
    "L2_business_capability",
    "L3_story",
    "UAT",
    "SIT",
    "GWT",
    "contract",
    "local_contract",
    "api_integration",
    "user_acceptance",
]
master = (root / "specs/00_MASTER_DEVELOPMENT_FLOW.md").read_text(encoding="utf-8")
for term in required_master_terms:
    if term not in master:
        violations.append(f"specs/00_MASTER_DEVELOPMENT_FLOW.md: missing required term {term!r}")

if violations:
    print("[verify] FAIL: global increment constraints regressed", file=sys.stderr)
    for item in violations:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)

print("[verify] OK: command/rule/master docs use the new tree and test model")
PY
