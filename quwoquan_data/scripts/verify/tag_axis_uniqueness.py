"""标签跨维度语义唯一性检查（R13-R16）。

标签体系的价值来自「同一个现实概念在系统内只有一个 tagRef」。一旦同名标签散落在
多处，召回、交集句和聚合页只能任选其一，其余副本必然成为孤儿。本模块把这条约束
拆成四条可执行规则，由 verify_tag_tree.py 调用：

- R13 跨组重名：Topic/Audience/Format/Entity 是四条正交轴，跨轴同名是允许的
  （「摄影」既是内容主题也是用户兴趣），但必须由作者显式声明 axisRole 确认，
  否则无法与「同一概念被复制」区分。
- R14 同轴重复：同一 group 内跨 dimension 重名没有正交解释，直接阻断。
- R15 自嵌套：X/Y/Y 形态既无语义也破坏路径前缀传播。
- R16 快照一致：_taxonomy.json 是下游消费的入口，必须与磁盘逐维度对齐。

地理标签天然跨层重名（多个省都有「城关区」），整体豁免重名治理。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from governance.taxonomy.axis_roles import AXIS_ROLES, axis_role_for, is_geo


def iter_tag_paths(tags_root: Path):
    """产出 (相对路径 posix, 目录 Path, 解析后的 definition dict)。"""
    for f in sorted(tags_root.rglob("_definition.json")):
        rel = f.parent.relative_to(tags_root).as_posix()
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # R3 已经报过
        yield rel, f.parent, data


def check_r13_cross_group_homonym(tags_root: Path) -> list[str]:
    """同一 label 跨 group 出现时，必须两侧都声明 axisRole，且各不相同。

    - 不声明 = 无法区分「刻意的正交轴」与「同一概念被复制」，按后者阻断。
    - 声明了但相同 = 同一个轴上出现了两份同名标签，仍然是重复，照样阻断。
    - 声明了但与路径推导不符 = 落盘的轴与它实际所在的位置矛盾，同样阻断。
    """
    errors: list[str] = []
    by_label: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for rel, path, data in iter_tag_paths(tags_root):
        if is_geo(rel):
            continue
        by_label[path.name].append((rel, data.get("axisRole")))

    for label, occurrences in sorted(by_label.items()):
        groups = {rel.split("/", 1)[0] for rel, _ in occurrences}
        if len(groups) < 2:
            continue
        declared: dict[str, list[str]] = defaultdict(list)
        for rel, axis_role in occurrences:
            if axis_role is None:
                errors.append(
                    f"R13: [{label}] 跨 group 重名（{'/'.join(sorted(groups))}）"
                    f"但 {rel} 未声明 axisRole，无法确认两轴正交")
            elif axis_role not in AXIS_ROLES:
                errors.append(
                    f"R13: {rel} 的 axisRole='{axis_role}' 不在允许集合 "
                    f"{sorted(AXIS_ROLES)} 中")
            elif axis_role != axis_role_for(rel):
                errors.append(
                    f"R13: {rel} 声明 axisRole='{axis_role}'，但按路径应为 "
                    f"'{axis_role_for(rel)}'——落盘的轴不得与所在位置矛盾")
            else:
                declared[axis_role].append(rel)
        for axis_role, paths in sorted(declared.items()):
            if len(paths) > 1:
                errors.append(
                    f"R13: [{label}] 在同一个轴 '{axis_role}' 上重复出现："
                    f"{', '.join(sorted(paths))}——同轴同名即重复，不是正交")
    return errors


def check_r13_same_as_refs_resolve(tags_root: Path) -> list[str]:
    """sameAsRefs 必须指向磁盘上真实存在的其他 tagRef，且必须是双向的。

    悬空的桥比没有桥更糟：推荐侧会按它做一次跨维度传播，权重加到一个不存在的
    tagRef 上，既拿不到内容也无法解释。单向的桥则让联通方向取决于用户先点了哪一侧。
    """
    errors: list[str] = []
    declared: dict[str, list[str]] = {}
    for rel, _path, data in iter_tag_paths(tags_root):
        refs = data.get("sameAsRefs")
        if refs is None:
            continue
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            errors.append(f"R13: {rel} 的 sameAsRefs 必须是字符串数组")
            continue
        declared[rel] = refs

    for rel, refs in sorted(declared.items()):
        for ref in refs:
            if ref == rel:
                errors.append(f"R13: {rel} 的 sameAsRefs 不得指向自己")
            elif not (tags_root / ref / "_definition.json").exists():
                errors.append(
                    f"R13: {rel} 的 sameAsRefs 指向不存在的 tagRef: {ref}")
            elif rel not in declared.get(ref, ()):
                errors.append(
                    f"R13: {rel} -> {ref} 的概念桥是单向的；{ref} 必须回指 {rel}")
    return errors


def check_r14_same_axis_duplicate(tags_root: Path) -> list[str]:
    """同一 group 内跨 dimension 重名直接阻断。

    同组同轴出现两个同名标签，必然有一个是孤儿：召回、交集和聚合页都只能选一个。
    """
    errors: list[str] = []
    by_group_label: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rel, path, _ in iter_tag_paths(tags_root):
        if is_geo(rel):
            continue
        parts = rel.split("/")
        if len(parts) < 2:
            continue
        by_group_label[(parts[0], path.name)].append(rel)

    for (group, label), paths in sorted(by_group_label.items()):
        dimensions = {p.split("/")[1] for p in paths}
        if len(dimensions) > 1:
            errors.append(
                f"R14: {group} 内 [{label}] 在多个 dimension 重复出现："
                f"{', '.join(sorted(paths))}——同轴重复必然产生孤儿，须合并到唯一真相源")
    return errors


def check_r15_self_nesting(tags_root: Path) -> list[str]:
    """禁止 X/Y/Y 形态的自嵌套节点。"""
    errors: list[str] = []
    for rel, _path, _data in iter_tag_paths(tags_root):
        parts = rel.split("/")
        if len(parts) >= 2 and parts[-1] == parts[-2]:
            errors.append(f"R15: 自嵌套节点 {rel}——子节点不得与父节点同名")
    return errors


def check_r16_snapshot_consistency(tags_root: Path, groups: list[str]) -> list[str]:
    """_taxonomy.json 快照必须与磁盘上的 group/dimension 集合与计数一致。"""
    errors: list[str] = []
    snapshot_file = tags_root / "_taxonomy.json"
    if not snapshot_file.exists():
        return ["R16: 缺少 taxonomy 快照 _taxonomy.json"]
    try:
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"R16: _taxonomy.json 解析失败: {e}"]

    disk_counts: dict[str, int] = {}
    for group in groups:
        group_dir = tags_root / group
        if not group_dir.exists():
            continue
        for dim_dir in group_dir.iterdir():
            if dim_dir.is_dir() and not dim_dir.name.startswith("_"):
                disk_counts[f"{group}/{dim_dir.name}"] = sum(
                    1 for _ in dim_dir.rglob("_definition.json"))

    snapshot_counts = {
        entry["id"]: entry.get("count")
        for entry in snapshot.get("dimensions", [])
        if isinstance(entry, dict) and entry.get("id")
    }

    for missing in sorted(set(disk_counts) - set(snapshot_counts)):
        errors.append(f"R16: 磁盘存在但快照缺失的 dimension: {missing}")
    for stale in sorted(set(snapshot_counts) - set(disk_counts)):
        errors.append(f"R16: 快照残留但磁盘已删除的 dimension: {stale}")
    for dim in sorted(set(disk_counts) & set(snapshot_counts)):
        if snapshot_counts[dim] != disk_counts[dim]:
            errors.append(
                f"R16: dimension {dim} 计数漂移：快照 {snapshot_counts[dim]} "
                f"≠ 磁盘 {disk_counts[dim]}")

    snapshot_total = snapshot.get("totalCount")
    disk_total = sum(1 for _ in tags_root.rglob("_definition.json"))
    if snapshot_total is not None and snapshot_total != disk_total:
        errors.append(
            f"R16: totalCount 漂移：快照 {snapshot_total} ≠ 磁盘 {disk_total}")
    return errors


def check_axis_uniqueness(tags_root: Path, groups: list[str]) -> list[str]:
    """按 R13-R16 顺序执行全部跨维度唯一性检查。"""
    return [
        *check_r13_cross_group_homonym(tags_root),
        *check_r13_same_as_refs_resolve(tags_root),
        *check_r14_same_axis_duplicate(tags_root),
        *check_r15_self_nesting(tags_root),
        *check_r16_snapshot_consistency(tags_root, groups),
    ]
