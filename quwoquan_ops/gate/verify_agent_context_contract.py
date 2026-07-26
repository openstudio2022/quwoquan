#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FILES = (
    "AGENTS.md", "specs/feature-tree/README.md", "specs/feature-tree/spec.md",
    "specs/feature-tree/design.md", "quwoquan_ops/cli/feature_tree.py",
    "quwoquan_app/AGENTS.md", "quwoquan_service/AGENTS.md", "quwoquan_data/AGENTS.md",
    "quwoquan_ops/AGENTS.md", "quwoquan_ops/portal/AGENTS.md",
)
KEY_COMMANDS = ("explore", "prd", "design", "baseline", "extend", "dev", "verify", "plan-review", "plan-next", "continue-dev")


def main() -> int:
    issues: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            issues.append(f"missing required context source: {rel}")
    root_agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for token in ("Spec Entry", "Pre-work Reflection", "Exit Review", "自然语言", "Data -> Service -> App", "make feature-context", "OPEN"):
        if token not in root_agents:
            issues.append(f"AGENTS.md missing {token}")
    standard = (ROOT / "specs/feature-tree/README.md").read_text(encoding="utf-8")
    for token in ("目录结构就是树", "Agent 最小阅读链", "动态工具", "自动门禁"):
        if token not in standard:
            issues.append(f"feature-tree README missing {token}")
    for name in KEY_COMMANDS:
        path = ROOT / ".cursor" / "commands" / f"{name}.md"
        if not path.is_file():
            issues.append(f"missing command: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if "自然语言等价触发" not in text:
            issues.append(f"{path.relative_to(ROOT)} missing natural-language trigger")
    retired = ("agent_context_contract.md", "agent_command_simulation_matrix.md", "docs/codex_workflow.md", "00_MASTER_DEVELOPMENT_FLOW.md")
    for path in [ROOT / "AGENTS.md", *sorted((ROOT / ".cursor/commands").glob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        for token in retired:
            if token in text:
                issues.append(f"{path.relative_to(ROOT)} references retired governance source {token}")
    if issues:
        print("[verify_agent_context_contract] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[verify_agent_context_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
