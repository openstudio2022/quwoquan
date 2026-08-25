"""verify 子命令与结构校验。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import context

# 本包有两种装载形态：quwoquan_ops.cli.lib.feature_tree（repo root 在 sys.path）
# 与顶层 feature_tree（cli/lib 在 sys.path）。后者下相对导入越界，回退兄弟模块名。
try:
    from ..gate_output import emit_gate_result, finding
except ImportError:
    from gate_output import emit_gate_result, finding

from .commands import command_change_report
from .delta import clause_binding_transitions, open_anchor_ratchet_targets
from .evidence import canonical_spec_ref, test_spec_refs
from . import gitio
from .nodes import Node, _visible_dirs, discover_nodes
from .ownership import validate_domain_service_ownership
from .parsing import (
    acceptance_clause_counts,
    acceptance_ids,
    acceptance_refs_in_open,
    anchorless_opens_in_text,
    engineering_roots,
    headings,
    ids,
    invalid_acceptance_refs_in_open,
    validate_acceptance_clause_coverage,
)
from .patterns import (
    CLAUSE_ANCHOR_RE,
    FORBIDDEN_CENTRAL_PATHS,
    FORBIDDEN_GLOBALS,
    FORBIDDEN_NODE_NAMES,
    LINK_RE,
    REPO_SPEC_PATH_RE,
    VALID_LEVELS,
)


ANCHORLESS_BASELINE = (
    "quwoquan_ops/policies/gates/feature_tree_anchorless_open_baseline.yaml"
)

UNBOUND_COMPOUND_BASELINE = (
    "quwoquan_ops/policies/gates/feature_tree_unbound_compound_acceptance_baseline.yaml"
)


def _baseline_entries(rel_path: str, second_key: str) -> set[tuple[str, str]]:
    """读取逐条登记册。

    只解析 ``- spec:`` 与 ``second_key`` 两个键，刻意不引入 YAML 依赖：这类文件是
    逐条清单而不是配置，形状越固定越难被悄悄放宽。
    """
    path = context.REPO_ROOT / rel_path
    if not path.is_file():
        return set()
    entries: set[tuple[str, str]] = set()
    spec = ""
    prefix = f"{second_key}:"
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- spec:"):
            spec = stripped.removeprefix("- spec:").strip()
        elif stripped.startswith(prefix) and spec:
            entries.add((spec, stripped.removeprefix(prefix).strip()))
            spec = ""
    return entries


def anchorless_baseline_entries() -> set[tuple[str, str]]:
    return _baseline_entries(ANCHORLESS_BASELINE, "open_id")


def unbound_compound_baseline_entries() -> set[tuple[str, str]]:
    return _baseline_entries(UNBOUND_COMPOUND_BASELINE, "anchor")


def unbound_compound_anchors(
    spec: Path, pending: set[str], bound: dict[str, set[int]]
) -> set[str]:
    """返回「声称已闭合、却没有任何子句级绑定」的复合验收。

    复合验收有多条结果子句，整体绑一个 spec_ref 无法说明哪条子句真被断言过；不在
    OPEN 里挂账就意味着它被当作已闭合，于是缺失的那部分证据不再有任何出口。
    """
    return {
        anchor_id
        for anchor_id, count in acceptance_clause_counts(spec).items()
        if count >= 2 and anchor_id not in pending and not bound.get(anchor_id)
    }


def validate_links(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for raw in LINK_RE.findall(text):
        raw = raw.strip().split()[0].strip("<>")
        if re.match(r"^[a-z][a-z0-9+.-]*:", raw, re.IGNORECASE):
            continue
        target_text, _, anchor = raw.partition("#")
        target = path if not target_text else (path.parent / target_text).resolve()
        if not target.exists():
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: 链接目标不存在 `{raw}`")
            continue
        if anchor and target.is_file() and anchor not in headings(target):
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: 锚点不存在 `{raw}`")
    return errors


def validate_repo_spec_paths(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for raw in REPO_SPEC_PATH_RE.findall(text):
        if not (context.REPO_ROOT / raw).is_file():
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: 反引号规格路径不存在 `{raw}`")
    return errors


def validate_journey_bidirection(nodes: list[Node]) -> list[str]:
    errors: list[str] = []
    root_text = (context.TREE_ROOT / "spec.md").read_text(encoding="utf-8")
    l1_by_id = {node.node_id: node for node in nodes if node.level == 1}
    scenario_to_journey: dict[str, tuple[str, set[str]]] = {}
    journeys = list(re.finditer(r"^###\s+(JNY-\d{3,})\b", root_text, re.MULTILINE))
    for index, match in enumerate(journeys):
        end = journeys[index + 1].start() if index + 1 < len(journeys) else len(root_text)
        next_section = re.search(r"^##\s+", root_text[match.end() :], re.MULTILINE)
        if next_section is not None:
            end = min(end, match.end() + next_section.start())
        block = root_text[match.start() : end]
        participants = set(re.findall(r"\]\(\./([A-Za-z0-9_.-]+)/spec\.md\)", block))
        scenario_matches = list(re.finditer(r"^####\s+(SCN-\d{3,})\b", block, re.MULTILINE))
        scenario_owners: set[str] = set()
        for scenario_index, scenario_match in enumerate(scenario_matches):
            scenario_end = (
                scenario_matches[scenario_index + 1].start()
                if scenario_index + 1 < len(scenario_matches)
                else len(block)
            )
            scenario_block = block[scenario_match.start() : scenario_end]
            handoff = re.search(r"^- 领域交接：(.+)$", scenario_block, re.MULTILINE)
            if not handoff:
                errors.append(
                    f"specs/feature-tree/spec.md: {scenario_match.group(1)} 缺少领域交接"
                )
                continue
            owners = {
                owner.strip()
                for owner in handoff.group(1).split("→")
                if owner.strip()
            }
            scenario = scenario_match.group(1).lower()
            scenario_to_journey[scenario] = (match.group(1), owners)
            scenario_owners.update(owners)
            for owner in owners:
                node = l1_by_id.get(owner)
                if node is None:
                    errors.append(
                        f"specs/feature-tree/spec.md: {scenario_match.group(1)} 领域交接不存在 `{owner}`"
                    )
                    continue
                l1_text = node.spec.read_text(encoding="utf-8")
                if f"../spec.md#{scenario}" not in l1_text:
                    errors.append(
                        f"{node.rel}: 未反向引用 {match.group(1)} / {scenario_match.group(1)}"
                    )
        if scenario_owners != participants:
            missing = sorted(scenario_owners - participants)
            extra = sorted(participants - scenario_owners)
            errors.append(
                f"specs/feature-tree/spec.md: {match.group(1)} 参与领域与 Scenario 交接不一致；"
                f"缺少={missing or '无'}，多余={extra or '无'}"
            )
        for participant in participants:
            if participant not in l1_by_id:
                errors.append(f"specs/feature-tree/spec.md: Journey 参与领域不存在 `{participant}`")
    for node in l1_by_id.values():
        l1_text = node.spec.read_text(encoding="utf-8")
        for scenario in set(re.findall(r"\.\./spec\.md#(scn-\d{3,})", l1_text, re.IGNORECASE)):
            journey = scenario_to_journey.get(scenario.lower())
            if journey is None:
                errors.append(f"{node.rel}: 引用了 AppRoot 不存在的 `{scenario}`")
            elif node.node_id not in journey[1]:
                errors.append(f"{node.rel}: 引用 `{scenario}`，但未登记在 {journey[0]} 的参与领域中")
    return errors


def validate_policy_governance() -> list[str]:
    errors: list[str] = []
    root = context.REPO_ROOT / "quwoquan_ops" / "policies" / "gates"
    if not root.exists():
        return errors
    required = {"owner", "reason", "expires_when"}
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        values: dict[str, object] = {}
        if path.suffix == ".json":
            try:
                values = json.loads(path.read_text(encoding="utf-8")).get("_governance", {})
            except (json.JSONDecodeError, AttributeError):
                errors.append(f"{path.relative_to(context.REPO_ROOT)}: policy JSON 无法解析")
                continue
        elif path.suffix in {".yaml", ".yml"}:
            text = path.read_text(encoding="utf-8")
            block = re.search(r"^governance:\s*$([\s\S]*?)(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)", text, re.MULTILINE)
            if block:
                values = {key: value.strip() for key, value in re.findall(r"^\s{2}(owner|reason|expires_when):\s*(.+)$", block.group(1), re.MULTILINE)}
        else:
            continue
        missing = sorted(key for key in required if not values.get(key))
        if missing:
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: policy governance 缺少 {', '.join(missing)}")
    return errors


def command_verify(args: argparse.Namespace) -> int:
    errors: list[str] = []
    nodes = discover_nodes()
    for required in (context.TREE_ROOT / "README.md", context.TREE_ROOT / "spec.md", context.TREE_ROOT / "design.md"):
        if not required.is_file():
            errors.append(f"缺少 `{required.relative_to(context.REPO_ROOT)}`")
    for name in FORBIDDEN_GLOBALS:
        if (context.TREE_ROOT / name).exists():
            errors.append(f"禁止全局注册表回潮：`specs/feature-tree/{name}`")
    for path in (context.REPO_ROOT / "specs" / "l1_index.yaml", context.REPO_ROOT / "specs" / "engineering_directory_manifest.yaml"):
        if path.exists():
            errors.append(f"禁止全局注册表回潮：`{path.relative_to(context.REPO_ROOT)}`")
    for raw in FORBIDDEN_CENTRAL_PATHS:
        if (context.REPO_ROOT / raw).exists():
            errors.append(f"禁止中央注册/台账/历史目录回潮：`{raw}`")

    node_dirs = {node.directory.resolve() for node in nodes}
    for node in nodes:
        if not node.spec.is_file():
            errors.append(f"{node.directory.relative_to(context.REPO_ROOT)}: 缺少 spec.md")
            continue
        first = node.spec.read_text(encoding="utf-8").splitlines()[0]
        expected = f"# {VALID_LEVELS[node.level]}"
        if not first.startswith(expected):
            errors.append(f"{node.rel}: 首行必须以 `{expected}` 开始")
        doc_ids = ids(node.spec)
        duplicates = sorted({item for item in doc_ids if doc_ids.count(item) > 1})
        if duplicates:
            errors.append(f"{node.rel}: ID 重复：{', '.join(duplicates)}")
        for acceptance_id in sorted(invalid_acceptance_refs_in_open(node.spec)):
            errors.append(
                f"{node.rel}: OPEN 完成判定引用不存在的验收 `{acceptance_id}`"
            )
        if node.level in (0, 1) and not node.design.is_file():
            errors.append(f"{node.directory.relative_to(context.REPO_ROOT)}: AppRoot/L1 必须有 design.md")
        if node.level == 3 and node.design.exists():
            errors.append(f"{node.directory.relative_to(context.REPO_ROOT)}: L3 禁止 design.md")
        if node.level == 2:
            spec_text = node.spec.read_text(encoding="utf-8")
            if node.design.is_file() and "设计触发原因" not in node.design.read_text(encoding="utf-8"):
                errors.append(f"{node.design.relative_to(context.REPO_ROOT)}: 缺少设计触发原因")
            if not node.design.is_file() and not re.search(r"\.\./design\.md#dec-\d{3,}", spec_text, re.IGNORECASE):
                errors.append(f"{node.rel}: 无本层 design 时必须指向父 L1 DEC")
        if node.level < 3:
            direct = [item for item in _visible_dirs(node.directory) if (item / "spec.md").is_file()]
            spec_text = node.spec.read_text(encoding="utf-8")
            expected_links = {child.name for child in direct}
            actual_links = set(re.findall(r"\]\(\./([A-Za-z0-9_.-]+)/spec\.md(?:#[^)]+)?\)", spec_text))
            for child in direct:
                if f"./{child.name}/spec.md" not in spec_text:
                    errors.append(f"{node.rel}: 缺少直接子节点链接 `./{child.name}/spec.md`")
            for stale in sorted(actual_links - expected_links):
                errors.append(f"{node.rel}: 声明了非直接子节点 `./{stale}/spec.md`")
        for item in node.directory.iterdir():
            if node.level > 0 and item.is_file() and item.name in FORBIDDEN_NODE_NAMES:
                errors.append(f"{item.relative_to(context.REPO_ROOT)}: 节点禁止文件")
            if node.level == 3 and item.is_dir():
                errors.append(f"{item.relative_to(context.REPO_ROOT)}: L3 不得嵌套目录")
        if "--" in node.node_id:
            errors.append(f"{node.rel}: 节点名不得使用 `--` 表达伪层级")
        if node.level == 2 and "journey" in node.node_id.lower():
            errors.append(f"{node.rel}: Journey 不得作为 L2 目录层")
        errors.extend(validate_links(node.spec))
        errors.extend(validate_repo_spec_paths(node.spec))
        if node.design.is_file():
            design_ids = ids(node.design)
            design_duplicates = sorted({item for item in design_ids if design_ids.count(item) > 1})
            if design_duplicates:
                errors.append(f"{node.design.relative_to(context.REPO_ROOT)}: ID 重复：{', '.join(design_duplicates)}")
            errors.extend(validate_links(node.design))
            errors.extend(validate_repo_spec_paths(node.design))

    for path in context.TREE_ROOT.rglob("*"):
        if path.is_file() and path.name not in {"README.md", "spec.md", "design.md"}:
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: 特性树内存在非规格/设计文件")
        if path.is_dir() and path != context.TREE_ROOT and path.resolve() not in node_dirs:
            errors.append(f"{path.relative_to(context.REPO_ROOT)}: 目录不是可识别节点")

    claims: dict[str, list[str]] = {}
    for node in (item for item in nodes if item.level == 1):
        roots = engineering_roots(node)
        if not roots:
            errors.append(f"{node.rel}: 缺少可解析的工程归属路径")
        for root in roots:
            if not (context.REPO_ROOT / root).exists():
                errors.append(f"{node.rel}: 工程归属路径不存在 `{root}`")
            claims.setdefault(root.rstrip("/"), []).append(node.node_id)
    for root, owners in claims.items():
        if len(owners) > 1:
            errors.append(f"工程归属重叠 `{root}`：{', '.join(sorted(owners))}")

    errors.extend(validate_domain_service_ownership(nodes))
    errors.extend(validate_journey_bidirection(nodes))
    errors.extend(validate_policy_governance())

    refs_by_test = test_spec_refs()
    referenced: set[str] = set()
    bound_clauses: dict[str, dict[str, set[int]]] = {}
    for test, refs in refs_by_test.items():
        for ref in refs:
            target_text, _, anchor = ref.partition("#")
            target = context.REPO_ROOT / target_text
            clause_match = CLAUSE_ANCHOR_RE.match(anchor)
            if clause_match:
                anchor_id = clause_match.group(1).upper()
                index = int(clause_match.group(2))
                count = acceptance_clause_counts(target).get(anchor_id, 0)
                if not target.is_file() or count == 0:
                    errors.append(f"{test}: 无效 spec_ref `{ref}`")
                elif not 1 <= index <= count:
                    errors.append(
                        f"{test}: 悬空子句 spec_ref `{ref}`，该验收只有 {count} 条结果子句"
                    )
                else:
                    referenced.add(f"{target_text}#{clause_match.group(1)}")
                    bound_clauses.setdefault(target_text, {}).setdefault(anchor_id, set()).add(index)
                continue
            if not target.is_file() or anchor not in headings(target):
                errors.append(f"{test}: 无效 spec_ref `{ref}`")
            else:
                referenced.add(ref)
    changed_specs = {
        rel for rel in gitio.git_changed_paths()
        if rel.startswith("specs/feature-tree/") and rel.endswith("spec.md")
    }
    anchorless_baseline = anchorless_baseline_entries()
    unbound_baseline = unbound_compound_baseline_entries()
    live_unbound: set[tuple[str, str]] = set()
    for node in nodes:
        pending = acceptance_refs_in_open(node.spec)
        for acceptance_id in acceptance_ids(node.spec):
            ref = canonical_spec_ref(node.spec, acceptance_id)
            if ref not in referenced and acceptance_id not in pending:
                errors.append(f"{node.rel}#{acceptance_id.lower()}: 已支持验收缺少真实测试/可执行门 spec_ref")
        errors.extend(
            validate_acceptance_clause_coverage(
                node.rel,
                acceptance_clause_counts(node.spec),
                pending,
                bound_clauses.get(node.rel, {}),
                clause_binding_transitions(node.rel) if node.rel in changed_specs else set(),
            )
        )
        # anchorless 是全树存量硬门，不是「本次改动」增量门。只查 changed_specs 时，
        # 存量 anchorless OPEN 永远不会被任何一次提交看见，于是长期沉淀且不断累积。
        anchorless = anchorless_opens_in_text(node.spec.read_text(encoding="utf-8"))
        for open_id in sorted(anchorless):
            if (node.rel, open_id) in anchorless_baseline:
                continue
            errors.append(
                f"{node.rel}#{open_id.lower()}: 完成判定未引用任何验收锚点，"
                "该 OPEN 结构上不可裁定；请引用 GWT/SIT/DOM/UAT（必要时含子句 .tN），"
                "缺对应验收时先补锚点"
            )
        # 与 anchorless 同理，这里也必须是全树存量硬门。删掉一条「要求逐子句绑定」的
        # OPEN 却不补绑定时，欠的证据会原地滑进这个集合；只打印总数的话，既没人被
        # 拦住，也没有任何记录说明它是从哪一次删除漏过来的。
        for anchor_id in sorted(
            unbound_compound_anchors(node.spec, pending, bound_clauses.get(node.rel, {}))
        ):
            live_unbound.add((node.rel, anchor_id))
            if (node.rel, anchor_id) in unbound_baseline:
                continue
            errors.append(
                f"{node.rel}#{anchor_id.lower()}: 复合验收被当作已闭合，却没有任何"
                "子句级 spec_ref；请为每条结果子句补 `.tN` 绑定，或在 OPEN 里挂账"
            )

    if args.changes:
        report_args = argparse.Namespace()
        change_report_code = command_change_report(report_args)
        if change_report_code != 0:
            # command_change_report 仅在 unowned 时非 0；release_blockers 只打印
            # RELEASE_GATES_BLOCKED，不阻断非提升性结构门禁 / commit_gate。
            errors.append(
                "当前 Git diff 存在未归属工程变更；见 feature-tree/change-report.md"
            )
    emit_gate_result(
        "verify-feature-tree", [finding(error) for error in errors], context.REPO_ROOT
    )
    if errors:
        print(f"GATE_BLOCK: feature-tree 发现 {len(errors)} 个问题", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    counts = {level: sum(node.level == level for node in nodes) for level in range(4)}
    print(f"OK: directory-native feature tree verified (AppRoot={counts[0]}, L1={counts[1]}, L2={counts[2]}, L3={counts[3]})")
    print(
        f"RATCHET: 声称已闭合但尚无子句级绑定的复合验收 {len(live_unbound)} 条"
        f"（全部已登记于 {UNBOUND_COMPOUND_BASELINE}；不在册者直接 BLOCK）"
    )
    bound_since_baseline = unbound_baseline - live_unbound
    if bound_since_baseline:
        # 与 anchorless 一致：先补绑定后删登记是正常顺序，不该被判成失败。
        print(f"RATCHET: 其中 {len(bound_since_baseline)} 条已补齐子句绑定，请同批从基线删除对应条目：")
        for spec_rel, anchor_id in sorted(bound_since_baseline):
            print(f"  - {spec_rel} {anchor_id}")
    live_anchorless = {
        (node.rel, open_id)
        for node in nodes
        if node.spec.is_file()
        for open_id in anchorless_opens_in_text(node.spec.read_text(encoding="utf-8"))
    }
    resolved = anchorless_baseline - live_anchorless
    print(
        f"RATCHET: 完成判定不引用任何验收锚点、结构上不可裁定的 OPEN {len(live_anchorless)} 条"
        f"（全部已登记于 {ANCHORLESS_BASELINE}；不在册者直接 BLOCK）"
    )
    if resolved:
        # 只提示不阻断：补锚点和删登记应该同批提交，但先补后删的顺序不该被判成失败。
        print(
            f"RATCHET: 其中 {len(resolved)} 条已补齐锚点，请同批从基线删除对应条目："
        )
        for spec_rel, open_id in sorted(resolved):
            print(f"  - {spec_rel} {open_id}")
    return 0
