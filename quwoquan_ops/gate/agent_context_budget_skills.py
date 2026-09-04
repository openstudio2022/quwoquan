"""Agent context gate 的 Workflow Skill 发现与 metadata 校验。"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

import yaml


def frontmatter(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """解析 Skill/command 共用的 YAML frontmatter。"""

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


def discover_workflow_skill_metadata(
    root: Path,
    *,
    skill_line_budget: int,
    description_each_budget: int,
    frontmatter_fields: Collection[str],
    required_sections: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """发现并完整校验仓库声明的 Workflow Skill。"""

    agents_root = root / ".agents"
    skills_root = agents_root / "skills"
    workflows: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    if agents_root.is_symlink():
        return workflows, [".agents 必须是 real non-symlink directory"]
    if not agents_root.is_dir():
        return workflows, [".agents 不存在"]
    if skills_root.is_symlink():
        return workflows, [".agents/skills 必须是 real non-symlink directory"]
    if not skills_root.is_dir():
        return workflows, [".agents/skills 不存在"]
    try:
        children = sorted(skills_root.iterdir(), key=lambda item: item.name)
    except OSError as error:
        return workflows, [f".agents/skills 无法枚举（{error}）"]

    directories: list[Path] = []
    for child in children:
        if child.is_symlink():
            issues.append(
                f"{child.relative_to(root).as_posix()}: "
                "Skill 直接子项必须是 real directory，不得是 symlink"
            )
            continue
        if child.is_dir():
            directories.append(child)

    for directory in directories:
        issue_count = len(issues)
        path = directory / "SKILL.md"
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            issues.append(
                f"{relative}: 每个 Skill 直接子目录必须包含 regular non-symlink SKILL.md"
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            issues.append(f"{relative}: 无法读取 SKILL.md（{error}）")
            continue
        fields, error = frontmatter(text)
        if error or fields is None:
            issues.append(f"{relative}: {error or 'frontmatter 无效'}")
            continue
        metadata = fields.get("metadata")
        if not isinstance(metadata, dict):
            issues.append(f"{relative}: metadata 必须是映射")
        elif metadata.get("kind") != "workflow":
            issues.append(f"{relative}: metadata.kind 必须为 workflow")
        if fields.get("name") != directory.name:
            issues.append(f"{relative}: name={fields.get('name')!r} 与目录名不一致")
        extra = sorted(set(fields) - set(frontmatter_fields))
        if extra:
            issues.append(f"{relative}: frontmatter 含非开放字段 {extra}")
        description = fields.get("description")
        if not isinstance(description, str) or not description:
            issues.append(f"{relative}: 缺 description")
        elif len(description) > description_each_budget:
            issues.append(f"{relative}: description 超过 {description_each_budget} 字符")
        if len(text.splitlines()) > skill_line_budget:
            issues.append(f"{relative}: 超过 {skill_line_budget} 行，重资料应按需放 references")
        declared = metadata.get("command") if isinstance(metadata, dict) else None
        if declared is not None and declared != f"/{directory.name}":
            issues.append(
                f"{relative}: metadata.command={declared!r}，应为 /{directory.name}"
            )
        headings = re.findall(r"^##\s+(.+?)\s*$", text, re.M)
        if headings != list(required_sections):
            issues.append(
                f"{relative}: 二级段落必须且只能按顺序为 "
                + " / ".join(required_sections)
            )
        if any(
            token in text
            for token in ("completion-criteria.md", "interaction-protocols.md")
        ):
            issues.append(f"{relative}: 完成与交互契约必须就地声明，不得跳转共享文档")
        if len(issues) == issue_count:
            workflows[directory.name] = fields
    return workflows, issues


__all__ = ["discover_workflow_skill_metadata", "frontmatter"]
