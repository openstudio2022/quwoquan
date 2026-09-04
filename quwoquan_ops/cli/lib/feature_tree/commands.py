"""context / overview / change-report 子命令。"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


from ..agent_governance_contract import (
    contract_schema_version,
    contract_section,
    declared_object,
    validate_feature_context_manifest,
)
from . import context, gitio
from .content_addressed_writer import (
    _content_addressed_path as _content_addressed_path,
    _fd_path as _fd_path,
    _read_exact_bytes_at as _read_exact_bytes_at,
    _safe_directory_fd as _safe_directory_fd,
    _write_content_addressed_bytes as _write_content_addressed_bytes,
    _write_content_addressed_json as _write_content_addressed_json,
    fcntl as fcntl,
)
from .delta import semantic_anchor_changes
from .evidence import extract_spec_refs, test_spec_refs
from .nodes import Node, discover_nodes, node_for_spec, parent_chain
from .ownership import TargetResolution, owners_for_path, resolve_target_details
from .parsing import block_open_items, open_item_details, title
from .patterns import PATH_RE, VALID_LEVELS
from ..evidence_fingerprint import canonical_json_bytes
from ..candidate_evidence import CandidateEvidenceError, build_candidate_evidence
from ..feature_context_fingerprint import (
    build_feature_context_fingerprint,
    embedded_fingerprint_binding,
    referenced_fingerprint_binding,
)

MANIFEST_MAX_BYTES = int(contract_section("feature_context_manifest")["max_bytes"])
CANONICAL_FEATURE_SPEC_RE = re.compile(
    r"^specs/feature-tree/(?:[A-Za-z0-9][A-Za-z0-9_.-]*/)*spec\.md$"
)
_MARKDOWN_INLINE_LINK_RE = re.compile(
    r"(?<!!)\[[^]\n]*\]\(\s*"
    r"(?P<destination><[^>\n]+>|[^()\s]+)"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?\s*\)"
)
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_SPEC_REF_CODE_SPAN_RE = re.compile(
    r"^\s*spec_ref\s*:\s*(?P<reference>.+?)\s*$",
    re.IGNORECASE,
)
_BRACED_DIRECT_REFERENCE_RE = re.compile(
    r"^(?P<prefix>[^{}]*)\{(?P<options>[^{}]+)\}(?P<suffix>[^{}]*)$"
)


def _is_service_contract_path(path: str) -> bool:
    parts = Path(path).parts
    return (
        len(parts) >= 4
        and parts[:2] == ("quwoquan_service", "services")
        and not any(character in parts[2] for character in "*?[]{}")
        and parts[3] == "contracts"
    )


def _is_metadata_contract_file(path: str) -> bool:
    return (
        path.startswith("quwoquan_service/contracts/metadata/")
        and path.endswith(".yaml")
    )


def _canonical_reference_kind(path: str) -> str | None:
    """按仓库物理边界判定 canonical 类型，不维护文件 allowlist。"""

    if CANONICAL_FEATURE_SPEC_RE.fullmatch(path):
        return "spec"
    parts = Path(path).parts
    if (
        len(parts) == 3
        and parts[:2] == ("quwoquan_ops", "policies")
        and parts[2].endswith(".yaml")
    ):
        return "contract"
    if _is_metadata_contract_file(path):
        return "contract"
    if _is_service_contract_path(path):
        return "contract"
    return None


def _source_label(source: Path) -> str:
    try:
        return _relative(source)
    except ValueError:
        return str(source)


def _resolved_direct_reference(
    reference: str,
    *,
    source: Path,
) -> tuple[str, str | None, str] | None:
    """解析一个直接引用；canonical 候选一旦无效即 fail-closed。"""

    raw = reference.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1].strip()
    if not raw or raw.startswith("#"):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw) or raw.startswith("//"):
        return None

    path_text, separator, anchor = raw.partition("#")
    path_text = path_text.strip()
    anchor_value = anchor.strip() if separator else None
    # canonical contract 的 `/**` 是该直接目录本身的递归摘要记法；manifest 保留
    # 目录 context，由 EvidenceFingerprint 对目录内容递归取摘要，不展开文件清单。
    if path_text.endswith("/**"):
        path_text = path_text[:-3].rstrip("/")
    explicit_spec = (
        path_text.startswith("specs/feature-tree/")
        and path_text.endswith("/spec.md")
    )
    relative_spec = path_text == "spec.md" or path_text.endswith("/spec.md")
    policy_parts = Path(path_text).parts
    explicit_contract = (
        (
            len(policy_parts) == 3
            and policy_parts[:2] == ("quwoquan_ops", "policies")
            and policy_parts[2].endswith(".yaml")
        )
        or _is_metadata_contract_file(path_text)
        or _is_service_contract_path(path_text)
    )
    candidate_type = explicit_spec or relative_spec or explicit_contract
    if not path_text or "?" in path_text or "\\" in path_text:
        if candidate_type:
            raise ValueError(
                f"GATE_BLOCK: {_source_label(source)} 包含无效 canonical 直接引用："
                f"{reference}"
            )
        return None
    if separator and not anchor_value:
        if candidate_type:
            raise ValueError(
                f"GATE_BLOCK: {_source_label(source)} 包含空锚点 canonical 直接引用："
                f"{reference}"
            )
        return None

    # selected canonical source segment 中的裸 YAML basename 只可能指向唯一
    # quwoquan_ops/policies 文件；即使目标缺失也必须作为 candidate fail-closed。
    # 带目录的普通 YAML 仍按其原路径判断，不映射到 policies。
    if "/" not in path_text and path_text.endswith(".yaml"):
        candidate = context.REPO_ROOT / "quwoquan_ops" / "policies" / path_text
        candidate_type = True
    elif path_text.startswith(
        ("specs/", "quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")
    ):
        candidate = context.REPO_ROOT / path_text
    else:
        candidate = source.parent / path_text

    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(context.REPO_ROOT.resolve()).as_posix()
    except ValueError as error:
        if candidate_type:
            raise ValueError(
                f"GATE_BLOCK: {_source_label(source)} 的 canonical 直接引用越出仓库："
                f"{reference}"
            ) from error
        return None

    kind = _canonical_reference_kind(relative)
    if kind is None:
        if candidate_type:
            raise ValueError(
                f"GATE_BLOCK: {_source_label(source)} 的直接引用不属于 canonical "
                f"spec/contract 物理边界：{reference} -> {relative}"
            )
        return None
    if resolved.is_file():
        return relative, anchor_value, kind
    if (
        resolved.is_dir()
        and kind == "contract"
        and _is_service_contract_path(relative)
    ):
        return relative, anchor_value, kind
    raise ValueError(
        f"GATE_BLOCK: {_source_label(source)} 的 canonical 直接引用不存在："
        f"{reference} -> {relative}"
    )


def _direct_reference_variants(reference: str) -> tuple[str, ...]:
    """展开 Markdown 中显式枚举的有限路径，不扫描目录或构建 inventory。"""

    if not reference.startswith(
        ("quwoquan_service/contracts/metadata/", "quwoquan_service/services/")
    ):
        return (reference,)
    match = _BRACED_DIRECT_REFERENCE_RE.fullmatch(reference)
    if match is None:
        return (reference,)
    options = tuple(
        option.strip()
        for option in match.group("options").split(",")
        if option.strip()
    )
    if len(options) < 2:
        return (reference,)
    return tuple(
        f"{match.group('prefix')}{option}{match.group('suffix')}"
        for option in options
    )


def _direct_canonical_references(
    source: Path,
    segment: str,
    *,
    bare_policy_candidates: bool = True,
) -> set[tuple[str, str | None, str]]:
    # `spec_ref: <repo spec>#<anchor>` 是 canonical 验收绑定，不是上下文扩展入口。
    # 先用全仓唯一 spec_ref 词法入口提取精确 ref，校验它的物理边界与存在性，
    # 同时避免把 code span 中的 `spec_ref: ` marker 拼进相对路径。
    explicit_spec_refs = extract_spec_refs(segment)
    references = list(explicit_spec_refs)
    for match in _CODE_SPAN_RE.finditer(segment):
        code_span = match.group(1)
        if code_span in explicit_spec_refs or extract_spec_refs(code_span):
            continue
        marked_ref = _SPEC_REF_CODE_SPAN_RE.fullmatch(code_span)
        references.append(
            marked_ref.group("reference") if marked_ref is not None else code_span
        )
    references.extend(
        match.group("destination")
        for match in _MARKDOWN_INLINE_LINK_RE.finditer(segment)
    )
    resolved: set[tuple[str, str | None, str]] = set()
    for reference in references:
        for variant in _direct_reference_variants(reference):
            path_text = variant.partition("#")[0].strip()
            if (
                not bare_policy_candidates
                and "/" not in path_text
                and path_text.endswith(".yaml")
            ):
                continue
            item = _resolved_direct_reference(variant, source=source)
            if item is not None and reference not in explicit_spec_refs:
                resolved.add(item)
    return resolved


def _anchor_section(text: str, anchor: str) -> str:
    """Return one ID heading without absorbing the following non-ID section."""

    match = re.search(
        rf"^(?P<marks>#{{3,6}})\s+{re.escape(anchor)}\b.*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if match is None:
        return ""
    level = len(match.group("marks"))
    following = text[match.end() :]
    next_heading = re.search(rf"^#{{1,{level}}}\s+", following, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end].strip()


def _serialize_context_manifest(payload: Mapping[str, object]) -> str:
    """按 canonical JSON 精确序列化默认机器 manifest。"""

    return canonical_json_bytes(payload).decode("utf-8")


def write_output(name: str, content: str) -> Path:
    context.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = context.OUTPUT_ROOT / name
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def _relative(path: Path) -> str:
    return path.resolve().relative_to(context.REPO_ROOT.resolve()).as_posix()


def _canonical_contexts(
    resolution: TargetResolution,
    *,
    raw_target: str,
) -> list[dict[str, str | None]]:
    """返回直达 canonical 文档及锚点，不展开中间转引文本。"""

    design_owner = resolution.design_ownership
    contexts: list[dict[str, str | None]] = []

    def append(path: Path, anchor: str | None, kind: str) -> None:
        entry = declared_object(
            {"path": _relative(path), "anchor": anchor, "kind": kind},
            "feature_context_manifest",
            "context_fields",
        )
        if entry not in contexts:
            contexts.append(entry)

    requested_name = Path(raw_target.partition("#")[0]).name
    if design_owner is not None:
        append(design_owner.l2.design, design_owner.anchor, "decision")
        for anchor in design_owner.requirement_anchors:
            append(design_owner.story.spec, anchor, "requirement")
        for anchor in design_owner.acceptance_anchors:
            append(design_owner.story.spec, anchor, "acceptance")
        if not design_owner.requirement_anchors and not design_owner.acceptance_anchors:
            append(design_owner.story.spec, None, "spec")
    else:
        # 直接 spec/design 请求只读取被请求文档的直接引用；工程路径没有更精确
        # DEC 时仍加载当前 owner 的 spec/design。父链只保留在 owner_chain。
        append(resolution.node.spec, None, "spec")
        if requested_name != "spec.md" and resolution.node.design.is_file():
            append(resolution.node.design, None, "design")

    # 只读取已选 DEC/REQ/GWT 锚点中的 direct contract；Story 其他要求、父层全文
    # 与集中契约清单都不应扩大本次 feature context。
    source_segments: list[tuple[Path, str]] = []
    if design_owner is not None:
        design_text = design_owner.l2.design.read_text(encoding="utf-8")
        story_text = design_owner.story.spec.read_text(encoding="utf-8")
        selected = (
            design_owner.anchor,
            *design_owner.requirement_anchors,
            *design_owner.acceptance_anchors,
        )
        for anchor in selected:
            section = _anchor_section(design_text, anchor)
            if section:
                source_segments.append((design_owner.l2.design, section))
                continue
            section = _anchor_section(story_text, anchor)
            if section:
                source_segments.append((design_owner.story.spec, section))
    else:
        if requested_name == "spec.md":
            source_paths = (resolution.node.spec,)
        elif requested_name == "design.md":
            source_paths = (resolution.node.design,)
        else:
            source_paths = (resolution.node.spec, resolution.node.design)
        for path in source_paths:
            if path.is_file():
                source_segments.append((path, path.read_text(encoding="utf-8")))

    direct_refs: set[tuple[str, str | None, str]] = set()
    for source, segment in source_segments:
        direct_refs.update(
            _direct_canonical_references(
                source,
                segment,
                bare_policy_candidates=(
                    design_owner is not None or requested_name == "design.md"
                ),
            )
        )
    for path, anchor, kind in sorted(
        direct_refs,
        key=lambda item: (item[2], item[0], item[1] or ""),
    ):
        append(context.REPO_ROOT / path, anchor, kind)
    return contexts


def _applicable_agents(target: Path) -> list[str]:
    """按仓库根到最近子树顺序返回真实存在的 AGENTS.md。"""

    try:
        target.resolve().relative_to(context.REPO_ROOT.resolve())
    except ValueError:
        return []
    current = target if target.is_dir() else target.parent
    found: list[Path] = []
    while True:
        candidate = current / "AGENTS.md"
        if candidate.is_file():
            found.append(candidate)
        if current.resolve() == context.REPO_ROOT.resolve():
            break
        if not current.resolve().is_relative_to(context.REPO_ROOT.resolve()):
            break
        current = current.parent
    return [_relative(path) for path in reversed(found)]


def _context_manifest(
    raw_target: str,
    resolution: TargetResolution,
    nodes: list[Node],
    *,
    fingerprint_receipt: dict[str, object] | None = None,
) -> dict[str, object]:
    by_dir = {node.directory.resolve(): node for node in nodes}
    chain = parent_chain(resolution.node, by_dir)
    open_items = [
        declared_object(
            {
                "path": str(item["node"]),
                "id": str(item["id"]),
                "title": str(item["title"]),
                "release_impact": str(item["releaseImpact"]),
            },
            "feature_context_manifest",
            "open_item_fields",
        )
        for item in open_item_details(resolution.node)
    ]
    payload = {
        "schema_version": contract_schema_version("feature_context_manifest"),
        "target": _relative(resolution.target),
        "resolved_owner": resolution.node.rel,
        "owner_chain": [
            declared_object(
                {"level": item.level, "node_id": item.node_id, "path": item.rel},
                "feature_context_manifest",
                "owner_chain_fields",
            )
            for item in chain
        ],
        "canonical_contexts": _canonical_contexts(resolution, raw_target=raw_target),
        "applicable_agents": _applicable_agents(resolution.target),
        "open_items": open_items,
    }
    receipt = (
        fingerprint_receipt
        if fingerprint_receipt is not None
        else build_feature_context_fingerprint(payload, repo_root=context.REPO_ROOT)
    )
    payload["evidence_fingerprint"] = embedded_fingerprint_binding(receipt)
    validate_feature_context_manifest(payload)
    return payload


def _command_expanded_context(
    args: argparse.Namespace,
    nodes: list[Node],
    node: Node,
) -> int:
    by_dir = {item.directory.resolve(): item for item in nodes}
    chain = parent_chain(node, by_dir)
    blocks = [
        "# Feature Context",
        "",
        f"- TARGET：`{args.target}`",
        f"- 归属节点：`{node.rel}`",
        "",
    ]
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


def command_context(args: argparse.Namespace) -> int:
    nodes = discover_nodes()
    try:
        resolution = resolve_target_details(args.target, nodes)
        output_format = getattr(args, "format", "manifest")
        if output_format == "expanded":
            return _command_expanded_context(args, nodes, resolution.node)
        manifest = _context_manifest(args.target, resolution, nodes)
        content = canonical_json_bytes(manifest)
        size = len(content)
        receipt: Mapping[str, object] | None = None
        if size > MANIFEST_MAX_BYTES:
            receipt = manifest["evidence_fingerprint"]["receipt"]
            receipt_content = canonical_json_bytes(receipt)
            receipt_ref = _relative(
                _content_addressed_path(
                    receipt_content, subdirectory="receipts"
                )
            )
            manifest["evidence_fingerprint"] = referenced_fingerprint_binding(
                receipt, receipt_ref=receipt_ref
            )
            content = canonical_json_bytes(manifest)
            size = len(content)
            if size > MANIFEST_MAX_BYTES:
                raise ValueError(
                    "GATE_BLOCK: feature context manifest 超出 8KiB 预算："
                    f"{size} bytes"
                )
        if receipt is not None:
            _write_content_addressed_json(receipt, subdirectory="receipts")
        output = _write_content_addressed_bytes(content)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(output.relative_to(context.REPO_ROOT))
    return 0



def command_candidate_evidence(args: argparse.Namespace) -> int:
    try:
        payload = build_candidate_evidence(
            args.owner_identity, list(args.changed_path), repo_root=context.REPO_ROOT
        )
        content = canonical_json_bytes(payload)
        if len(content) > int(contract_section("candidate_evidence_manifest")["max_bytes"]):
            raise CandidateEvidenceError(
                "CANDIDATE.STALE", f"candidate evidence 超出预算：{len(content)} bytes"
            )
        output = _write_content_addressed_bytes(
            content, subdirectory="candidates/by-fingerprint"
        )
    except CandidateEvidenceError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError) as error:
        print(f"CANDIDATE.STALE: {error}", file=sys.stderr)
        return 2
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
