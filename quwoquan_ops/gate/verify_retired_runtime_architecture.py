#!/usr/bin/env python3
"""阻断退役 runtime 数据访问架构重新进入当前指令真相源。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CURRENT_AUTHORITY_FILES = (
    (
        "specs/feature-tree/runtime/system-architecture-and-engineering-guide/"
        "design.md"
    ),
    (
        "specs/feature-tree/runtime/system-architecture-and-engineering-guide/"
        "acceptance.yaml"
    ),
    "quwoquan_service/contracts/metadata/DESIGN.md",
)

RETIRED_ROOT_DOCUMENTS = (
    "specs/runtime_gap_analysis_and_plan.md",
    "specs/RUNTIME_DEVELOPMENT_PLAN.md",
    "specs/runtime_framework_spec.md",
    "specs/runtime_framework_design.md",
)

RETIRED_FEATURE_NODES = (
    "specs/feature-tree/runtime/runtime-registry",
    "specs/feature-tree/runtime/runtime-repository",
)

RETIRED_FEATURE_NODE_NAMES = (
    "runtime-registry",
    "runtime-repository",
    "metadata-loader-and-entity-registry",
    "repository-interface-layering",
)

RETIRED_TERMS = (
    "runtime/repository",
    "runtime/registry",
    "GenericAggregateStore",
    "GenericSliceReader",
    "BaseFacade",
    "EntityRegistry",
    "Repository[T]",
)

RETIRED_DYNAMIC_PATTERNS = (
    re.compile(r"\bGetStorageBackend\b"),
    re.compile(r"\bMustInitFromRegistry\b"),
    re.compile(r"\bFactory\.(?:Create|WithCache)\s*\("),
    re.compile(
        r"storage_backend.{0,100}(?:自动|动态).{0,60}(?:选择|路由|选厂)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:factory|工厂).{0,100}storage_backend",
        re.IGNORECASE,
    ),
)

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_LINK_FILES = (
    "specs/00_AGENT_MASTER_SPEC.md",
    "specs/README.md",
    "specs/runtime_extension_catalog.md",
)

NEGATIVE_REFERENCE_PATHS = {
    ".cursor/commands/infra-audit.md",
    ".cursor/commands/infra-dev.md",
    "specs/feature-tree/design.md",
    (
        "specs/feature-tree/runtime/system-architecture-and-engineering-guide/"
        "spec.md"
    ),
    (
        "specs/feature-tree/runtime/system-architecture-and-engineering-guide/"
        "design.md"
    ),
    "quwoquan_service/contracts/metadata/DESIGN.md",
}

NEGATIVE_MARKERS = (
    "禁止",
    "不得",
    "不生成",
    "不暴露",
    "不允许",
    "退役",
    "已删除",
    "不存在",
    "out of scope",
)

HISTORICAL_PATHS = {
    "docs/outstanding_risks_backlog.md",
}

REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    "specs/runtime_extension_catalog.md": (
        "system-architecture-and-engineering-guide/design.md",
        "quwoquan_service/contracts/metadata/DESIGN.md",
        "commercial validate",
        "Object Application Facade",
        "Object Data Ports",
        "owned_entity",
        "separate_aggregate",
        "无界集合禁止内嵌",
        "query 绑定 named Reader/Slice",
        "local_contract",
        "api_integration",
        "user_acceptance",
        "alpha",
        "beta",
        "gamma",
        "prod",
        "Memory、Noop、Mock",
    ),
    ".cursor/commands/extend.md": (
        "EX01–EX11",
        "commercial validate",
        "Object Application Facade",
        "Object Data Ports",
        "无界集合禁止内嵌",
        "query",
        "named Reader",
        "local_contract",
        "api_integration",
        "user_acceptance",
    ),
    ".cursor/rules/01-arch-constraints.mdc": (
        "system-architecture-and-engineering-guide/design.md",
        "对象专属 command/query Facade",
        "对象专属 `AggregateStore` / named Reader / typed Slice",
        "显式 composition root",
        "qwq-contract commercial validate",
    ),
    "specs/README.md": (
        "system-architecture-and-engineering-guide/design.md",
        "system-architecture-and-engineering-guide/acceptance.yaml",
        "quwoquan_service/contracts/metadata/DESIGN.md",
    ),
    "specs/00_AGENT_MASTER_SPEC.md": (
        "system-architecture-and-engineering-guide/design.md",
        "system-architecture-and-engineering-guide/acceptance.yaml",
        "metadata/DESIGN.md",
    ),
    "quwoquan_service/contracts/metadata/README.md": (
        "system-architecture-and-engineering-guide/design.md",
        "ContractGraph operation + Object Facade facet/method",
        "服务 composition root 显式注入 Store/Reader 实现",
    ),
}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _active_instruction_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for directory, pattern in (
        (root / ".cursor" / "rules", "*.mdc"),
        (root / ".cursor" / "commands", "*.md"),
        (root / "specs", "*.md"),
        (root / "specs" / "feature-tree", "*.yaml"),
        (root / "docs", "*.md"),
    ):
        if directory.is_dir():
            paths.update(directory.rglob(pattern))

    paths.update(root.rglob("AGENTS.md"))
    for relative in (
        "quwoquan_service/contracts/metadata/README.md",
        "quwoquan_service/contracts/metadata/DESIGN.md",
    ):
        path = root / relative
        if path.is_file():
            paths.add(path)

    return sorted(
        path
        for path in paths
        if _relative(path, root) not in HISTORICAL_PATHS
        and "specs/changelog" not in path.as_posix()
    )


def _context(lines: list[str], index: int, radius: int = 8) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(lines[start:end]).lower()


def _is_allowed_negative_reference(
    relative: str,
    lines: list[str],
    index: int,
) -> bool:
    if relative not in NEGATIVE_REFERENCE_PATHS:
        return False
    context = _context(lines, index)
    return any(marker in context for marker in NEGATIVE_MARKERS)


def scan_instruction_text(relative: str, text: str) -> list[str]:
    """扫描一份当前指令文本；供门禁与 local_contract 共同使用。"""

    issues: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        for document in RETIRED_ROOT_DOCUMENTS:
            if document in line or Path(document).name in line:
                issues.append(
                    f"{relative}:{index + 1}: 引用已删除第二真相源 {document}"
                )

        for node_name in RETIRED_FEATURE_NODE_NAMES:
            if node_name in line:
                issues.append(
                    f"{relative}:{index + 1}: 引用已删除 feature-tree 节点 "
                    f"{node_name}"
                )

        for term in RETIRED_TERMS:
            if term not in line:
                continue
            if _is_allowed_negative_reference(relative, lines, index):
                continue
            issues.append(
                f"{relative}:{index + 1}: 出现退役 runtime 口径 {term}"
            )

        for pattern in RETIRED_DYNAMIC_PATTERNS:
            if not pattern.search(line):
                continue
            if _is_allowed_negative_reference(relative, lines, index):
                continue
            issues.append(
                f"{relative}:{index + 1}: 出现动态 storage backend factory 口径"
            )

    return issues


def scan_markdown_links(
    relative: str,
    text: str,
    root: Path = ROOT,
) -> list[str]:
    issues: list[str] = []
    source = root / relative
    for target in MARKDOWN_LINK_RE.findall(text):
        clean_target = target.split("#", 1)[0].strip()
        if (
            not clean_target
            or clean_target.startswith(("http://", "https://", "mailto:"))
        ):
            continue
        resolved = (source.parent / clean_target).resolve()
        if not resolved.exists():
            issues.append(f"{relative}: Markdown 链接目标不存在 {target}")
    return issues


def collect_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []

    for relative in CURRENT_AUTHORITY_FILES:
        if not (root / relative).is_file():
            issues.append(f"{relative}: 当前 D0/F1 权威文件缺失")

    for relative in RETIRED_ROOT_DOCUMENTS:
        if (root / relative).exists():
            issues.append(f"{relative}: 退役第二真相源不得恢复")

    for relative in RETIRED_FEATURE_NODES:
        path = root / relative
        has_files = path.is_dir() and any(
            item.is_file() for item in path.rglob("*")
        )
        if path.is_file() or has_files:
            issues.append(f"{relative}: 退役 feature-tree 节点不得恢复")

    for path in _active_instruction_files(root):
        relative = _relative(path, root)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            # 并行批次可能在扫描 glob 与读取之间原子迁移/删除文档；消失的文件
            # 不构成“退役节点恢复”，下一轮扫描会以最新磁盘集合重新判定。
            continue
        issues.extend(scan_instruction_text(relative, text))

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        if not path.is_file():
            issues.append(f"{relative}: 缺少当前架构入口")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token not in text:
                issues.append(f"{relative}: 缺少当前 D0/F1 合同标记 {token}")

    for relative in MARKDOWN_LINK_FILES:
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        issues.extend(scan_markdown_links(relative, text, root))

    return sorted(set(issues))


def main() -> int:
    issues = collect_issues()
    if issues:
        print("[retired-runtime-architecture] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(
        "[retired-runtime-architecture] OK: "
        "当前指令面仅保留 Object Facade/Data Ports + ContractGraph"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
