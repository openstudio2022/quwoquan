#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DOC_FILES = ("spec.md", "design.md", "tasks.md", "acceptance.yaml")


def list_child_dirs(root: Path) -> list[Path]:
    return sorted(
        [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")],
        key=lambda path: path.name,
    )


def ensure_feature_docs(feature_dir: Path, l1_name: str, l2_name: str) -> None:
    feature_dir.mkdir(parents=True, exist_ok=True)

    spec = feature_dir / "spec.md"
    if not spec.exists():
        spec.write_text(
            "\n".join(
                [
                    f"# L2 Feature：{l2_name}",
                    "",
                    "## 背景与动机",
                    "",
                    f"- 该 Feature 由 `{l1_name}` 下的扁平 Story 目录自动回收而来。",
                    "",
                    "## Feature 范围",
                    "",
                    "- 聚合其下相关 Story，统一承载范围与边界。",
                    "",
                    "## 不做什么（Out of Scope）",
                    "",
                    "- 不在 Feature 层继续新建 subfeature/detail/leaf 目录。",
                    "",
                    "## 约束",
                    "",
                    "- 具体实现与验收下沉到各个 L3 Story。",
                    "",
                ]
            )
            + "\n"
        )

    design = feature_dir / "design.md"
    if not design.exists():
        design.write_text(
            "\n".join(
                [
                    f"# {l2_name} 设计方案",
                    "",
                    "## 设计动因",
                    "",
                    "- 由目录迁移自动生成，后续由人工持续收敛。",
                    "",
                    "## Feature 聚合策略",
                    "",
                    "- 统一聚合相关 Story。",
                    "- Feature 层只保留范围、边界和跨 Story 决策。",
                    "",
                ]
            )
            + "\n"
        )

    tasks = feature_dir / "tasks.md"
    if not tasks.exists():
        tasks.write_text(
            "\n".join(
                [
                    "# 任务列表",
                    "",
                    "## 当前交付任务",
                    "- [ ] 收敛 Feature 边界与 Story 划分",
                    "",
                    "## 搁置任务（带规划）",
                    "- [ ] 无",
                    "",
                    "## 未来演进任务",
                    "- [ ] 无",
                    "",
                ]
            )
        )

    acceptance = feature_dir / "acceptance.yaml"
    if not acceptance.exists():
        acceptance.write_text(
            "\n".join(
                [
                    f'feature: "{l2_name}"',
                    'level: "L2_feature"',
                    "archived: false",
                    "execution:",
                    '  local_gate: "make gate"',
                    '  full_gate: "make gate-full"',
                    "level_acceptance:",
                    "  A1:",
                    '    criteria: "Feature 范围、边界与 Story 归属已冻结"',
                    "    status: pending",
                    "    linked_tasks: []",
                    "    test_layers:",
                    "      T1: required",
                    "      T2: optional",
                    "      T3: optional",
                    "      T4: optional",
                    "    tests: []",
                    "",
                ]
            )
        )


def rewrite_level(acceptance_path: Path, new_level: str) -> None:
    if not acceptance_path.exists():
        return

    lines = acceptance_path.read_text().splitlines()
    rewritten: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("level:"):
            indent = line[: len(line) - len(line.lstrip())]
            rewritten.append(f'{indent}level: "{new_level}"')
            replaced = True
            continue
        if stripped.startswith("feature_level:"):
            continue
        rewritten.append(line)

    if not replaced:
        rewritten.insert(1, f'level: "{new_level}"')

    acceptance_path.write_text("\n".join(rewritten) + "\n")


def move_story(source_dir: Path, feature_dir: Path, story_name: str) -> None:
    target_dir = feature_dir / story_name
    if target_dir.exists():
        raise RuntimeError(f"target story already exists: {target_dir}")
    shutil.move(str(source_dir), str(target_dir))
    rewrite_level(target_dir / "acceptance.yaml", "L3_story")


def migrate_l1(l1_dir: Path) -> None:
    child_dirs = list_child_dirs(l1_dir)
    root_acceptance = l1_dir / "acceptance.yaml"
    rewrite_level(root_acceptance, "L1_capability")

    for child_dir in child_dirs:
        name = child_dir.name
        if "--" not in name:
            rewrite_level(child_dir / "acceptance.yaml", "L2_feature")
            continue

        feature_name, story_name = name.split("--", 1)
        feature_dir = l1_dir / feature_name
        if feature_dir != child_dir:
            ensure_feature_docs(feature_dir, l1_dir.name, feature_name)
            move_story(child_dir, feature_dir, story_name)

    for child_dir in list_child_dirs(l1_dir):
        rewrite_level(child_dir / "acceptance.yaml", "L2_feature")
        for story_dir in list_child_dirs(child_dir):
            rewrite_level(story_dir / "acceptance.yaml", "L3_story")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore feature tree into L1/L2_feature/L3_story directories.")
    parser.add_argument("l1", nargs="+", help="L1 capability directories under specs/feature-tree")
    parser.add_argument(
        "--root",
        default="specs/feature-tree",
        help="feature tree root directory",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    for l1_name in args.l1:
        l1_dir = root / l1_name
        if not l1_dir.is_dir():
            raise SystemExit(f"missing l1 directory: {l1_dir}")
        migrate_l1(l1_dir)
        print(f"[migrate] restored three-level dirs for {l1_name}")


if __name__ == "__main__":
    main()
