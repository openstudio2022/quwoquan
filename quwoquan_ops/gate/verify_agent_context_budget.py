#!/usr/bin/env python3
"""Agent 上下文治理门禁。

指令文件本身没有强制力（harness 只把它们当普通消息投递），所以规则体系的结构性
约束必须由脚本兜住。本门禁只校验**可判定**的部分：

1. 三家 harness 的上下文预算（Codex 32 KiB 合并上限、单文件行数、description 清单预算）
2. 载体分配没有退化（真相源不落在 harness 专属目录、第三方 AGENTS.md 零容忍）
3. 顶层技能全部是完整工作流：统一八段模板、kind=workflow、命令双向一一映射、
   命令薄壳无历史叙述、HANDOFF 声明唯一合法下游
4. SKILL.md frontmatter 只用开放规范字段
5. 所有引用真实存在（globs、make target、脚本、skill 相对链接），且不引用已退役路径
6. checklist 每条带分级，且 MUST 绑定 gate 或 check
7. review registry 以工作流名为键做 profile 条件装配：binding/checklist/role 双向可达、
   profile 路径真实存在、workflow+segment 与各 SKILL 的「内置评审」声明一致、
   无条件 binding 之间 gate 不重复归属
8. 技能正文无跨文件重复段落（第二真相源检测）

触发范围：每次 gate 全仓无条件执行，不随变更文件裁剪。上下文预算与载体分配是全局
    不变量，只看某次改了哪些文件无法判定。
阻断条件：任一 issue 即 `main()` 返回 1。无 allowlist、无基线。
接入点：`make verify-agent-context-budget`、`make gate`、`make verify`，
    以及 `gate_repo.sh` 的无条件前置段。不进 L0 `commit_gate.sh`：该层禁止 `make gate`。
修复方式：每条失败消息自带具体修法与文件位置。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# 依赖与构建缓存不参与治理，且全量遍历它们会让门禁从秒级退化到半分钟级。
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

# ── 预算 ────────────────────────────────────────────────────────────────
# Codex project_doc_max_bytes 默认 32 KiB，超出部分静默截断，所以按目录算合并总量。
CODEX_MERGED_BYTE_BUDGET = 32 * 1024
# 单个指令文件的行数上限。指令文件过长后模型开始忽略内容。
AGENTS_LINE_BUDGET = 200
# SKILL.md 一旦被调用即常驻至会话结束，重资料必须压到 references/。
SKILL_LINE_BUDGET = 500
# skill 清单（name + description）常驻在每个会话里。8000 字符约 2000 token。
# 溢出会按使用频率静默丢弃 description，冷门技能将失去自动触发能力。
SKILL_DESCRIPTION_TOTAL_BUDGET = 8000
SKILL_DESCRIPTION_EACH_BUDGET = 500
# 命令是薄壳：frontmatter + 一行指向 SKILL.md。超过说明命令又开始承载语义。
COMMAND_FILE_LINE_BUDGET = 12

SPEC_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

REQUIRED_CONTEXT_SOURCES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".agents/README.md",
    "specs/feature-tree/README.md",
    "specs/feature-tree/spec.md",
    "specs/feature-tree/design.md",
    "quwoquan_ops/cli/feature_tree.py",
    "quwoquan_app/AGENTS.md",
    "quwoquan_service/AGENTS.md",
    "quwoquan_data/AGENTS.md",
    "quwoquan_ops/AGENTS.md",
    "quwoquan_ops/portal/AGENTS.md",
)

# 五段执行契约必须在根 AGENTS.md 中成文，否则两种入口会退回各说各话。
ROOT_AGENTS_REQUIRED_TOKENS = (
    "RESOLVE",
    "PRE",
    "DURING",
    "POST",
    "HANDOFF",
    "make feature-context",
    "OPEN",
    ".agents/skills",
)

# 顶层技能目录的封闭集合：每个都是有独立触发条件与交付件的完整工作流。
# 原则、标准、检查清单一律下沉到 review/references/roles/**，不得回到顶层。
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
)

# 有 Cursor 命令的工作流。命令文件与 metadata.command 必须双向一一映射。
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

# 统一八段模板。允许追加段（如 review 的「扩展」），但八段缺一不可。
REQUIRED_SKILL_SECTIONS = (
    "## 触发",
    "## 输入",
    "## 角色",
    "## 执行",
    "## 交付件",
    "## 内置评审",
    "## 失败与停止",
    "## HANDOFF",
)

RETIRED_GOVERNANCE_SOURCES = (
    "agent_context_contract.md",
    "agent_command_simulation_matrix.md",
    "docs/codex_workflow.md",
    "00_MASTER_DEVELOPMENT_FLOW.md",
)

# 已退役的技能路径。命中即说明有文件仍指向旧结构。
RETIRED_SKILL_PATH_TOKENS = (
    "skills/review-board",
    "skills/stage-explore",
    "skills/stage-prd",
    "skills/stage-design",
    "skills/stage-extend",
    "skills/stage-dev",
    "skills/stage-verify",
    "skills/stage-plan-next",
    "skills/absent-empty-failure",
    "skills/app-layering",
    "skills/auth-entry-no-loop",
    "skills/cross-platform-portability",
    "skills/dart-coding-standards",
    "skills/flutter-design-system",
    "skills/mock-data-isolation",
    "skills/page-horizontal-quality",
    "skills/pageflip-backward-mainline",
    "skills/python-script-governance",
    "skills/quwoquan-data-content",
    "skills/quwoquan-exception-triage",
)

# 命令薄壳禁用的历史叙述措辞：命令只描述当前执行入口。
COMMAND_HISTORICAL_TOKENS = ("迁移", "原先", "此前", "历史", "旧版", "已删除", "曾经")

# 真相源不得落在 harness 专属目录。命中即说明载体分配退化。
HARNESS_PRIVATE_TRUTH_MARKERS = (
    ".cursor/skills/",
    ".cursor/commands/crawl",
)

GRADE_TAGS = ("MUST NOT", "MUST", "SHOULD NOT", "SHOULD", "MAY", "ADVISORY")
CHECKLIST_ITEM_RE = re.compile(r"^-\s*\[(?P<tag>[A-Z ]+)\]")
BINDING_RE = re.compile(r"^\s+(?:gate|check):\s*\S")
GATE_COMMAND_RE = re.compile(r"^\s+gate:\s*(?P<cmd>.+?)\s*$", re.M)
MAKE_TARGET_RE = re.compile(r"gate:\s*make\s+(?:-C\s+(?P<dir>\S+)\s+)?(?P<target>[a-z0-9][a-z0-9-]*)")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EMBEDDED_REVIEW_CALL_RE = re.compile(r"workflow=`(?P<workflow>[a-z-]+)`，segment=(?P<segment>PRE|POST)")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _find_agents_files() -> list[Path]:
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIR_NAMES]
        if "AGENTS.md" in filenames:
            found.append(Path(current) / "AGENTS.md")
    return sorted(found)


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


def _glob_exists(pattern: str) -> bool:
    # 先用静态前缀短路：`**` 展开在本仓这种体量下代价很高。
    static = pattern.split("*")[0].rstrip("/")
    if static and (ROOT / static).exists():
        return True
    return next(ROOT.glob(pattern), None) is not None


def _tracked_files() -> set[str] | None:
    """受版本控制的文件集合；git 不可用时返回 None。

    调用方必须把 None 当作失败而不是「跳过」——第一方判定一旦静默失效，
    依赖缓存自带的 AGENTS.md 就会无声回流进上下文。
    """
    try:
        out = subprocess.run(
            ["git", "--work-tree=.", "ls-files"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return set(out.stdout.split())


def _skill_frontmatter(text: str) -> dict | None:
    match = re.match(r"---\n(?P<fm>.*?)\n---\n", text, re.S)
    if match is None:
        return None
    try:
        parsed = yaml.safe_load(match.group("fm"))
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def check_required_sources() -> list[str]:
    return [
        f"缺必需上下文源: {rel}"
        for rel in REQUIRED_CONTEXT_SOURCES
        if not (ROOT / rel).is_file()
    ]


def check_lifecycle_contract() -> list[str]:
    issues: list[str] = []
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for token in ROOT_AGENTS_REQUIRED_TOKENS:
        if token not in text:
            issues.append(f"AGENTS.md 缺五段执行契约标记 {token}")

    readme = (ROOT / "specs/feature-tree/README.md").read_text(encoding="utf-8")
    for token in ("目录结构就是树", "Agent 最小阅读链", "动态工具", "自动门禁"):
        if token not in readme:
            issues.append(f"specs/feature-tree/README.md 缺 {token}")

    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if "@AGENTS.md" not in claude:
        issues.append("CLAUDE.md 未用 @AGENTS.md 桥接根指令，Claude Code 将看不到全仓红线")
    return issues


def check_workflow_skills() -> list[str]:
    """顶层技能封闭集合 + 八段模板 + 命令双向映射 + 命令薄壳。"""
    issues: list[str] = []
    skills_root = ROOT / ".agents/skills"
    if not skills_root.is_dir():
        return [".agents/skills 不存在，技能真相源缺失"]

    on_disk = {p.name for p in skills_root.iterdir() if p.is_dir()}
    for name in set(WORKFLOW_SKILLS) - on_disk:
        issues.append(f"缺工作流技能: .agents/skills/{name}/SKILL.md")
    for name in sorted(on_disk - set(WORKFLOW_SKILLS)):
        issues.append(
            f".agents/skills/{name}: 不在工作流封闭集合内。顶层只允许完整工作流；"
            "原则/标准/检查清单请下沉 review/references/roles/**，"
            "并在本门禁的 WORKFLOW_SKILLS 中登记新工作流"
        )

    commands_dir = ROOT / ".cursor/commands"
    command_files = {p.stem for p in commands_dir.glob("*.md")} if commands_dir.is_dir() else set()
    for name in set(COMMAND_BOUND_WORKFLOWS) - command_files:
        issues.append(f"缺命令薄壳: .cursor/commands/{name}.md")
    for name in sorted(command_files - set(COMMAND_BOUND_WORKFLOWS)):
        issues.append(
            f".cursor/commands/{name}.md: 没有同名工作流技能声明 metadata.command，"
            "命令与技能必须双向一一映射"
        )

    for name in sorted(set(WORKFLOW_SKILLS) & on_disk):
        skill = skills_root / name / "SKILL.md"
        if not skill.is_file():
            issues.append(f".agents/skills/{name}: 缺 SKILL.md")
            continue
        text = skill.read_text(encoding="utf-8")
        rel = _rel(skill)

        fields = _skill_frontmatter(text) or {}
        metadata = fields.get("metadata") or {}
        if not isinstance(metadata, dict) or metadata.get("kind") != "workflow":
            issues.append(f"{rel}: metadata.kind 必须为 workflow")
        declared_command = metadata.get("command") if isinstance(metadata, dict) else None

        if name in COMMAND_BOUND_WORKFLOWS:
            if declared_command != f"/{name}":
                issues.append(
                    f"{rel}: metadata.command={declared_command!r}，应为 '/{name}' 并与 "
                    f".cursor/commands/{name}.md 双向映射"
                )
        elif declared_command:
            issues.append(f"{rel}: 自动工作流不得声明 metadata.command={declared_command!r}")

        for section in REQUIRED_SKILL_SECTIONS:
            if not re.search(rf"^{re.escape(section)}\s*$", text, re.M):
                issues.append(f"{rel}: 缺统一模板段 {section}")

        handoff = text.split("## HANDOFF", 1)[-1]
        for token in ("唯一合法下游", "证据链"):
            if token not in handoff:
                issues.append(f"{rel}: HANDOFF 段缺「{token}」声明")

    for name in sorted(set(COMMAND_BOUND_WORKFLOWS) & command_files):
        command = commands_dir / f"{name}.md"
        text = command.read_text(encoding="utf-8")
        rel = _rel(command)
        lines = len(text.splitlines())
        if lines > COMMAND_FILE_LINE_BUDGET:
            issues.append(
                f"{rel}: {lines} 行超过命令薄壳 {COMMAND_FILE_LINE_BUDGET} 行上限；"
                "命令只指向 SKILL.md，语义写进技能"
            )
        if f".agents/skills/{name}/SKILL.md" not in text:
            issues.append(f"{rel}: 未指向 .agents/skills/{name}/SKILL.md")
        for token in COMMAND_HISTORICAL_TOKENS:
            if token in text:
                issues.append(f"{rel}: 含历史叙述措辞「{token}」；命令只描述当前执行入口")
    return issues


def check_agents_budget() -> list[str]:
    issues: list[str] = []
    agents = _find_agents_files()

    tracked = _tracked_files()
    if tracked is None:
        return ["无法查询 git 索引，第一方 AGENTS.md 判定不可执行；请在 git 工作树内运行本门禁"]

    for path in agents:
        rel = _rel(path)
        if rel not in tracked:
            issues.append(
                f"{rel}: 非第一方 AGENTS.md（未受版本控制），会经嵌套拾取污染上下文；"
                "请加入 .cursorignore 或删除"
            )
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > AGENTS_LINE_BUDGET:
            issues.append(f"{rel}: {lines} 行超过 {AGENTS_LINE_BUDGET} 行上限，请向嵌套目录分层")

    # Codex 在某目录下工作时会合并该路径上所有 AGENTS.md，按最深目录算最坏情况。
    for path in agents:
        total = 0
        parts: list[str] = []
        current = path.parent
        while True:
            candidate = current / "AGENTS.md"
            if candidate.is_file():
                size = len(candidate.read_bytes())
                total += size
                parts.append(f"{_rel(candidate)}={size}")
            if current == ROOT:
                break
            current = current.parent
        if total > CODEX_MERGED_BYTE_BUDGET:
            issues.append(
                f"{_rel(path.parent) or '.'}: AGENTS.md 合并 {total} 字节超过 Codex "
                f"{CODEX_MERGED_BYTE_BUDGET} 字节上限（{', '.join(parts)}），超出部分会被静默截断"
            )
    return issues


def check_skills() -> list[str]:
    issues: list[str] = []
    skills_root = ROOT / ".agents/skills"
    if not skills_root.is_dir():
        return [".agents/skills 不存在，技能真相源缺失"]

    total_description = 0
    for directory in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill = directory / "SKILL.md"
        if not skill.is_file():
            issues.append(f"{_rel(directory)}: 缺 SKILL.md")
            continue

        text = skill.read_text(encoding="utf-8")
        rel = _rel(skill)

        lines = len(text.splitlines())
        if lines > SKILL_LINE_BUDGET:
            issues.append(
                f"{rel}: {lines} 行超过 {SKILL_LINE_BUDGET} 行上限，"
                "重资料请压到 references/"
            )

        match = re.match(r"---\n(?P<fm>.*?)\n---\n", text, re.S)
        if match is None:
            issues.append(f"{rel}: 缺 YAML frontmatter")
            continue

        # 必须用真正的 YAML 解析器。手写的 `partition(":")` 会把
        # `description: A: B` 读成合法值，而 harness 侧会整份解析失败——
        # 结果是技能静默不可见，且门禁看不出来。
        try:
            parsed = yaml.safe_load(match.group("fm"))
        except yaml.YAMLError as error:
            reason = str(error).splitlines()[0]
            issues.append(
                f"{rel}: frontmatter 不是合法 YAML（{reason}）；"
                "该技能在 harness 侧会静默不可见。值里含「冒号+空格」时必须加引号"
            )
            continue
        if not isinstance(parsed, dict):
            issues.append(f"{rel}: frontmatter 不是键值映射")
            continue
        fields = {str(key): value for key, value in parsed.items()}

        extra = set(fields) - SPEC_FRONTMATTER_FIELDS
        if extra:
            issues.append(
                f"{rel}: frontmatter 含非开放规范字段 {sorted(extra)}；"
                f"只允许 {sorted(SPEC_FRONTMATTER_FIELDS)}"
            )

        if fields.get("name") != directory.name:
            issues.append(f"{rel}: name={fields.get('name')!r} 与目录名 {directory.name!r} 不一致")

        description = str(fields.get("description") or "")
        if not description:
            issues.append(f"{rel}: 缺 description，模型无法自动匹配该技能")
        else:
            total_description += len(description)
            if len(description) > SKILL_DESCRIPTION_EACH_BUDGET:
                issues.append(
                    f"{rel}: description {len(description)} 字符超过单条 "
                    f"{SKILL_DESCRIPTION_EACH_BUDGET} 字符上限"
                )

    if total_description > SKILL_DESCRIPTION_TOTAL_BUDGET:
        issues.append(
            f".agents/skills: description 合计 {total_description} 字符超过 "
            f"{SKILL_DESCRIPTION_TOTAL_BUDGET} 字符清单预算；"
            "溢出会按使用频率静默丢弃 description，冷门技能将失去自动触发能力"
        )
    return issues


def check_rule_pointers() -> list[str]:
    issues: list[str] = []
    rules_dir = ROOT / ".cursor/rules"
    if not rules_dir.is_dir():
        return issues

    for path in sorted(rules_dir.glob("*.mdc")):
        text = path.read_text(encoding="utf-8")
        rel = _rel(path)
        match = re.match(r"---\n(?P<fm>.*?)\n---\n", text, re.S)
        frontmatter = match.group("fm") if match else ""

        globs = re.search(r"^globs:\s*(.+)$", frontmatter, re.M)
        if globs:
            for pattern in (p.strip() for p in globs.group(1).split(",")):
                if pattern and not _glob_exists(pattern):
                    issues.append(
                        f"{rel}: globs 指向磁盘不存在的路径 {pattern}，该规则永不触发"
                    )

        always = re.search(r"^alwaysApply:\s*true\s*$", frontmatter, re.M)
        if always and len(text) > 2500:
            issues.append(
                f"{rel}: alwaysApply 常驻规则 {len(text)} 字符过大；"
                "常驻层只允许薄指针，正文请迁 .agents/skills"
            )
    return issues


def check_references() -> list[str]:
    """校验共享层与规则层引用的 make target、脚本、相对链接真实存在。"""
    issues: list[str] = []
    root_targets = _make_targets(ROOT / "Makefile")

    scan: list[Path] = [ROOT / "AGENTS.md"]
    scan.extend(sorted((ROOT / ".agents/skills").rglob("*.md")))
    scan.extend(sorted((ROOT / ".agents/skills").rglob("*.yaml")))
    scan.extend(sorted((ROOT / ".cursor/rules").glob("*.mdc")))
    scan.extend(sorted((ROOT / ".cursor/commands").glob("*.md")))
    scan.extend(sorted((ROOT / ".claude/agents").glob("*.md")))

    for path in scan:
        text = path.read_text(encoding="utf-8")
        rel = _rel(path)

        for marker in HARNESS_PRIVATE_TRUTH_MARKERS:
            if marker in text:
                issues.append(f"{rel}: 引用已迁移的 harness 专属路径 {marker}")

        for token in RETIRED_GOVERNANCE_SOURCES:
            if token in text:
                issues.append(f"{rel}: 引用已退役治理源 {token}")

        for token in RETIRED_SKILL_PATH_TOKENS:
            if token in text:
                issues.append(f"{rel}: 引用已退役技能路径 {token}")

        for match in MAKE_TARGET_RE.finditer(text):
            target = match.group("target")
            subdir = match.group("dir")
            if subdir:
                if target not in _make_targets(ROOT / subdir / "Makefile"):
                    issues.append(f"{rel}: gate 引用不存在的 target make -C {subdir} {target}")
            elif target not in root_targets:
                issues.append(f"{rel}: gate 引用根 Makefile 中不存在的 target make {target}")

        for script in re.findall(r"quwoquan_[A-Za-z0-9_\-/]+\.(?:py|sh|yaml|json)", text):
            if not (ROOT / script).exists():
                issues.append(f"{rel}: 引用不存在的文件 {script}")

        if path.suffix == ".md" and ".agents/skills" in rel:
            for target in MARKDOWN_LINK_RE.findall(text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                resolved = (path.parent / target.split("#")[0]).resolve()
                if not resolved.exists():
                    issues.append(f"{rel}: 相对链接断链 {target}")
    return issues


def check_checklist_grading() -> list[str]:
    """每条 checklist 必须带分级；MUST 必须绑 gate 或 check。"""
    issues: list[str] = []
    roles_root = ROOT / ".agents/skills/review/references/roles"
    if not roles_root.is_dir():
        return ["review 角色目录缺失"]

    for path in sorted(roles_root.glob("*/checklists/*/*.md")):
        rel = _rel(path)
        lines = path.read_text(encoding="utf-8").splitlines()

        # HANDOFF 是交接契约（产出物 / 未决项去向 / 下一步 / 证据链），不是判定条目，
        # 分级对它没有意义。只有 PRE / DURING / POST 三段要求分级。
        in_handoff = False
        for index, line in enumerate(lines):
            if line.startswith("#"):
                in_handoff = "HANDOFF" in line
                continue
            if in_handoff or not line.startswith("- "):
                continue
            match = CHECKLIST_ITEM_RE.match(line)
            if match is None:
                issues.append(f"{rel}:{index + 1}: checklist 条目缺分级标签 -> {line.strip()[:60]}")
                continue
            tag = match.group("tag").strip()
            if tag not in GRADE_TAGS:
                issues.append(f"{rel}:{index + 1}: 未知分级标签 [{tag}]")
                continue
            if tag not in ("MUST", "MUST NOT"):
                continue
            # MUST 的绑定允许写在同行或紧随的缩进行
            bound = "gate:" in line or "check:" in line
            for follow in lines[index + 1 :]:
                if not follow.strip():
                    break
                if follow.startswith("- "):
                    break
                if BINDING_RE.match(follow):
                    bound = True
                    break
            if not bound:
                issues.append(
                    f"{rel}:{index + 1}: [{tag}] 未绑定 gate 或 check，"
                    "按 grading.md 必须降级为 SHOULD"
                )
    return issues


def check_review_registry() -> list[str]:
    """registry 必须能真的派发出去，且与各 SKILL 的「内置评审」声明双向一致。

    注册了却不存在的 checklist、存在却没人引用的 checklist、指向已消失路径的
    profile，都会让评审静默少一整个维度。
    """
    issues: list[str] = []
    board = ROOT / ".agents/skills/review"
    registry_path = board / "references/registry.yaml"
    if not registry_path.is_file():
        return ["缺 .agents/skills/review/references/registry.yaml"]

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    references_root = board / "references"
    roles_root = references_root / "roles"

    concurrency = registry.get("concurrency") or {}
    for key in ("max_parallel", "per_role_timeout_minutes"):
        if not isinstance(concurrency.get(key), int):
            issues.append(f"registry.yaml: concurrency.{key} 缺失或不是整数")

    profiles: dict[str, dict] = registry.get("profiles") or {}
    for profile, config in profiles.items():
        paths = (config or {}).get("paths") or []
        if not paths and not (config or {}).get("deliverables"):
            issues.append(f"registry.yaml: profiles.{profile} 既无 paths 也无 deliverables，永不激活")
        for pattern in paths:
            if not _glob_exists(pattern):
                issues.append(
                    f"registry.yaml: profiles.{profile} 路径 {pattern} 在磁盘不存在，永不命中"
                )

    workflows: dict[str, dict] = registry.get("workflows") or {}
    if not workflows:
        issues.append("registry.yaml: 缺 workflows 段，registry 必须以工作流名为键")

    referenced_checklists: set[str] = set()
    referenced_roles: set[str] = set()
    registry_segments: dict[str, set[str]] = {}

    for workflow, config in workflows.items():
        config = config or {}
        segments = set(config.get("segments") or [])
        if not segments or not segments <= {"PRE", "POST"}:
            issues.append(f"registry.yaml: workflows.{workflow}.segments 必须是 PRE/POST 的非空子集")
        registry_segments[workflow] = segments
        if not config.get("deliverable"):
            issues.append(f"registry.yaml: workflows.{workflow} 缺 deliverable")

        bindings = config.get("bindings") or []
        if not bindings:
            issues.append(f"registry.yaml: workflows.{workflow} 没有任何 binding")
        seen: set[tuple[str, str]] = set()
        unconditional_gates: dict[str, str] = {}
        for binding in bindings:
            role = (binding or {}).get("role")
            checklist = (binding or {}).get("checklist")
            when = (binding or {}).get("when")
            if not role or not checklist:
                issues.append(f"registry.yaml: workflows.{workflow} 存在缺 role/checklist 的 binding")
                continue
            key = (role, checklist)
            if key in seen:
                issues.append(f"registry.yaml: workflows.{workflow} 重复 binding {role} -> {checklist}")
            seen.add(key)
            referenced_roles.add(role)
            referenced_checklists.add(checklist)
            if not (roles_root / role / "ROLE.md").is_file():
                issues.append(f"registry.yaml: 角色 {role} 已注册但缺 roles/{role}/ROLE.md")
            checklist_path = references_root / checklist
            if not checklist_path.is_file():
                issues.append(
                    f"registry.yaml: workflows.{workflow} 引用不存在的 checklist {checklist}"
                )
            if when is not None:
                for profile in when:
                    if profile not in profiles:
                        issues.append(
                            f"registry.yaml: workflows.{workflow} binding {role} 引用"
                            f"未声明的 profile {profile}"
                        )
            elif checklist_path.is_file():
                # 无条件 binding 之间同一 gate 只允许一个执行 owner；
                # 条件 binding 的重叠由 board 在运行时按 evidence id 去重。
                for match in GATE_COMMAND_RE.finditer(checklist_path.read_text(encoding="utf-8")):
                    command = match.group("cmd")
                    owner = unconditional_gates.setdefault(command, checklist)
                    if owner != checklist:
                        issues.append(
                            f"registry.yaml: workflows.{workflow} 无条件 bundle 内 gate 重复归属"
                            f"（{command} 同时出现在 {owner} 与 {checklist}）"
                        )

    # 反向可达：磁盘上的 checklist 与角色目录必须被 registry 引用，否则永不派发。
    for path in sorted(roles_root.glob("*/checklists/*/*.md")):
        rel_to_refs = path.relative_to(references_root).as_posix()
        if rel_to_refs not in referenced_checklists:
            issues.append(f"{_rel(path)}: 未被 registry 任何 binding 引用，永远不会被派发")
    for directory in sorted(p for p in roles_root.iterdir() if p.is_dir()):
        if directory.name not in referenced_roles:
            issues.append(f"roles/{directory.name} 存在但未被 registry 引用，永远不会被派发")
        for stray in sorted(directory.glob("*.md")):
            if stray.name != "ROLE.md":
                issues.append(
                    f"{_rel(stray)}: checklist 必须放在 checklists/<workflow>/ 下，"
                    "角色根目录只允许 ROLE.md"
                )

    # SKILL「内置评审」声明与 registry 双向一致。
    skill_segments: dict[str, set[str]] = defaultdict(set)
    for name in WORKFLOW_SKILLS:
        skill = ROOT / ".agents/skills" / name / "SKILL.md"
        if not skill.is_file():
            continue
        text = skill.read_text(encoding="utf-8")
        section = text.split("## 内置评审", 1)
        if len(section) < 2:
            continue
        body = section[1].split("\n## ", 1)[0]
        for match in EMBEDDED_REVIEW_CALL_RE.finditer(body):
            skill_segments[match.group("workflow")].add(match.group("segment"))

    for workflow, segments in sorted(skill_segments.items()):
        missing = segments - registry_segments.get(workflow, set())
        for segment in sorted(missing):
            issues.append(
                f"SKILL 声明了 review({workflow}, {segment}) 但 registry 无对应 "
                f"workflows.{workflow}.segments 条目——死调用"
            )
    for workflow, segments in sorted(registry_segments.items()):
        declared = skill_segments.get(workflow, set())
        for segment in sorted(segments - declared):
            issues.append(
                f"registry 注册了 workflows.{workflow} segment {segment}，"
                f"但没有任何 SKILL 的「内置评审」声明该调用——死注册"
            )
    return issues


def check_duplicate_body() -> list[str]:
    """跨文件重复段落检测：同一段正文只允许一个 owner，其他位置引用。"""
    issues: list[str] = []
    paragraphs: dict[str, str] = {}
    scan = sorted((ROOT / ".agents/skills").rglob("*.md"))
    for path in scan:
        rel = _rel(path)
        text = path.read_text(encoding="utf-8")
        # 代码块内是模板/示例，不当正文比对。
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for block in text.split("\n\n"):
            normalized = re.sub(r"\s+", " ", block).strip()
            if len(normalized) < 120 or normalized.startswith("#"):
                continue
            owner = paragraphs.setdefault(normalized, rel)
            if owner != rel:
                issues.append(
                    f"{rel}: 段落与 {owner} 重复（{normalized[:40]}…）；"
                    "正文只允许一个 owner，其余位置改为引用"
                )
    return issues


def check_generated_subagents() -> list[str]:
    generator = ROOT / "quwoquan_ops/tools/generate_codex_agents.py"
    if not generator.is_file():
        return ["缺 quwoquan_ops/tools/generate_codex_agents.py"]
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    detail = (result.stderr or result.stdout).strip().splitlines()
    return [f"Codex 子代理生成物不是最新: {line.strip()}" for line in detail if line.strip()]


CHECKS = (
    ("必需上下文源", check_required_sources),
    ("五段执行契约", check_lifecycle_contract),
    ("工作流技能与命令映射", check_workflow_skills),
    ("AGENTS.md 预算", check_agents_budget),
    ("SKILL.md 规范与预算", check_skills),
    ("Cursor 规则指针", check_rule_pointers),
    ("引用有效性", check_references),
    ("checklist 分级", check_checklist_grading),
    ("review 派发表", check_review_registry),
    ("重复正文", check_duplicate_body),
    ("子代理生成物", check_generated_subagents),
)


def main() -> int:
    failures: list[tuple[str, list[str]]] = []
    for label, check in CHECKS:
        issues = check()
        if issues:
            failures.append((label, issues))

    if failures:
        print("[verify_agent_context_budget] FAIL", file=sys.stderr)
        for label, issues in failures:
            print(f"  [{label}]", file=sys.stderr)
            for issue in issues:
                print(f"    - {issue}", file=sys.stderr)
        return 1

    print("[verify_agent_context_budget] OK: 上下文预算、工作流结构、派发表与分级均合规")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
