#!/usr/bin/env python3
"""渐进加载 Agent 上下文治理门禁。

每次 ``make verify-agent-context-budget`` 都检查全仓 Agent 治理载体；任一预算、
唯一 owner、Review v2、adapter 或退役入口约束不成立即以非零退出阻断。修复应落到
报错指向的 canonical spec/design、registry/checklist、Skill 或中性 adapter 源，再重跑
同一入口。功能事实和角色判断不在本 gate 复制。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_ROOT = ROOT

sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))
from gate_output import emit_gate_result, finding  # noqa: E402


AGENTS_CHAIN_BYTE_BUDGET = 16 * 1024
MANIFEST_BYTE_BUDGET = 8 * 1024
REVIEWER_CONTEXT_BYTE_BUDGET = 24 * 1024
SKILL_LINE_BUDGET = 500
SKILL_DESCRIPTION_EACH_BUDGET = 500
SKILL_DESCRIPTION_TOTAL_BUDGET = 8000
COMMAND_FILE_LINE_BUDGET = 12
HARNESS_STUB_LINE_BUDGET = 12

PRUNED_DIR_NAMES = {
    ".git",
    ".qwq_output",
    "node_modules",
    ".dart_tool",
    ".pub-cache",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
}

WORKFLOW_SKILLS = (
    "explore",
    "prd",
    "design",
    "dev",
    "continue",
    "plan-next",
    "review",
    "commit",
    "environment-ops",
    "content-production",
    "incident-inspection",
    "distill",
)
COMMAND_BOUND_WORKFLOWS = (
    "explore",
    "prd",
    "design",
    "dev",
    "continue",
    "plan-next",
    "review",
    "commit",
)
CONTROL_WORKFLOWS_WITHOUT_AUTOMATIC_REVIEW = {
    "explore",
    "continue",
    "plan-next",
    "review",
    "commit",
}
REQUIRED_SKILL_SECTIONS = (
    "触发与输入",
    "执行",
    "完成证据",
    "失败与停止",
    "条件性交接",
)

SPEC_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
REQUIRED_SOURCES = (
    "AGENTS.md",
    ".agents/README.md",
    "specs/feature-tree/README.md",
    "specs/feature-tree/spec.md",
    "specs/feature-tree/design.md",
    "quwoquan_ops/cli/feature_tree.py",
    "quwoquan_ops/cli/lib/feature_tree/commands.py",
    "quwoquan_ops/cli/lib/agent_governance_contract.py",
    "quwoquan_ops/cli/lib/evidence_fingerprint.py",
    "quwoquan_ops/cli/lib/feature_context_fingerprint.py",
    "quwoquan_ops/cli/evidence_runner.py",
    "quwoquan_ops/cli/handoff_manifest.py",
    "quwoquan_ops/policies/agent_governance_contract.yaml",
    "quwoquan_ops/cli/lib/human_agent_delivery/contract.py",
    "quwoquan_ops/policies/human_agent_delivery_contract.yaml",
    ".agents/skills/review/references/registry.yaml",
    ".agents/skills/review/references/reviewer-executor.md",
    "quwoquan_ops/tools/generate_agent_adapters.py",
    ".cursor/agents/reviewer.md",
    ".codex/agents/reviewer.toml",
)
FORBIDDEN_ACTIVE_PATHS = (
    "CLAUDE.md",
    ".claude",
    "quwoquan_ops/tools/generate_codex_agents.py",
    ".agents/skills/review/references/completion-criteria.md",
    ".agents/skills/review/references/interaction-protocols.md",
)
RETIRED_REFERENCE_TOKENS = (
    "skills/review-board",
    "skills/stage-explore",
    "skills/stage-prd",
    "skills/stage-design",
    "skills/stage-dev",
    "skills/stage-verify",
    "completion-criteria.md",
    "interaction-protocols.md",
    "generate_codex_agents.py",
)
HARNESS_PRIVATE_TRUTH_MARKERS = (
    ".cursor/rules/",
    ".cursor/skills/environment-ops/SKILL.md",
)
GRADE_TAGS = {"MUST NOT", "MUST", "SHOULD NOT", "SHOULD", "MAY", "ADVISORY"}
CHECKLIST_ITEM_RE = re.compile(r"^-\s*\[(?P<tag>[A-Z ]+)\]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EVIDENCE_LINE_RE = re.compile(r"^\s*evidence:\s*(?P<id>[a-z0-9][a-z0-9-]*)\s*$", re.M)
CHECK_LINE_RE = re.compile(r"^\s*check:\s*(?P<text>.+?)\s*$", re.M)
GATE_LINE_RE = re.compile(r"^\s*gate:\s*", re.M)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _find_agents_files() -> list[Path]:
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in PRUNED_DIR_NAMES]
        if "AGENTS.md" in filenames:
            found.append(Path(current) / "AGENTS.md")
    return sorted(found)


def _tracked_files() -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return set(result.stdout.splitlines())


def _make_targets(makefile: Path) -> set[str]:
    if not makefile.is_file():
        return set()
    return set(
        re.findall(
            r"^([a-zA-Z0-9][a-zA-Z0-9_-]*):",
            makefile.read_text(encoding="utf-8"),
            re.M,
        )
    )


def _static_glob_prefix(pattern: str) -> str:
    return pattern.split("*", 1)[0].rstrip("/")


def _glob_can_match(pattern: str) -> bool:
    prefix = _static_glob_prefix(pattern)
    return bool(prefix and (ROOT / prefix).exists()) or next(ROOT.glob(pattern), None) is not None


def _frontmatter(text: str) -> tuple[dict[str, Any] | None, str | None]:
    match = re.match(r"---\n(?P<body>.*?)\n---\n", text, re.S)
    if match is None:
        return None, "缺 YAML frontmatter"
    try:
        value = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as error:
        return None, f"frontmatter 不是合法 YAML（{str(error).splitlines()[0]}）"
    if not isinstance(value, dict):
        return None, "frontmatter 不是键值映射"
    return value, None


def check_required_sources_and_carriers() -> list[str]:
    issues = [f"缺必需上下文源: {rel}" for rel in REQUIRED_SOURCES if not (ROOT / rel).is_file()]
    for rel in FORBIDDEN_ACTIVE_PATHS:
        if (ROOT / rel).exists() or (ROOT / rel).is_symlink():
            issues.append(f"退役载体仍是活跃入口: {rel}")

    for path in sorted((ROOT / ".cursor/rules").glob("*.mdc")):
        issues.append(f"{_rel(path)}: Cursor rule 不得承载规范；迁移到 owner spec/design/contract")

    roles_root = ROOT / ".agents/skills/review/references/roles"
    if roles_root.is_dir():
        for path in sorted(roles_root.glob("*/references/**/*")):
            if path.is_file() or path.is_symlink():
                issues.append(f"{_rel(path)}: role references 不得拥有或转引规范事实")
    return issues


def check_agents_budget() -> list[str]:
    issues: list[str] = []
    agents = _find_agents_files()
    tracked = _tracked_files()
    if tracked is None:
        return ["无法查询 git 索引，第一方 AGENTS.md 判定不可执行"]

    for path in agents:
        rel = _rel(path)
        if rel not in tracked:
            issues.append(f"{rel}: 非第一方 AGENTS.md 会污染渐进上下文")

    for leaf in agents:
        current = leaf.parent
        chain: list[Path] = []
        while True:
            candidate = current / "AGENTS.md"
            if candidate.is_file():
                chain.append(candidate)
            if current == ROOT:
                break
            if not current.resolve().is_relative_to(ROOT.resolve()):
                break
            current = current.parent
        size = sum(len(path.read_bytes()) for path in chain)
        if size > AGENTS_CHAIN_BYTE_BUDGET:
            detail = ", ".join(f"{_rel(path)}={len(path.read_bytes())}" for path in reversed(chain))
            issues.append(
                f"{_rel(leaf.parent) or '.'}: 适用 AGENTS 链 {size} bytes 超过 "
                f"{AGENTS_CHAIN_BYTE_BUDGET} bytes（{detail}）"
            )
    return issues


def _manifest_budget_nodes(nodes: list[Any]) -> list[Any]:
    """返回全部 Feature 节点，禁止用抽样掩盖超预算 Story。"""

    return list(nodes)


def check_manifest_budget() -> list[str]:
    issues: list[str] = []
    commands_path = ROOT / "quwoquan_ops/cli/lib/feature_tree/commands.py"
    cli_entry = ROOT / "quwoquan_ops/cli/lib/feature_tree/cli_entry.py"
    contract_path = ROOT / "quwoquan_ops/policies/agent_governance_contract.yaml"
    try:
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        return [f"无法读取 agent governance contract：{error}"]
    manifest_contract = contract.get("feature_context_manifest") or {}
    configured = manifest_contract.get("max_bytes")
    required_fields = manifest_contract.get("required_fields")
    if configured != MANIFEST_BYTE_BUDGET:
        issues.append(
            "agent governance contract 的 manifest max_bytes 必须精确为 8192，"
            f"当前={configured!r}"
        )
    if not isinstance(required_fields, list) or not all(
        isinstance(field, str) for field in required_fields
    ):
        issues.append("agent governance contract 的 manifest required_fields 必须为字符串列表")
        required_fields = []
    if cli_entry.is_file() and not re.search(r'default\s*=\s*["\']manifest["\']', cli_entry.read_text(encoding="utf-8")):
        issues.append("feature-context --format 默认值必须是 manifest")

    # 对每个 Feature 节点生成内存态 manifest；命令仍会对任意工程路径 fail-closed。
    if ROOT == ORIGINAL_ROOT and commands_path.is_file():
        cli_root = ROOT / "quwoquan_ops/cli"
        if str(cli_root) not in sys.path:
            sys.path.insert(0, str(cli_root))
        try:
            from lib.feature_tree.commands import (
                _context_manifest,
                _serialize_context_manifest,
            )
            from lib.feature_tree.nodes import discover_nodes
            from lib.feature_tree.ownership import resolve_target_details

            nodes = discover_nodes()
            budget_fingerprint = None
            for node in _manifest_budget_nodes(nodes):
                target = node.spec.relative_to(ROOT).as_posix()
                resolution = resolve_target_details(target, nodes)
                payload = _context_manifest(
                    target,
                    resolution,
                    nodes,
                    fingerprint_receipt=budget_fingerprint,
                )
                if budget_fingerprint is None:
                    budget_fingerprint = payload["evidence_fingerprint"]["receipt"]
                if set(payload) != set(required_fields):
                    issues.append(
                        f"{target}: manifest 字段与 agent governance contract 不一致"
                    )
                size = len(
                    (_serialize_context_manifest(payload) + "\n").encode("utf-8")
                )
                if size > MANIFEST_BYTE_BUDGET:
                    from lib.feature_context_fingerprint import referenced_fingerprint_binding

                    payload["evidence_fingerprint"] = referenced_fingerprint_binding(
                        payload["evidence_fingerprint"]["receipt"],
                        receipt_ref=(
                            ".qwq_output/env/repo/runs/feature-tree/"
                            "context-manifest.evidence-fingerprint.json"
                        ),
                    )
                    size = len(
                        (_serialize_context_manifest(payload) + "\n").encode("utf-8")
                    )
                if size > MANIFEST_BYTE_BUDGET:
                    issues.append(f"{target}: 默认 manifest {size} bytes 超过 8192 bytes")
        except (ImportError, OSError, ValueError) as error:
            issues.append(f"无法生成默认 feature-context manifest：{error}")
    return issues


def check_workflow_skills() -> list[str]:
    issues: list[str] = []
    root = ROOT / ".agents/skills"
    if not root.is_dir():
        return [".agents/skills 不存在"]

    on_disk = {path.name for path in root.iterdir() if path.is_dir()}
    for name in sorted(set(WORKFLOW_SKILLS) - on_disk):
        issues.append(f"缺 Workflow Skill: .agents/skills/{name}/SKILL.md")
    for name in sorted(on_disk - set(WORKFLOW_SKILLS)):
        issues.append(f".agents/skills/{name}: 顶层只允许完整 Workflow Skill")

    descriptions = 0
    for name in sorted(set(WORKFLOW_SKILLS) & on_disk):
        path = root / name / "SKILL.md"
        if not path.is_file():
            issues.append(f".agents/skills/{name}: 缺 SKILL.md")
            continue
        text = path.read_text(encoding="utf-8")
        rel = _rel(path)
        fields, error = _frontmatter(text)
        if error:
            issues.append(f"{rel}: {error}")
            continue
        assert fields is not None
        extra = sorted(set(fields) - SPEC_FRONTMATTER_FIELDS)
        if extra:
            issues.append(f"{rel}: frontmatter 含非开放字段 {extra}")
        if fields.get("name") != name:
            issues.append(f"{rel}: name={fields.get('name')!r} 与目录名不一致")
        description = str(fields.get("description") or "")
        descriptions += len(description)
        if not description:
            issues.append(f"{rel}: 缺 description")
        elif len(description) > SKILL_DESCRIPTION_EACH_BUDGET:
            issues.append(f"{rel}: description 超过 {SKILL_DESCRIPTION_EACH_BUDGET} 字符")
        if len(text.splitlines()) > SKILL_LINE_BUDGET:
            issues.append(f"{rel}: 超过 {SKILL_LINE_BUDGET} 行，重资料应按需放 references")

        metadata = fields.get("metadata") or {}
        if not isinstance(metadata, dict) or metadata.get("kind") != "workflow":
            issues.append(f"{rel}: metadata.kind 必须为 workflow")
            metadata = {}
        declared = metadata.get("command")
        expected = f"/{name}" if name in COMMAND_BOUND_WORKFLOWS else None
        if declared != expected:
            issues.append(f"{rel}: metadata.command={declared!r}，应为 {expected!r}")

        headings = re.findall(r"^##\s+(.+?)\s*$", text, re.M)
        if headings != list(REQUIRED_SKILL_SECTIONS):
            issues.append(
                f"{rel}: 二级段落必须且只能按顺序为 "
                + " / ".join(REQUIRED_SKILL_SECTIONS)
            )
        if any(token in text for token in ("completion-criteria.md", "interaction-protocols.md")):
            issues.append(f"{rel}: 完成与交互契约必须就地声明，不得跳转共享文档")

    if descriptions > SKILL_DESCRIPTION_TOTAL_BUDGET:
        issues.append(
            f".agents/skills description 合计 {descriptions} 字符超过 "
            f"{SKILL_DESCRIPTION_TOTAL_BUDGET}"
        )
    return issues


def check_commands_and_harness_stubs() -> list[str]:
    issues: list[str] = []
    commands = ROOT / ".cursor/commands"
    command_files = {path.stem for path in commands.glob("*.md")} if commands.is_dir() else set()
    for name in sorted(set(COMMAND_BOUND_WORKFLOWS) - command_files):
        issues.append(f"缺 Cursor 命令薄壳: .cursor/commands/{name}.md")
    for name in sorted(command_files - set(COMMAND_BOUND_WORKFLOWS)):
        issues.append(f".cursor/commands/{name}.md: 没有同名 Workflow Skill")
    for name in sorted(command_files):
        path = commands / f"{name}.md"
        text = path.read_text(encoding="utf-8")
        _, error = _frontmatter(text)
        if error:
            issues.append(f"{_rel(path)}: {error}")
        if len(text.splitlines()) > COMMAND_FILE_LINE_BUDGET:
            issues.append(f"{_rel(path)}: 超过 {COMMAND_FILE_LINE_BUDGET} 行命令薄壳预算")
        if f".agents/skills/{name}/SKILL.md" not in text:
            issues.append(f"{_rel(path)}: 未指向 .agents/skills/{name}/SKILL.md")

    for pattern in (".cursor/skills/*/SKILL.md", ".codex/skills/*/SKILL.md"):
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            _, error = _frontmatter(text)
            if error:
                issues.append(f"{_rel(path)}: {error}")
            if len(text.splitlines()) > HARNESS_STUB_LINE_BUDGET:
                issues.append(f"{_rel(path)}: 超过 {HARNESS_STUB_LINE_BUDGET} 行 adapter stub 预算")
            if ".agents/skills/" not in text:
                issues.append(f"{_rel(path)}: 未指向 .agents/skills 真相源")
    return issues


def _load_registry() -> tuple[dict[str, Any] | None, list[str]]:
    path = ROOT / ".agents/skills/review/references/registry.yaml"
    if not path.is_file():
        return None, ["缺 Review registry"]
    try:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        return None, [f"registry.yaml 不是合法 YAML：{error}"]
    if not isinstance(registry, dict):
        return None, ["registry.yaml 必须是映射"]
    return registry, []


def check_checklists_and_registry() -> list[str]:
    registry, issues = _load_registry()
    if registry is None:
        return issues
    if registry.get("schema_version") != 2:
        issues.append("registry.yaml: schema_version 必须为 2")
    if any(key in registry for key in ("concurrency", "bindings")):
        issues.append("registry.yaml: 不得保留 v1 concurrency/bindings")

    limits = registry.get("limits") or {}
    expected_limits = {
        "max_parallel": 2,
        "max_role_invocations": 4,
        "reviewer_context_bytes": REVIEWER_CONTEXT_BYTE_BUDGET,
    }
    for key, expected in expected_limits.items():
        if limits.get(key) != expected:
            issues.append(f"registry.yaml: limits.{key} 必须为 {expected}")
    timeout = limits.get("per_role_timeout_minutes")
    if not isinstance(timeout, int) or timeout <= 0:
        issues.append("registry.yaml: limits.per_role_timeout_minutes 必须为正整数")

    evidence = registry.get("evidence") or {}
    if not isinstance(evidence, dict) or not evidence:
        issues.append("registry.yaml: evidence 必须是非空映射")
        evidence = {}
    root_targets = _make_targets(ROOT / "Makefile")
    for evidence_id, config in evidence.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(evidence_id)):
            issues.append(f"registry.yaml: 非法 evidence id {evidence_id!r}")
        if not isinstance(config, dict):
            issues.append(f"registry.yaml: evidence.{evidence_id} 必须是映射")
            continue
        for key in ("command", "segment", "required", "covers"):
            if key not in config:
                issues.append(f"registry.yaml: evidence.{evidence_id} 缺 {key}")
        if config.get("segment") != "POST":
            issues.append(f"registry.yaml: evidence.{evidence_id}.segment 必须为 POST")
        if not isinstance(config.get("required"), bool):
            issues.append(f"registry.yaml: evidence.{evidence_id}.required 必须为 bool")
        if not isinstance(config.get("covers"), list):
            issues.append(f"registry.yaml: evidence.{evidence_id}.covers 必须为 list")
        command = str(config.get("command") or "")
        make = re.fullmatch(r"make\s+([a-zA-Z0-9][a-zA-Z0-9_-]*)", command)
        if make and make.group(1) not in root_targets:
            issues.append(f"registry.yaml: evidence.{evidence_id} 引用不存在的 make target {make.group(1)}")

    roles_root = ROOT / ".agents/skills/review/references/roles"
    profiles = registry.get("profiles") or {}
    if not isinstance(profiles, dict):
        issues.append("registry.yaml: profiles 必须是映射")
        profiles = {}
    for profile, config in profiles.items():
        if not isinstance(config, dict):
            issues.append(f"registry.yaml: profiles.{profile} 必须是映射")
            continue
        paths = config.get("paths") or []
        deliverables = config.get("deliverables") or []
        if not paths and not deliverables:
            issues.append(f"registry.yaml: profiles.{profile} 无 paths/deliverables，永不激活")
        for pattern in paths:
            if not _glob_can_match(str(pattern)):
                issues.append(f"registry.yaml: profiles.{profile} 路径 {pattern} 永不命中")
        specialist = config.get("specialist")
        if not isinstance(specialist, dict):
            issues.append(f"registry.yaml: profiles.{profile} 缺唯一 specialist")
            continue
        for key in ("role", "priority", "required", "checklists"):
            if key not in specialist:
                issues.append(f"registry.yaml: profiles.{profile}.specialist 缺 {key}")
        if not isinstance(specialist.get("priority"), int):
            issues.append(f"registry.yaml: profiles.{profile}.specialist.priority 必须为整数")
        if not isinstance(specialist.get("required"), bool):
            issues.append(f"registry.yaml: profiles.{profile}.specialist.required 必须为 bool")
        role = str(specialist.get("role") or "")
        if role and not (roles_root / role / "ROLE.md").is_file():
            issues.append(f"registry.yaml: specialist 角色 {role} 缺 ROLE.md")
        for workflow, checklist in (specialist.get("checklists") or {}).items():
            if workflow not in WORKFLOW_SKILLS:
                issues.append(f"registry.yaml: profiles.{profile} 引用未知 workflow {workflow}")
            if not (ROOT / ".agents/skills/review/references" / str(checklist)).is_file():
                issues.append(f"registry.yaml: profiles.{profile} checklist 不存在: {checklist}")

    workflows = registry.get("workflows") or {}
    if not isinstance(workflows, dict):
        issues.append("registry.yaml: workflows 必须是映射")
        workflows = {}
    for workflow in WORKFLOW_SKILLS:
        if workflow not in workflows:
            issues.append(f"registry.yaml: 缺 workflows.{workflow}")
    for workflow, config in workflows.items():
        if workflow not in WORKFLOW_SKILLS or not isinstance(config, dict):
            continue
        if config.get("segments") != ["PRE", "POST"]:
            issues.append(f"registry.yaml: workflows.{workflow}.segments 必须为 [PRE, POST]")
        automatic_review = config.get("automatic_review")
        if automatic_review is False:
            if workflow not in CONTROL_WORKFLOWS_WITHOUT_AUTOMATIC_REVIEW:
                issues.append(
                    f"registry.yaml: {workflow} 不是控制型 workflow，不得关闭 automatic review"
                )
            if config.get("primary"):
                issues.append(f"registry.yaml: {workflow} 必须默认零 Reviewer，不得再配 primary")
            continue
        if workflow in CONTROL_WORKFLOWS_WITHOUT_AUTOMATIC_REVIEW:
            issues.append(f"registry.yaml: {workflow} 控制型 workflow 必须默认零 Reviewer")
            continue
        primary = config.get("primary")
        if not isinstance(primary, dict):
            issues.append(f"registry.yaml: workflows.{workflow} 缺 primary")
            continue
        role = str(primary.get("role") or "")
        checklist = str(primary.get("checklist") or "")
        if primary.get("required") is not True:
            issues.append(f"registry.yaml: workflows.{workflow}.primary.required 必须为 true")
        if role and not (roles_root / role / "ROLE.md").is_file():
            issues.append(f"registry.yaml: primary 角色 {role} 缺 ROLE.md")
        if checklist and not (ROOT / ".agents/skills/review/references" / checklist).is_file():
            issues.append(f"registry.yaml: workflows.{workflow} primary checklist 不存在: {checklist}")

    # 检查全部 checklist，但不再要求磁盘文件反向注册成 inventory。
    for path in sorted(roles_root.glob("*/checklists/*/*.md")):
        text = path.read_text(encoding="utf-8")
        rel = _rel(path)
        if GATE_LINE_RE.search(text):
            issues.append(f"{rel}: checklist 禁止 gate: 命令，只能引用命名 evidence 或 check")
        lines = text.splitlines()
        item_starts = [index for index, line in enumerate(lines) if line.startswith("- ")]
        for position, index in enumerate(item_starts):
            line_number = index + 1
            line = lines[index]
            match = CHECKLIST_ITEM_RE.match(line)
            if match is None:
                issues.append(f"{rel}:{line_number}: checklist 条目缺分级标签")
                continue
            tag = match.group("tag").strip()
            if tag not in GRADE_TAGS:
                issues.append(f"{rel}:{line_number}: 未知分级标签 [{tag}]")
                continue

            next_index = item_starts[position + 1] if position + 1 < len(item_starts) else len(lines)
            item_text = "\n".join(lines[index:next_index])
            evidence_ids = EVIDENCE_LINE_RE.findall(item_text)
            checks = CHECK_LINE_RE.findall(item_text)
            for evidence_id in evidence_ids:
                if evidence_id not in evidence:
                    issues.append(f"{rel}:{line_number}: 引用未注册 evidence: {evidence_id}")
            for predicate in checks:
                if "判失败" not in predicate:
                    issues.append(
                        f"{rel}:{line_number}: check 必须写明客观输入与“判失败”条件"
                    )
            if tag in {"MUST", "MUST NOT"} and not (evidence_ids or checks):
                issues.append(
                    f"{rel}:{line_number}: [{tag}] checklist 未绑定本条 evidence 或客观 check"
                )
    return issues


def _agents_chain_bytes_for_prefix(prefix: str) -> int:
    path = ROOT / prefix
    current = path if path.is_dir() else path.parent
    total = 0
    while True:
        agents = current / "AGENTS.md"
        if agents.is_file():
            total += len(agents.read_bytes())
        if current == ROOT:
            break
        if not current.resolve().is_relative_to(ROOT.resolve()):
            break
        current = current.parent
    return total


def check_reviewer_context_budget() -> list[str]:
    registry, issues = _load_registry()
    if registry is None:
        return issues
    references = ROOT / ".agents/skills/review/references"
    base_paths = [references / "reviewer-executor.md", references / "grading.md"]
    if any(not path.is_file() for path in base_paths):
        return ["Reviewer context 基础文件缺失"]
    base_bytes = sum(len(path.read_bytes()) for path in base_paths)
    profiles = registry.get("profiles") or {}
    workflows = registry.get("workflows") or {}
    evidence = registry.get("evidence") or {}

    cases: list[tuple[str, dict[str, Any], dict[str, Any], int]] = []
    root_agents_bytes = len((ROOT / "AGENTS.md").read_bytes())
    for workflow, config in workflows.items():
        primary = (config or {}).get("primary")
        if isinstance(primary, dict):
            cases.append((f"workflow:{workflow}", primary, {"workflow": config}, root_agents_bytes))
    for profile, config in profiles.items():
        specialist = (config or {}).get("specialist")
        if not isinstance(specialist, dict):
            continue
        paths = config.get("paths") or []
        chain_bytes = max(
            (_agents_chain_bytes_for_prefix(_static_glob_prefix(str(pattern))) for pattern in paths),
            default=root_agents_bytes,
        )
        for workflow, checklist in (specialist.get("checklists") or {}).items():
            cases.append(
                (
                    f"profile:{profile}/{workflow}",
                    {**specialist, "checklist": checklist},
                    {"profile": config, "workflow": workflows.get(workflow)},
                    chain_bytes,
                )
            )

    for label, reviewer, registry_slice, agents_bytes in cases:
        role = str(reviewer.get("role") or "")
        checklist = str(reviewer.get("checklist") or "")
        paths = [references / "roles" / role / "ROLE.md", references / checklist]
        if any(not path.is_file() for path in paths):
            continue
        checklist_text = paths[1].read_text(encoding="utf-8")
        used_evidence = {
            evidence_id: evidence.get(evidence_id)
            for evidence_id in EVIDENCE_LINE_RE.findall(checklist_text)
        }
        registry_bytes = len(
            yaml.safe_dump(
                {**registry_slice, "evidence": used_evidence},
                allow_unicode=True,
                sort_keys=False,
            ).encode("utf-8")
        )
        total = agents_bytes + base_bytes + sum(len(path.read_bytes()) for path in paths) + registry_bytes
        if total > REVIEWER_CONTEXT_BYTE_BUDGET:
            issues.append(
                f"{label}: 单 Reviewer 规则/profile/checklist 上下文 {total} bytes 超过 "
                f"{REVIEWER_CONTEXT_BYTE_BUDGET} bytes"
            )
    return issues


def check_references_and_duplicates() -> list[str]:
    issues: list[str] = []
    scan = [ROOT / "AGENTS.md"]
    scan.extend(_find_agents_files())
    scan.extend(sorted((ROOT / ".agents/skills").rglob("*.md")))
    scan.extend(sorted((ROOT / ".cursor/commands").glob("*.md")))
    seen_paths: set[Path] = set()
    paragraphs: dict[str, str] = {}
    for path in scan:
        if path in seen_paths or not path.is_file():
            continue
        seen_paths.add(path)
        rel = _rel(path)
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_REFERENCE_TOKENS:
            if token in text:
                issues.append(f"{rel}: 引用退役治理源 {token}")
        for marker in HARNESS_PRIVATE_TRUTH_MARKERS:
            if marker in text:
                issues.append(f"{rel}: 规范不得引用 harness 私有载体 {marker}")
        if path.suffix == ".md":
            for target in MARKDOWN_LINK_RE.findall(text):
                target_path = target.split("#", 1)[0]
                if not target_path or target.startswith(("http://", "https://", "mailto:")):
                    continue
                if any(char in target_path for char in ("<", ">", "{")):
                    continue
                if not (path.parent / target_path).resolve().exists():
                    issues.append(f"{rel}: 相对链接断链 {target}")

        # 子服务 AGENTS 可以共享同一条稳定模板；重复正文只约束会被模型按工作流
        # 同时发现的 SKILL，避免以“去重”为名破坏路径自治。
        if "/SKILL.md" not in rel:
            continue
        body = re.sub(r"```.*?```", "", text, flags=re.S)
        for block in body.split("\n\n"):
            normalized = re.sub(r"\s+", " ", block).strip()
            if len(normalized) < 180 or normalized.startswith("#"):
                continue
            owner = paragraphs.setdefault(normalized, rel)
            if owner != rel:
                issues.append(f"{rel}: 长规范段落与 {owner} 重复，应改为单一 owner 引用")
    return issues


def check_adapter_generation() -> list[str]:
    generator = ROOT / "quwoquan_ops/tools/generate_agent_adapters.py"
    if not generator.is_file():
        return ["缺中性 adapter 生成器 quwoquan_ops/tools/generate_agent_adapters.py"]
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    detail = (result.stderr or result.stdout).strip().splitlines()
    if not detail:
        return [
            "Cursor/Codex adapter 与中性源不一致: "
            f"generator 静默退出 {result.returncode}"
        ]
    return [f"Cursor/Codex adapter 与中性源不一致: {line.strip()}" for line in detail if line.strip()]


CHECKS = (
    ("载体分层", check_required_sources_and_carriers),
    ("AGENTS 链预算", check_agents_budget),
    ("默认 manifest 预算", check_manifest_budget),
    ("Workflow Skill 五段", check_workflow_skills),
    ("命令与 harness 薄壳", check_commands_and_harness_stubs),
    ("Review registry/checklist", check_checklists_and_registry),
    ("Reviewer 上下文预算", check_reviewer_context_budget),
    ("引用与重复规范", check_references_and_duplicates),
    ("两宿主 adapter", check_adapter_generation),
)


def main() -> int:
    failures: list[tuple[str, list[str]]] = []
    for label, check in CHECKS:
        issues = check()
        if issues:
            failures.append((label, issues))

    emit_gate_result(
        "verify-agent-context-budget",
        [finding(f"[{label}] {issue}") for label, issues in failures for issue in issues],
        ROOT,
    )
    if failures:
        print("[verify_agent_context_budget] FAIL", file=sys.stderr)
        for label, issues in failures:
            print(f"  [{label}]", file=sys.stderr)
            for issue in issues:
                print(f"    - {issue}", file=sys.stderr)
        return 1
    print(
        "[verify_agent_context_budget] OK: 渐进上下文预算、五段技能、Review v2 与两宿主 adapter 合规"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
