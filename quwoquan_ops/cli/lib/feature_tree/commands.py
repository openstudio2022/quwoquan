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
from .parsing import block_open_items, open_item_details, title
from .patterns import PATH_RE, SPEC_REF_CODE_SPAN_RE, VALID_LEVELS
from ..evidence_fingerprint import canonical_json_bytes
from ..candidate_evidence import CandidateEvidenceError, build_candidate_evidence
from ..feature_context_fingerprint import (
    build_feature_context_fingerprint,
    embedded_fingerprint_binding,
    referenced_fingerprint_binding,
    feature_context_closure,
    feature_context_closure_identity,
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

    # 裸 YAML basename 只在 quwoquan_ops/policies/<name> 已存在时才是
    # canonical policy 引用；缺失当作散文忽略。带目录的 YAML 仍按原路径判断。
    if "/" not in path_text and path_text.endswith(".yaml"):
        candidate = context.repository_root() / "quwoquan_ops" / "policies" / path_text
        if not candidate.is_file():
            return None
        candidate_type = True
    elif path_text.startswith(
        ("specs/", "quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")
    ):
        candidate = context.repository_root() / path_text
    else:
        candidate = source.parent / path_text

    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(context.repository_root().resolve()).as_posix()
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
        marked_ref = SPEC_REF_CODE_SPAN_RE.fullmatch(code_span)
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
    context.output_root().mkdir(parents=True, exist_ok=True)
    path = context.output_root() / name
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def _relative(path: Path) -> str:
    return path.resolve().relative_to(context.repository_root().resolve()).as_posix()




def _direct_feature_resolution(raw_target: str, nodes: list[Node]) -> tuple[Path, list[Node]]:
    raw_path = raw_target.partition("#")[0]
    target = Path(raw_path)
    if not target.is_absolute():
        target = context.repository_root() / target
    try:
        target.resolve(strict=False).relative_to(context.repository_root().resolve())
    except ValueError as exc:
        raise ValueError(f"GATE_BLOCK: {raw_target} 越出仓库") from exc
    if target.is_dir() and (target / "spec.md").is_file():
        target = target / "spec.md"
    spec = target if target.name == "spec.md" else target.parent / "spec.md"
    direct = node_for_spec(spec, nodes)
    if direct is None:
        return target, []
    by_dir = {node.directory.resolve(): node for node in nodes}
    return target, parent_chain(direct, by_dir)

def _canonical_contexts(feature_chain: list[Node], *, target: Path) -> list[dict[str, str | None]]:
    contexts: list[dict[str, str | None]] = []
    requested = target.name
    selected = feature_chain[-1:]
    for node in selected:
        sources = [node.spec]
        if requested != "spec.md" and node.design.is_file(): sources.append(node.design)
        for source in sources:
            contexts.append(declared_object({"path": _relative(source), "anchor": None, "kind": "spec" if source.name == "spec.md" else "design"}, "feature_context_manifest", "context_fields"))
    return sorted(contexts, key=lambda item: (str(item["path"]).encode(), str(item["anchor"] or "").encode(), str(item["kind"]).encode()))

def _applicable_agents(target: Path) -> list[str]:
    """按仓库根到最近子树顺序返回真实存在的 AGENTS.md。"""

    try:
        target.resolve().relative_to(context.repository_root().resolve())
    except ValueError:
        return []
    current = target if target.is_dir() else target.parent
    found: list[Path] = []
    while True:
        candidate = current / "AGENTS.md"
        if candidate.is_file():
            found.append(candidate)
        if current.resolve() == context.repository_root().resolve():
            break
        if not current.resolve().is_relative_to(context.repository_root().resolve()):
            break
        current = current.parent
    return [_relative(path) for path in reversed(found)]


def _context_manifest(raw_target: str, nodes: list[Node], *, fingerprint_receipt: dict[str, object] | None = None) -> dict[str, object]:
    target, chain = _direct_feature_resolution(raw_target, nodes)
    open_items = [declared_object({"path": str(item["node"]), "id": str(item["id"]), "title": str(item["title"]), "release_impact": str(item["releaseImpact"])}, "feature_context_manifest", "open_item_fields") for node in chain[-1:] for item in open_item_details(node)]
    contexts = _canonical_contexts(chain, target=target)
    payload = {"schema_version": contract_schema_version("feature_context_manifest"), "target": _relative(target), "context_status": "context_resolved" if chain else "context_unresolved", "feature_chain": [declared_object({"level": item.level, "node_id": item.node_id, "path": item.rel}, "feature_context_manifest", "feature_chain_fields") for item in chain], "canonical_contexts": contexts, "applicable_agents": _applicable_agents(target), "open_items": open_items, "dependency_evidence": sorted({path for node in chain[-1:] for source in (node.spec, node.design) if source.is_file() for path, _, _ in _direct_canonical_references(source, source.read_text(encoding="utf-8"), bare_policy_candidates=False)}, key=lambda item: item.encode())}
    receipt = fingerprint_receipt or build_feature_context_fingerprint(payload, repo_root=context.repository_root())
    payload["evidence_fingerprint"] = embedded_fingerprint_binding(receipt); validate_feature_context_manifest(payload); return payload

def _command_expanded_context(args: argparse.Namespace, nodes: list[Node], chain: list[Node]) -> int:
    blocks = ["# Feature Context", "", f"- TARGET：`{args.target}`", f"- 上下文状态：`{'context_resolved' if chain else 'context_unresolved'}`", ""]
    for item in chain:
        blocks.extend([f"## {VALID_LEVELS[item.level]} · {item.node_id}", "", item.spec.read_text(encoding="utf-8").strip(), ""]);
        if item.design.is_file(): blocks.extend([f"### 有效设计 · {item.node_id}", "", item.design.read_text(encoding="utf-8").strip(), ""])
    output = write_output("context.md", "\n".join(blocks)); print(output.relative_to(context.repository_root())); return 0

def command_context(args: argparse.Namespace) -> int:
    nodes = discover_nodes()
    try:
        target, chain = _direct_feature_resolution(args.target, nodes)
        output_format = getattr(args, "format", "manifest")
        if output_format == "expanded":
            return _command_expanded_context(args, nodes, chain)
        manifest = _context_manifest(args.target, nodes)
        content = canonical_json_bytes(manifest)
        size = len(content)
        receipt: Mapping[str, object] | None = None
        closure: dict[str, object] | None = None
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
            closure = feature_context_closure(manifest)
            closure_raw = canonical_json_bytes(closure)
            if len(closure_raw) > int(contract_section("feature_context_closure")["max_bytes"]):
                raise ValueError("GATE_BLOCK: feature context closure 超出资源边界")
            manifest["closure_identity"] = feature_context_closure_identity(closure)
            for field in ("owner_chain", "canonical_contexts", "applicable_agents", "open_items"):
                manifest[field] = []
            validate_feature_context_manifest(manifest)
            content = canonical_json_bytes(manifest)
            size = len(content)
            if size > MANIFEST_MAX_BYTES:
                raise ValueError(
                    "GATE_BLOCK: feature context manifest 超出 8KiB 预算："
                    f"{size} bytes"
                )
        if receipt is not None:
            _write_content_addressed_json(receipt, subdirectory="receipts")
        if closure is not None:
            _write_content_addressed_json(closure, subdirectory="feature-context-closure")
        output = _write_content_addressed_bytes(content)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(output.relative_to(context.repository_root()))
    return 0



def command_candidate_evidence(args: argparse.Namespace) -> int:
    try:
        payload = build_candidate_evidence(list(args.changed_path), repo_root=context.repository_root())
        content = canonical_json_bytes(payload)
        if len(content) > int(contract_section("candidate_evidence_manifest")["max_bytes"]):
            raise CandidateEvidenceError(
                "CANDIDATE.STALE", f"candidate evidence 超出预算：{len(content)} bytes"
            )
        output = _write_content_addressed_bytes(
            content, subdirectory="candidates/by-fingerprint"
        )
        # 发布后完整读回；缺依赖/当前字节漂移时不返回可消费ref。
        from ..candidate_evidence import validate_candidate_ref
        validate_candidate_ref(
            output.relative_to(context.repository_root()).as_posix(), repo_root=context.repository_root(),
            expected_changed_paths=list(args.changed_path),
        )
    except CandidateEvidenceError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError) as error:
        print(f"CANDIDATE.STALE: {error}", file=sys.stderr)
        return 2
    print(output.relative_to(context.repository_root()))
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
        l1_prefix = l1.directory.relative_to(context.repository_root()).as_posix() + "/"
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
            l2_prefix = l2.directory.relative_to(context.repository_root()).as_posix() + "/"
            l2_subtree = [item for item in open_items if str(item["node"]).startswith(l2_prefix)]
            lines.append(
                f"- [{title(l2.spec)}]({os.path.relpath(l2.spec, context.output_root()).replace(os.sep, '/')})："
                f"{story_count} Story；本层 {l2_open} OPEN；子树 {len(l2_subtree)} OPEN"
            )
        lines.append("")
    lines.extend(["## 准出阻断 OPEN", ""])
    lines.extend(
        f"- `{item['priority']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(context.repository_root() / str(item['node']), context.output_root()).replace(os.sep, '/')}) "
        f"· 完成判定：{item['completion']}"
        for item in block_items
    )
    if not block_items:
        lines.append("- 无")
    lines.append("")
    lines.extend(["## 全部开放事项", ""])
    lines.extend(
        f"- `{item['priority']}/{item['releaseImpact']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(context.repository_root() / str(item['node']), context.output_root()).replace(os.sep, '/')}) "
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
    print(f"{markdown_path.relative_to(context.repository_root())}\n{json_path.relative_to(context.repository_root())}")
    return 0


def command_change_report(_: argparse.Namespace) -> int:
    nodes = discover_nodes()
    by_dir = {node.directory.resolve(): node for node in nodes}
    changed = gitio.git_changed_paths()
    impacted: dict[str, list[str]] = {}
    impacted_nodes: set[Node] = set()
    for rel in changed:
        path = context.repository_root() / rel
        node = None
        if rel.startswith("specs/feature-tree/"):
            current = path if path.name == "spec.md" else path.parent / "spec.md"
            while current.parent.resolve().is_relative_to(context.TREE_ROOT.resolve()):
                node = node_for_spec(current, nodes)
                if node:
                    break
                current = current.parent.parent / "spec.md"
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
        path = context.repository_root() / rel
        if not path.exists():
            metadata_breaking.append(f"{rel}: 删除 canonical metadata 文件")
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", rel],
            cwd=context.repository_root(),
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

    from quwoquan_ops.ci.impact_planner_core import classify_impacts

    impact_plan = classify_impacts(changed)
    required_layers = {
        name for name, required in impact_plan["local_scopes"].items() if required
    }
    required_gates = {"canonical ImpactPlan required_ids"}


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
    output = write_output("change-report.md", "\n".join(lines))
    json_output = write_output(
        "change-report.json",
        json.dumps(
            {
                "changed": changed,
                "impacted": impacted,
                "semantic_anchor_changes": semantic_changes,
                "metadata": {"changed": metadata_changes, "breaking_signals": metadata_breaking},
                "impact_plan": impact_plan,
                "required_test_layers": sorted(required_layers),
                "required_gates": sorted(required_gates),
                "release_blockers": sorted(release_blockers),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"{output.relative_to(context.repository_root())}\n{json_output.relative_to(context.repository_root())}")
    if release_blockers:
        print(
            "RELEASE_GATES_BLOCKED: 当前变更关联的正式发布准出仍被 OPEN 阻断；"
            "该事实已写入 change report，但不阻断非提升性修复的结构门禁。"
        )
    # `verify-feature-tree --changes` 校验的是目录归属和可追溯性。block OPEN
    # 仍是正式发布门禁，但不能令其本身的非提升性修复无法提交；stackctl release
    # profile 继续消费 change report 中的 release blockers 并如实阻断发布。
    return 0
