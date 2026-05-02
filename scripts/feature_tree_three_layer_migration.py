#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


DOC_FILES = ("spec.md", "design.md", "tasks.md", "acceptance.yaml")


@dataclass(frozen=True)
class NodeMapping:
    l1_capability: str
    current_path: str
    current_level: str
    target_l2_story_slug: str
    action: str
    task_bucket: str
    depth: int


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def list_l1_dirs(feature_tree_root: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in feature_tree_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ],
        key=lambda path: path.name,
    )


def collect_feature_dirs(l1_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for candidate in sorted(l1_dir.rglob("*"), key=lambda path: (len(path.parts), str(path))):
        if not candidate.is_dir():
            continue
        if not any((candidate / name).exists() for name in DOC_FILES):
            continue
        dirs.append(candidate)
    return dirs


def derive_level(path: Path) -> str:
    acceptance = read_yaml(path / "acceptance.yaml")
    level = str(acceptance.get("level", "")).strip()
    if level:
        return level
    return "L2_story" if (path / "acceptance.yaml").exists() else ""


def target_story_slug(relative_parts: tuple[str, ...]) -> str:
    return "--".join(relative_parts)


def build_mappings(feature_tree_root: Path) -> list[NodeMapping]:
    mappings: list[NodeMapping] = []
    for l1_dir in list_l1_dirs(feature_tree_root):
        l1_name = l1_dir.name
        for feature_dir in collect_feature_dirs(l1_dir):
            rel = feature_dir.relative_to(l1_dir)
            if not rel.parts:
                continue

            depth = len(rel.parts)
            current_level = derive_level(feature_dir)

            if depth <= 3:
                action = "keep_as_story"
                target_slug = target_story_slug(rel.parts)
                task_bucket = ""
            else:
                action = "fold_into_tasks"
                target_slug = target_story_slug(rel.parts[:-1])
                task_bucket = rel.parts[-1]

            mappings.append(
                NodeMapping(
                    l1_capability=l1_name,
                    current_path=str(feature_dir.relative_to(feature_tree_root)),
                    current_level=current_level or "unknown",
                    target_l2_story_slug=target_slug,
                    action=action,
                    task_bucket=task_bucket,
                    depth=depth,
                )
            )
    return mappings


def write_mapping_file(mappings: Iterable[NodeMapping], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "l1_capability": item.l1_capability,
            "current_path": item.current_path,
            "current_level": item.current_level,
            "target_l2_story_slug": item.target_l2_story_slug,
            "action": item.action,
            "task_bucket": item.task_bucket,
            "depth": item.depth,
        }
        for item in mappings
    ]
    output_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def ensure_story_dir(l1_dir: Path, slug: str) -> Path:
    story_dir = l1_dir / slug
    story_dir.mkdir(parents=True, exist_ok=True)
    return story_dir


def initialize_story_docs(story_dir: Path, slug: str) -> None:
    for file_name in DOC_FILES:
        path = story_dir / file_name
        if path.exists():
            continue
        if file_name.endswith(".md"):
            path.write_text(f"# {slug}\n", encoding="utf-8")
        else:
            path.write_text(
                yaml.safe_dump(
                    {
                        "feature": slug,
                        "level": "L2_story",
                        "archived": False,
                        "execution": {
                            "local_gate": "make gate",
                            "full_gate": "make gate-full",
                        },
                        "level_acceptance": {},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
def merge_markdown(target_file: Path, source_file: Path, heading: str) -> None:
    if not source_file.exists():
        return
    source = source_file.read_text(encoding="utf-8").strip()
    if not source:
        return
    if not target_file.exists():
        target_file.write_text(source + "\n", encoding="utf-8")
        return
    target = target_file.read_text(encoding="utf-8")
    if source in target:
        return
    block = f"\n\n## {heading}\n\n{source}\n"
    target_file.write_text(target.rstrip() + block, encoding="utf-8")


def rewrite_acceptance_level(path: Path, level: str) -> None:
    data = read_yaml(path)
    data["level"] = level
    tree_context = data.get("tree_context")
    if isinstance(tree_context, dict):
        tree_context["feature_level"] = level
        data["tree_context"] = tree_context
    for key in ("current_level", "current_path", "acceptance_inherits_from"):
        data.pop(key, None)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def merge_current_acceptance(target_file: Path, source_file: Path, source_path: str, task_bucket: str) -> None:
    if not source_file.exists():
        return
    target_data = read_yaml(target_file)
    source_data = read_yaml(source_file)
    entries = target_data.get("current_merged_acceptance") or []
    if not isinstance(entries, list):
        entries = []
    entries.append(
        {
            "source_path": source_path,
            "task_bucket": task_bucket,
            "migrated_as": "L3_task",
        }
    )
    target_data["current_merged_acceptance"] = entries
    target_file.write_text(
        yaml.safe_dump(target_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def append_current_task(target_tasks: Path, mapping: NodeMapping) -> None:
    source_heading = f"Migrated current node: `{mapping.task_bucket}`"
    line = f"- [ ] {source_heading} (from `{mapping.current_path}`)\n"
    content = target_tasks.read_text(encoding="utf-8") if target_tasks.exists() else "# 任务列表\n"
    if line in content:
        return
    if "## 当前交付任务" not in content:
        content = content.rstrip() + "\n\n## 当前交付任务\n"
    parts = content.split("## 搁置任务（带规划）", 1)
    if len(parts) == 2:
        head, tail = parts
        new_head = head.rstrip() + "\n" + line + "\n"
        target_tasks.write_text(new_head + "## 搁置任务（带规划）" + tail, encoding="utf-8")
    else:
        target_tasks.write_text(content.rstrip() + "\n" + line, encoding="utf-8")


def move_story(source_dir: Path, target_dir: Path, relative_source: str) -> None:
    for file_name in DOC_FILES:
        source_file = source_dir / file_name
        target_file = target_dir / file_name
        if not source_file.exists():
            continue
        if file_name == "acceptance.yaml":
            if not target_file.exists() or target_file.read_text(encoding="utf-8").strip() in {"", "{}", "null"}:
                shutil.copy2(source_file, target_file)
            rewrite_acceptance_level(target_file, "L2_story")
        else:
            merge_markdown(target_file, source_file, f"Migrated from `{relative_source}`")


def cleanup_empty_dirs(root: Path) -> None:
    for candidate in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if not candidate.is_dir():
            continue
        if any(candidate.iterdir()):
            continue
        candidate.rmdir()


def apply_migration(feature_tree_root: Path, mappings: list[NodeMapping]) -> None:
    by_l1: dict[str, list[NodeMapping]] = {}
    for mapping in mappings:
        by_l1.setdefault(mapping.l1_capability, []).append(mapping)

    for l1_name, items in by_l1.items():
        l1_dir = feature_tree_root / l1_name
        l1_acceptance = l1_dir / "acceptance.yaml"
        if l1_acceptance.exists():
            rewrite_acceptance_level(l1_acceptance, "L1_capability")

        keep_items = sorted(
            [item for item in items if item.action == "keep_as_story"],
            key=lambda item: item.depth,
        )
        for item in keep_items:
            source_dir = feature_tree_root / item.current_path
            target_dir = ensure_story_dir(l1_dir, item.target_l2_story_slug)
            if source_dir.resolve() != target_dir.resolve():
                move_story(source_dir, target_dir, item.current_path)
            else:
                acceptance = target_dir / "acceptance.yaml"
                if acceptance.exists():
                    rewrite_acceptance_level(acceptance, "L2_story")

        fold_items = sorted(
            [item for item in items if item.action == "fold_into_tasks"],
            key=lambda item: item.depth,
        )
        for item in fold_items:
            source_dir = feature_tree_root / item.current_path
            target_dir = ensure_story_dir(l1_dir, item.target_l2_story_slug)
            initialize_story_docs(target_dir, item.target_l2_story_slug)
            merge_markdown(target_dir / "spec.md", source_dir / "spec.md", f"Folded current node `{item.task_bucket}`")
            merge_markdown(target_dir / "design.md", source_dir / "design.md", f"Folded current node `{item.task_bucket}`")
            merge_markdown(target_dir / "tasks.md", source_dir / "tasks.md", f"Folded current node `{item.task_bucket}`")
            append_current_task(target_dir / "tasks.md", item)
            merge_current_acceptance(
                target_dir / "acceptance.yaml",
                source_dir / "acceptance.yaml",
                item.current_path,
                item.task_bucket,
            )

        # Remove all old nested feature directories, then recreate target stories in-place.
        for item in sorted(items, key=lambda item: item.depth, reverse=True):
            source_dir = feature_tree_root / item.current_path
            if source_dir.exists() and source_dir.parent != l1_dir:
                shutil.rmtree(source_dir)

        cleanup_empty_dirs(l1_dir)


def normalize_root_docs(feature_tree_root: Path) -> None:
    for l1_dir in list_l1_dirs(feature_tree_root):
        design = l1_dir / "design.md"
        if not design.exists():
            design.write_text(
                f"# {l1_dir.name} 设计\n\n## 设计动因\n\n由三层特性树迁移脚本补齐，请后续人工收敛。\n",
                encoding="utf-8",
            )
        tasks = l1_dir / "tasks.md"
        if not tasks.exists():
            tasks.write_text(
                "# 任务列表\n\n## 当前交付任务\n- [ ] 由三层迁移后补齐能力治理任务\n\n## 搁置任务（带规划）\n- [ ] 无\n\n## 未来演进任务\n- [ ] 无\n",
                encoding="utf-8",
            )
        acceptance = l1_dir / "acceptance.yaml"
        if not acceptance.exists():
            acceptance.write_text(
                yaml.safe_dump(
                    {
                        "feature": l1_dir.name,
                        "level": "L1_capability",
                        "archived": False,
                        "execution": {
                            "local_gate": "make gate",
                            "full_gate": "make gate-full",
                        },
                        "level_acceptance": {},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        rewrite_acceptance_level(acceptance, "L1_capability")

        for story_dir in sorted([path for path in l1_dir.iterdir() if path.is_dir()], key=lambda path: path.name):
            initialize_story_docs(story_dir, story_dir.name)
            rewrite_acceptance_level(story_dir / "acceptance.yaml", "L2_story")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="specs/feature-tree")
    parser.add_argument("--map-out", default="tmp/feature_tree_migration_map.yaml")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    feature_tree_root = Path(args.root).resolve()
    map_out = Path(args.map_out).resolve()

    mappings = build_mappings(feature_tree_root)
    write_mapping_file(mappings, map_out)
    normalize_root_docs(feature_tree_root)

    if args.apply:
        apply_migration(feature_tree_root, mappings)


if __name__ == "__main__":
    main()
