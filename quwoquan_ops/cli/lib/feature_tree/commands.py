"""context / overview / change-report 子命令。"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import context
from .delta import semantic_anchor_changes
from .evidence import test_spec_refs
from . import gitio
from .nodes import Node, discover_nodes, node_for_spec, parent_chain
from .ownership import owners_for_path, resolve_target
from .parsing import block_open_items, open_item_details, title
from .patterns import PATH_RE, VALID_LEVELS


def write_output(name: str, content: str) -> Path:
    context.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = context.OUTPUT_ROOT / name
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def command_context(args: argparse.Namespace) -> int:
    nodes = discover_nodes()
    by_dir = {node.directory.resolve(): node for node in nodes}
    try:
        node = resolve_target(args.target, nodes)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    chain = parent_chain(node, by_dir)
    blocks = ["# Feature Context", "", f"- TARGET：`{args.target}`", f"- 归属节点：`{node.rel}`", ""]
    for item in chain:
        blocks.extend([f"## {VALID_LEVELS[item.level]} · {item.node_id}", "", item.spec.read_text(encoding="utf-8").strip(), ""])
        if item.design.is_file():
            blocks.extend([f"### 有效设计 · {item.node_id}", "", item.design.read_text(encoding="utf-8").strip(), ""])

    metadata_refs: set[str] = set()
    for item in chain:
        for path in (item.spec, item.design):
            if path.is_file():
                metadata_refs.update(
                    ref for ref in PATH_RE.findall(path.read_text(encoding="utf-8"))
                    if ref.startswith("quwoquan_service/contracts/metadata/")
                )
    blocks.extend(["## Metadata 引用", "", *([f"- `{ref}`" for ref in sorted(metadata_refs)] or ["- 无"]), ""])

    chain_specs = {item.spec.relative_to(context.REPO_ROOT).as_posix() for item in chain}
    refs_by_test = test_spec_refs()
    matching_tests = {
        test: sorted(ref for ref in refs if ref.partition("#")[0] in chain_specs)
        for test, refs in refs_by_test.items()
        if any(ref.partition("#")[0] in chain_specs for ref in refs)
    }
    blocks.extend(["## 测试/可执行门规格引用", ""])
    if matching_tests:
        for test, refs in sorted(matching_tests.items()):
            blocks.append(f"- `{test}`")
            blocks.extend(f"  - `{ref}`" for ref in refs)
    else:
        blocks.append("- 无；若验收已关闭，`verify-feature-tree` 将阻断。")
    blocks.append("")

    siblings = [
        item for item in nodes
        if item.level == node.level and item.directory.parent == node.directory.parent and item != node
    ]
    blocks.extend(["## 相邻节点", "", *([f"- `{item.rel}`" for item in siblings] or ["- 无"]), ""])

    changed = gitio.git_changed_paths()
    chain_prefixes = [item.directory.relative_to(context.REPO_ROOT).as_posix().rstrip("/") + "/" for item in chain]
    related_changes: list[str] = []
    for rel in changed:
        if any(rel.startswith(prefix) for prefix in chain_prefixes):
            related_changes.append(rel)
            continue
        owners = owners_for_path(context.REPO_ROOT / rel, nodes)
        if len(owners) == 1 and owners[0] in chain:
            related_changes.append(rel)
    blocks.extend(["## 当前 Git 增量", "", *([f"- `{rel}`" for rel in related_changes] or ["- 无"]), ""])
    output = write_output("context.md", "\n".join(blocks))
    print(output.relative_to(context.REPO_ROOT))
    return 0


def command_overview(_: argparse.Namespace) -> int:
    nodes = discover_nodes()
    counts = {level: sum(node.level == level for node in nodes) for level in range(4)}
    open_items = [item for node in nodes for item in open_item_details(node)]
    block_items = [item for item in open_items if item["releaseImpact"] == "block"]

    def grouped(field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in open_items:
            key = str(item.get(field) or "unspecified")
            result[key] = result.get(key, 0) + 1
        return dict(sorted(result.items()))

    summary = {
        "total": len(open_items),
        "block": len(block_items),
        "track": sum(item["releaseImpact"] == "track" for item in open_items),
        "byType": grouped("type"),
        "byPriority": grouped("priority"),
    }
    lines = [
        "# Feature Tree Overview",
        "",
        f"- AppRoot：{counts[0]}",
        f"- L1：{counts[1]}",
        f"- L2：{counts[2]}",
        f"- L3：{counts[3]}",
        f"- OPEN：{summary['total']}（block={summary['block']}，track={summary['track']}）",
        f"- OPEN 类型：{', '.join(f'{key}={value}' for key, value in summary['byType'].items())}",
        f"- OPEN 优先级：{', '.join(f'{key}={value}' for key, value in summary['byPriority'].items())}",
        "",
    ]
    for l1 in (node for node in nodes if node.level == 1):
        text = l1.spec.read_text(encoding="utf-8")
        children = [node for node in nodes if node.level == 2 and node.directory.parent == l1.directory]
        open_count = len(re.findall(r"^###\s+OPEN-\d{3,}\b", text, re.MULTILINE))
        l1_prefix = l1.directory.relative_to(context.REPO_ROOT).as_posix() + "/"
        subtree_open = [item for item in open_items if str(item["node"]).startswith(l1_prefix)]
        subtree_block = sum(item["releaseImpact"] == "block" for item in subtree_open)
        lines.extend(
            [
                f"## {title(l1.spec)}",
                "",
                f"- 节点：`{l1.rel}`",
                f"- L2：{len(children)}",
                f"- 本层 OPEN：{open_count}",
                f"- 子树 OPEN：{len(subtree_open)}（block={subtree_block}）",
                "",
            ]
        )
        for l2 in children:
            story_count = sum(node.level == 3 and node.directory.parent == l2.directory for node in nodes)
            l2_open = len(re.findall(r"^###\s+OPEN-\d{3,}\b", l2.spec.read_text(encoding="utf-8"), re.MULTILINE))
            l2_prefix = l2.directory.relative_to(context.REPO_ROOT).as_posix() + "/"
            l2_subtree = [item for item in open_items if str(item["node"]).startswith(l2_prefix)]
            lines.append(
                f"- [{title(l2.spec)}]({os.path.relpath(l2.spec, context.OUTPUT_ROOT).replace(os.sep, '/')})："
                f"{story_count} Story；本层 {l2_open} OPEN；子树 {len(l2_subtree)} OPEN"
            )
        lines.append("")
    lines.extend(["## 准出阻断 OPEN", ""])
    lines.extend(
        f"- `{item['priority']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(context.REPO_ROOT / str(item['node']), context.OUTPUT_ROOT).replace(os.sep, '/')}) "
        f"· 完成判定：{item['completion']}"
        for item in block_items
    )
    if not block_items:
        lines.append("- 无")
    lines.append("")
    lines.extend(["## 全部开放事项", ""])
    lines.extend(
        f"- `{item['priority']}/{item['releaseImpact']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(context.REPO_ROOT / str(item['node']), context.OUTPUT_ROOT).replace(os.sep, '/')}) "
        f"· 完成判定：{item['completion']}"
        for item in open_items
    )
    if not open_items:
        lines.append("- 无")
    markdown_path = write_output("overview.md", "\n".join(lines))
    json_path = write_output(
        "overview.json",
        json.dumps(
            {"counts": counts, "openSummary": summary, "open": open_items},
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"{markdown_path.relative_to(context.REPO_ROOT)}\n{json_path.relative_to(context.REPO_ROOT)}")
    return 0


def command_change_report(_: argparse.Namespace) -> int:
    nodes = discover_nodes()
    by_dir = {node.directory.resolve(): node for node in nodes}
    changed = gitio.git_changed_paths()
    impacted: dict[str, list[str]] = {}
    impacted_nodes: set[Node] = set()
    unowned: list[str] = []
    for rel in changed:
        path = context.REPO_ROOT / rel
        node = None
        if rel.startswith("specs/feature-tree/"):
            current = path if path.name == "spec.md" else path.parent / "spec.md"
            while current.parent.resolve().is_relative_to(context.TREE_ROOT.resolve()):
                node = node_for_spec(current, nodes)
                if node:
                    break
                current = current.parent.parent / "spec.md"
        else:
            owners = owners_for_path(path, nodes)
            if len(owners) == 1:
                node = owners[0]
            elif rel.startswith(("quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")):
                unowned.append(rel)
        if node:
            impacted_nodes.add(node)
            chain = " -> ".join(item.node_id for item in parent_chain(node, by_dir))
            impacted.setdefault(chain, []).append(rel)

    semantic_changes: dict[str, dict[str, list[str]]] = {}
    for rel in changed:
        if rel.startswith("specs/feature-tree/") and rel.endswith(("spec.md", "design.md")):
            delta = semantic_anchor_changes(rel)
            if any(delta.values()):
                semantic_changes[rel] = delta

    metadata_changes = [rel for rel in changed if rel.startswith("quwoquan_service/contracts/metadata/")]
    metadata_breaking: list[str] = []
    for rel in metadata_changes:
        path = context.REPO_ROOT / rel
        if not path.exists():
            metadata_breaking.append(f"{rel}: 删除 canonical metadata 文件")
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", rel],
            cwd=context.REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout
        removed_contract_line = any(
            line.startswith("-") and not line.startswith("---") and re.search(r"(?:path|route|field|error|enum|operation|event|object|type|id)", line, re.IGNORECASE)
            for line in diff.splitlines()
        )
        if removed_contract_line:
            metadata_breaking.append(f"{rel}: 存在删除/收窄行，必须执行 breaking-contract 审核")

    changed_anchor_kinds = {
        anchor.split("-", 1)[0]
        for delta in semantic_changes.values()
        for key in ("added", "modified", "deleted")
        for anchor in delta[key]
    }
    required_layers: set[str] = set()
    if "UAT" in changed_anchor_kinds:
        required_layers.add("user_acceptance")
    if "DOM" in changed_anchor_kinds:
        required_layers.update({"local_contract", "api_integration"})
    if "SIT" in changed_anchor_kinds:
        required_layers.update({"local_contract", "api_integration"})
    if "GWT" in changed_anchor_kinds:
        required_layers.add("local_contract")
    required_gates = {"make verify-feature-tree"}
    if metadata_changes:
        required_gates.update({"metadata verify/codegen", "python3 quwoquan_ops/gate/verify_single_track_contracts.py"})
    if any(rel.startswith("quwoquan_app/") for rel in changed):
        required_gates.add("App scoped tests/gates")
    if any(rel.startswith("quwoquan_service/") for rel in changed):
        required_gates.add("Service scoped tests/gates")
    if any(rel.startswith("quwoquan_data/") for rel in changed):
        required_gates.add("Data scoped tests/gates")

    release_blockers: list[str] = []
    for node in impacted_nodes:
        for item in block_open_items(node.spec):
            release_blockers.append(f"{node.rel}#{item}")

    lines = [
        "# Feature Tree Change Report",
        "",
        f"- 变更文件：{len(changed)}",
        f"- 受影响父链：{len(impacted)}",
        f"- 规格/设计语义增量文件：{len(semantic_changes)}",
        f"- Metadata 变更：{len(metadata_changes)}",
        f"- 准出阻断 OPEN：{len(release_blockers)}",
        f"- 未归属工程变更：{len(unowned)}",
        "",
        "## 受影响父链",
        "",
    ]
    for chain, paths in sorted(impacted.items()):
        lines.extend([f"### {chain}", "", *[f"- `{path}`" for path in paths], ""])
    lines.extend(["## 规格与设计语义增量", ""])
    if semantic_changes:
        for rel, delta in sorted(semantic_changes.items()):
            lines.append(f"### `{rel}`")
            lines.append("")
            for kind in ("added", "modified", "deleted"):
                lines.append(f"- {kind}：{', '.join(delta[kind]) if delta[kind] else '无'}")
            lines.append("")
    else:
        lines.extend(["- 无", ""])
    lines.extend(["## Metadata breaking signal", ""])
    lines.extend([f"- `{item}`" for item in metadata_breaking] or (["- 未检测到删除/收窄信号；新增或修改仍须以 metadata gate 为准"] if metadata_changes else ["- 无 metadata 变更"]))
    lines.extend(["", "## 所需测试与门禁", "", f"- 测试层：{', '.join(sorted(required_layers)) if required_layers else '按代码影响面最小验证'}"])
    lines.extend(f"- 门禁：`{gate}`" for gate in sorted(required_gates))
    lines.extend(["", "## 准出阻断 OPEN", "", *([f"- `{item}`" for item in sorted(release_blockers)] or ["- 无"]), ""])
    lines.extend(["## 未归属工程变更", "", *([f"- `{path}`" for path in unowned] or ["- 无"]), ""])
    output = write_output("change-report.md", "\n".join(lines))
    json_output = write_output(
        "change-report.json",
        json.dumps(
            {
                "changed": changed,
                "impacted": impacted,
                "semantic_anchor_changes": semantic_changes,
                "metadata": {"changed": metadata_changes, "breaking_signals": metadata_breaking},
                "required_test_layers": sorted(required_layers),
                "required_gates": sorted(required_gates),
                "release_blockers": sorted(release_blockers),
                "unowned": unowned,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"{output.relative_to(context.REPO_ROOT)}\n{json_output.relative_to(context.REPO_ROOT)}")
    if release_blockers:
        print(
            "RELEASE_GATES_BLOCKED: 当前变更关联的正式发布准出仍被 OPEN 阻断；"
            "该事实已写入 change report，但不阻断非提升性修复的结构门禁。"
        )
    # `verify-feature-tree --changes` 校验的是目录归属和可追溯性。block OPEN
    # 仍是正式发布门禁，但不能令其本身的非提升性修复无法提交；stackctl release
    # profile 继续消费 change report 中的 release blockers 并如实阻断发布。
    return 2 if unowned else 0
