#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    "AGENTS.md",
    "docs/agent_context_contract.md",
    "docs/agent_command_simulation_matrix.md",
    "docs/codex_workflow.md",
    "quwoquan_app/AGENTS.md",
    "quwoquan_service/AGENTS.md",
    "quwoquan_data/AGENTS.md",
    "agent_ops/AGENTS.md",
    "apps/ops-portal/AGENTS.md",
]

CONTEXT_REFERENCES = [
    "AGENTS.md",
    "docs/codex_workflow.md",
    ".cursor/commands/audit.md",
    ".cursor/commands/dev.md",
    ".cursor/commands/verify.md",
    ".cursor/commands/deliver.md",
    ".cursor/commands/commit.md",
    ".cursor/commands/deploy.md",
]

DATA_COMMAND_FILES = [
    ".cursor/commands/data-baseline.md",
    ".cursor/commands/data-build-entities-tags.md",
    ".cursor/commands/data-source-fetch.md",
    ".cursor/commands/data-trace-source.md",
    ".cursor/commands/crawl.md",
    ".cursor/commands/crawl-topic.md",
]

KEY_COMMAND_FILES = [
    ".cursor/commands/explore.md",
    ".cursor/commands/prd.md",
    ".cursor/commands/design.md",
    ".cursor/commands/baseline.md",
    ".cursor/commands/extend.md",
    ".cursor/commands/dev.md",
    ".cursor/commands/verify.md",
    ".cursor/commands/plan-review.md",
    ".cursor/commands/plan-next.md",
    ".cursor/commands/audit.md",
    ".cursor/commands/deliver.md",
    ".cursor/commands/commit.md",
    ".cursor/commands/deploy.md",
    ".cursor/commands/infra.md",
    ".cursor/commands/obs.md",
    ".cursor/commands/rec.md",
]

SIMULATION_COMMAND_TOKENS = [
    "/explore",
    "/prd",
    "/design",
    "/baseline",
    "/extend",
    "/dev",
    "/verify",
    "/plan-review",
    "/plan-next",
    "/audit",
    "/deliver",
    "/commit",
    "/deploy",
    "/infra",
    "/obs",
    "/rec",
    "data-baseline",
    "data-build-entities-tags",
    "crawl",
    "crawl-topic",
]


def read_rel(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    issues: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            issues.append(f"missing required agent context file: {rel}")

    for rel in CONTEXT_REFERENCES:
        path = ROOT / rel
        if path.is_file() and "docs/agent_context_contract.md" not in read_rel(rel):
            issues.append(f"{rel} must reference docs/agent_context_contract.md")

    contract_text = read_rel("docs/agent_context_contract.md")
    for token in ("Spec Entry", "Pre-work Reflection", "Exit Review", "Cursor voice", "Codex voice"):
        if token not in contract_text:
            issues.append(f"docs/agent_context_contract.md missing execution protocol token: {token}")
    if "docs/agent_command_simulation_matrix.md" not in contract_text:
        issues.append("docs/agent_context_contract.md must reference docs/agent_command_simulation_matrix.md")

    simulation_text = read_rel("docs/agent_command_simulation_matrix.md")
    for token in SIMULATION_COMMAND_TOKENS:
        if token not in simulation_text:
            issues.append(f"docs/agent_command_simulation_matrix.md missing command token: {token}")
    for token in ("Cursor 执行视角", "Codex 执行视角", "Simulation Cases", "最小验证命令"):
        if token not in simulation_text:
            issues.append(f"docs/agent_command_simulation_matrix.md missing section/token: {token}")

    root_agents = read_rel("AGENTS.md") if (ROOT / "AGENTS.md").is_file() else ""
    for token in ("自然语言", "端到端模式", "Data -> Service -> App", "Spec Entry", "Pre-work Reflection", "Exit Review", "docs/agent_command_simulation_matrix.md"):
        if token not in root_agents:
            issues.append(f"AGENTS.md missing context routing token: {token}")

    workflow_text = read_rel("docs/codex_workflow.md")
    for token in ("docs/agent_command_simulation_matrix.md", "Spec Entry", "Pre-work Reflection", "Exit Review", "Codex voice"):
        if token not in workflow_text:
            issues.append(f"docs/codex_workflow.md missing workflow token: {token}")

    dev_text = read_rel(".cursor/commands/dev.md")
    for token in ("正向规格理解", "执行前自检反思", "自然语言等价触发"):
        if token not in dev_text:
            issues.append(f".cursor/commands/dev.md missing {token}")

    verify_text = read_rel(".cursor/commands/verify.md")
    for token in ("完成后多视角验收复盘", "Data / Service / App", "自然语言等价触发"):
        if token not in verify_text:
            issues.append(f".cursor/commands/verify.md missing {token}")

    deploy_text = read_rel(".cursor/commands/deploy.md")
    for token in ("stackctl.py verify", "prod-hosted", "不存在 `prod-gray`"):
        if token not in deploy_text:
            issues.append(f".cursor/commands/deploy.md missing deploy context token: {token}")

    infra_text = read_rel(".cursor/commands/infra.md")
    for token in ("alpha|beta|gamma|prod", "stackctl.py verify", "自然语言等价触发"):
        if token not in infra_text:
            issues.append(f".cursor/commands/infra.md missing infra context token: {token}")

    for rel in DATA_COMMAND_FILES:
        text = read_rel(rel)
        if "quwoquan_data/tools/cli.py" in text:
            issues.append(f"{rel} must use quwoquan_data/scripts/cli.py, not tools/cli.py")
        if "自然语言等价触发" not in text:
            issues.append(f"{rel} missing natural-language trigger note")

    for rel in KEY_COMMAND_FILES:
        text = read_rel(rel)
        if "自然语言等价触发" not in text:
            issues.append(f"{rel} missing natural-language trigger note")
        if not any(token in text for token in ("出口", "产出：", "输出：")):
            issues.append(f"{rel} missing exit/output section")

    for path in sorted((ROOT / ".cursor/commands").iterdir()):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "自然语言等价触发" not in text:
            issues.append(f"{rel} missing natural-language trigger note")
        for token in ("Spec Entry", "Pre-work Reflection", "Exit Review"):
            if token not in text:
                issues.append(f"{rel} missing execution protocol token: {token}")

    for rel in (
        "quwoquan_app/AGENTS.md",
        "quwoquan_service/AGENTS.md",
        "quwoquan_data/AGENTS.md",
        "agent_ops/AGENTS.md",
        "apps/ops-portal/AGENTS.md",
    ):
        text = read_rel(rel)
        if "典型触发" not in text:
            issues.append(f"{rel} missing typical trigger section")
        if "E2E" not in text:
            issues.append(f"{rel} missing E2E linkage")

    rule_text = read_rel(".cursor/rules/00-fullstack-development-flow.mdc")
    for token in ("docs/agent_context_contract.md", "完成后复盘", "跨 App / Service / Data / Ops / Portal"):
        if token not in rule_text:
            issues.append(f".cursor/rules/00-fullstack-development-flow.mdc missing {token}")

    arch_text = read_rel(".cursor/rules/01-arch-constraints.mdc")
    if "contracts/error_codes.md" in arch_text:
        issues.append(".cursor/rules/01-arch-constraints.mdc must not point error codes to contracts/error_codes.md")
    if "contracts/metadata/{domain}/{entity}/errors.yaml" not in arch_text:
        issues.append(".cursor/rules/01-arch-constraints.mdc must point error codes to metadata errors.yaml")

    if issues:
        print("[verify_agent_context_contract] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print("[verify_agent_context_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
