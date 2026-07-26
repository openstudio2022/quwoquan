#!/usr/bin/env python3
"""从目录与 Markdown 直接读取、校验和展示特性树。

本工具刻意不支持 tree/index/registry/acceptance/changelog 兼容读取。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


REPO_ROOT = Path(__file__).resolve().parents[2]
TREE_ROOT = REPO_ROOT / "specs" / "feature-tree"
OUTPUT_ROOT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "feature-tree"
ID_RE = re.compile(r"^#{3,6}\s+(REQ|UAT|DOM|SIT|GWT|DEC|OPEN)-(\d{3,})\b", re.MULTILINE)
ACCEPTANCE_ID_RE = re.compile(r"^#{3,6}\s+(UAT|DOM|SIT|GWT)-(\d{3,})\b", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
PATH_RE = re.compile(
    r"`((?:quwoquan_app|quwoquan_service|quwoquan_data|quwoquan_ops|\.github)(?:/[^`\s；，]+)*)`"
)
ENGINEERING_CLAIM_RE = re.compile(
    r"^-\s+(App|Contracts|Metadata|Service|Data|Ops|CI)(?:（[^）]*）)?："
)
SPEC_REF_RE = re.compile(
    r"specs/feature-tree/(?:[A-Za-z0-9_.-]+/)*spec\.md#[A-Za-z0-9_.%\-\u4e00-\u9fff]+"
)
REPO_SPEC_PATH_RE = re.compile(r"`(specs/[A-Za-z0-9_./-]+\.md)(?:#[^`]*)?`")
FORBIDDEN_GLOBALS = (
    "tree_index.yaml",
    "journey_scenario_registry.yaml",
)
FORBIDDEN_NODE_NAMES = {
    "README.md",
    "acceptance.yaml",
    "tree.yaml",
    "plan.md",
    "plan.yaml",
    "tasks.md",
    "tasks.yaml",
}
FORBIDDEN_CENTRAL_PATHS = (
    "specs/changelog",
    "specs/gates",
    "specs/inventories",
    "specs/launch-plan",
    "specs/product",
    "docs/outstanding_risks_backlog.md",
)
EVIDENCE_ROOTS = (
    "quwoquan_app/test",
    "quwoquan_app/scripts",
    "quwoquan_service",
    "quwoquan_data/tests",
    "quwoquan_ops/gate",
    "quwoquan_ops/tests",
)
TEST_SUFFIXES = {".dart", ".go", ".py", ".sh", ".yaml", ".yml"}
VALID_LEVELS = {0: "AppRoot Spec", 1: "L1 Domain Service", 2: "L2 Business Capability", 3: "L3 Story"}


@dataclass(frozen=True)
class Node:
    level: int
    node_id: str
    directory: Path

    @property
    def spec(self) -> Path:
        return self.directory / "spec.md"

    @property
    def design(self) -> Path:
        return self.directory / "design.md"

    @property
    def rel(self) -> str:
        return self.spec.relative_to(REPO_ROOT).as_posix()


def _visible_dirs(path: Path) -> list[Path]:
    return sorted(
        (item for item in path.iterdir() if item.is_dir() and not item.name.startswith(".")),
        key=lambda item: item.name,
    )


def discover_nodes() -> list[Node]:
    nodes = [Node(0, "app-root", TREE_ROOT)]
    for l1 in _visible_dirs(TREE_ROOT):
        if l1.name == "templates":
            continue
        if not (l1 / "spec.md").is_file():
            continue
        nodes.append(Node(1, l1.name, l1))
        for l2 in _visible_dirs(l1):
            if not (l2 / "spec.md").is_file():
                continue
            nodes.append(Node(2, l2.name, l2))
            for l3 in _visible_dirs(l2):
                if (l3 / "spec.md").is_file():
                    nodes.append(Node(3, l3.name, l3))
    return nodes


def node_for_spec(path: Path, nodes: Iterable[Node]) -> Node | None:
    resolved = path.resolve()
    for node in nodes:
        if node.spec.resolve() == resolved or node.directory.resolve() == resolved:
            return node
    return None


def parent_chain(node: Node, by_dir: dict[Path, Node]) -> list[Node]:
    chain: list[Node] = []
    current: Node | None = node
    while current is not None:
        chain.append(current)
        if current.level == 0:
            break
        current = by_dir.get(current.directory.parent)
    return list(reversed(chain))


def markdown_anchor(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading).strip().lower()
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"[^\w\-\u4e00-\u9fff ]", "", text)
    return re.sub(r"\s+", "-", text)


def headings(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    result = {markdown_anchor(match.group(2)) for match in HEADING_RE.finditer(text)}
    result.update(re.findall(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', text, re.IGNORECASE))
    return result


def title(path: Path) -> str:
    if not path.is_file():
        return path.parent.name
    match = HEADING_RE.search(path.read_text(encoding="utf-8"))
    return match.group(2).strip() if match else path.parent.name


def ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [f"{kind}-{number}" for kind, number in ID_RE.findall(path.read_text(encoding="utf-8"))]


def acceptance_ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [f"{kind}-{number}" for kind, number in ACCEPTANCE_ID_RE.findall(path.read_text(encoding="utf-8"))]


def acceptance_refs_in_open(path: Path) -> set[str]:
    """返回同一 spec 的 OPEN 完成判定所引用的尚未闭合验收。"""

    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    refs: set[str] = set()
    for match in re.finditer(r"^###\s+OPEN-\d{3,}\b[\s\S]*?(?=^###\s+OPEN-\d{3,}\b|\Z)", text, re.MULTILINE):
        block = match.group(0)
        done = re.search(r"^- 完成判定：(.+)$", block, re.MULTILINE)
        if done:
            refs.update(re.findall(r"\b(?:UAT|DOM|SIT|GWT)-\d{3,}\b", done.group(1)))
    return refs


def invalid_acceptance_refs_in_open(path: Path) -> set[str]:
    """返回 OPEN 完成判定中不存在于同一 spec 的验收锚点。"""

    return acceptance_refs_in_open(path) - set(acceptance_ids(path))


def open_item_details(node: Node) -> list[dict[str, str | int]]:
    """从节点 spec 解析可检索的 OPEN 当前事实，不建立独立台账。"""

    if not node.spec.is_file():
        return []
    text = node.spec.read_text(encoding="utf-8")
    details: list[dict[str, str | int]] = []
    matches = list(re.finditer(r"^###\s+(OPEN-\d{3,})\s+(.+)$", text, re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]

        def value(label: str) -> str:
            field_match = re.search(rf"^- {re.escape(label)}：(.+?)\s*$", body, re.MULTILINE)
            raw = field_match.group(1).strip() if field_match else ""
            if len(raw) >= 2 and raw.startswith("`") and raw.endswith("`"):
                return raw[1:-1]
            return raw

        details.append(
            {
                "node": node.rel,
                "level": node.level,
                "id": match.group(1),
                "title": match.group(2).strip(),
                "type": value("类型"),
                "priority": value("优先级"),
                "releaseImpact": value("准出影响"),
                "impactOrValue": value("影响或价值"),
                "completion": value("完成判定"),
                "dependency": value("依赖"),
            }
        )
    return details


def iter_test_files() -> Iterator[Path]:
    for raw_root in EVIDENCE_ROOTS:
        root = REPO_ROOT / raw_root
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEST_SUFFIXES:
                continue
            if raw_root == "quwoquan_service" and "test" not in path.name.lower() and "tests" not in path.parts:
                continue
            yield path


def test_spec_refs() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for path in iter_test_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = set(SPEC_REF_RE.findall(content))
        if found:
            refs[path.relative_to(REPO_ROOT).as_posix()] = found
    return refs


def canonical_spec_ref(path: Path, anchor_id: str) -> str:
    return f"{path.relative_to(REPO_ROOT).as_posix()}#{anchor_id.lower()}"


def anchor_sections(text: str) -> dict[str, str]:
    """提取可追踪 ID 对应的小节，用于 Git 增量语义比较。"""

    matches = list(ID_RE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = f"{match.group(1)}-{match.group(2)}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[key] = text[match.start() : end].strip()
    return result


def section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+(?:\d+\.\s+)?{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end].strip()


def engineering_claims(node: Node) -> list[tuple[str, str]]:
    if node.level != 1 or not node.spec.is_file():
        return []
    body = section(node.spec.read_text(encoding="utf-8"), "工程归属")
    claims: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = ENGINEERING_CLAIM_RE.match(line.strip())
        if "协作引用" in line or match is None:
            continue
        claims.extend(
            (match.group(1), root.rstrip("/"))
            for root in PATH_RE.findall(line)
        )
    return sorted(set(claims))


def engineering_roots(node: Node) -> list[str]:
    return sorted({root for _, root in engineering_claims(node)})


def domain_service_roots() -> list[Path]:
    """仅从服务自身的 contracts/domain.yaml 发现领域服务。"""

    services_root = REPO_ROOT / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        domain_file.parent.parent
        for domain_file in services_root.glob("*/contracts/domain.yaml")
        if domain_file.is_file()
    )


def undeclared_service_roots() -> list[Path]:
    services_root = REPO_ROOT / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        service
        for service in services_root.iterdir()
        if service.is_dir() and not (service / "contracts" / "domain.yaml").is_file()
    )


def validate_domain_service_ownership(nodes: Iterable[Node]) -> list[str]:
    """验证领域服务根与共享 metadata 的直接 L1 归属，无服务名册。"""

    errors: list[str] = []
    l1_nodes = [node for node in nodes if node.level == 1]
    claims = {node: engineering_claims(node) for node in l1_nodes}
    for service in undeclared_service_roots():
        errors.append(
            f"{service.relative_to(REPO_ROOT)}: 服务根必须声明 contracts/domain.yaml"
        )
    for service in domain_service_roots():
        root = service.relative_to(REPO_ROOT).as_posix()
        direct_owners = sorted(
            node.node_id
            for node, node_claims in claims.items()
            if ("Service", root) in node_claims
        )
        if len(direct_owners) != 1:
            errors.append(
                f"{root}: 必须由唯一非宽泛 fallback 的 L1 Service 根直接认领；"
                f"当前={direct_owners or '无'}"
            )
            continue
        resolved = owners_for_path(service, l1_nodes)
        if [node.node_id for node in resolved] != direct_owners:
            errors.append(
                f"{root}: 直接 L1 owner {direct_owners[0]} 与路径解析结果 "
                f"{[node.node_id for node in resolved]} 不一致"
            )

    shared_metadata = (
        REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared"
    )
    if shared_metadata.is_dir():
        shared_root = shared_metadata.relative_to(REPO_ROOT).as_posix()
        shared_owners = sorted(
            node.node_id
            for node, node_claims in claims.items()
            if ("Metadata", shared_root) in node_claims
        )
        if shared_owners != ["runtime"]:
            errors.append(
                f"{shared_root}: 必须由 runtime L1 唯一直接拥有；"
                f"当前={shared_owners or '无'}"
            )
        elif [
            node.node_id for node in owners_for_path(shared_metadata, l1_nodes)
        ] != ["runtime"]:
            errors.append(f"{shared_root}: runtime 直接归属未成为路径解析 owner")
    return errors


def owners_for_path(target: Path, nodes: Iterable[Node]) -> list[Node]:
    try:
        rel = target.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return []
    matches: list[tuple[int, Node]] = []
    for node in nodes:
        for root in engineering_roots(node):
            root = root.rstrip("/")
            if rel == root or rel.startswith(root + "/"):
                matches.append((len(root), node))
    if not matches:
        return []
    longest = max(length for length, _ in matches)
    return sorted({node for length, node in matches if length == longest}, key=lambda item: item.node_id)


def resolve_target(raw: str, nodes: list[Node]) -> Node:
    target = Path(raw)
    if not target.is_absolute():
        target = REPO_ROOT / target
    if target.is_dir() and (target / "spec.md").is_file():
        target = target / "spec.md"
    direct = node_for_spec(target, nodes)
    if direct:
        return direct
    owners = owners_for_path(target, nodes)
    if len(owners) == 1:
        return owners[0]
    if not owners:
        raise ValueError(f"GATE_BLOCK: {raw} 未被任何 L1 工程归属认领")
    raise ValueError(f"GATE_BLOCK: {raw} 被多个 L1 同优先级认领：{', '.join(item.node_id for item in owners)}")


def write_output(name: str, content: str) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_ROOT / name
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

    chain_specs = {item.spec.relative_to(REPO_ROOT).as_posix() for item in chain}
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

    changed = git_changed_paths()
    chain_prefixes = [item.directory.relative_to(REPO_ROOT).as_posix().rstrip("/") + "/" for item in chain]
    related_changes: list[str] = []
    for rel in changed:
        if any(rel.startswith(prefix) for prefix in chain_prefixes):
            related_changes.append(rel)
            continue
        owners = owners_for_path(REPO_ROOT / rel, nodes)
        if len(owners) == 1 and owners[0] in chain:
            related_changes.append(rel)
    blocks.extend(["## 当前 Git 增量", "", *([f"- `{rel}`" for rel in related_changes] or ["- 无"]), ""])
    output = write_output("context.md", "\n".join(blocks))
    print(output.relative_to(REPO_ROOT))
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
        l1_prefix = l1.directory.relative_to(REPO_ROOT).as_posix() + "/"
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
            l2_prefix = l2.directory.relative_to(REPO_ROOT).as_posix() + "/"
            l2_subtree = [item for item in open_items if str(item["node"]).startswith(l2_prefix)]
            lines.append(
                f"- [{title(l2.spec)}]({os.path.relpath(l2.spec, OUTPUT_ROOT).replace(os.sep, '/')})："
                f"{story_count} Story；本层 {l2_open} OPEN；子树 {len(l2_subtree)} OPEN"
            )
        lines.append("")
    lines.extend(["## 准出阻断 OPEN", ""])
    lines.extend(
        f"- `{item['priority']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(REPO_ROOT / str(item['node']), OUTPUT_ROOT).replace(os.sep, '/')}) "
        f"· 完成判定：{item['completion']}"
        for item in block_items
    )
    if not block_items:
        lines.append("- 无")
    lines.append("")
    lines.extend(["## 全部开放事项", ""])
    lines.extend(
        f"- `{item['priority']}/{item['releaseImpact']}/{item['type']}` `{item['id']}` "
        f"[{item['title']}]({os.path.relpath(REPO_ROOT / str(item['node']), OUTPUT_ROOT).replace(os.sep, '/')}) "
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
    print(f"{markdown_path.relative_to(REPO_ROOT)}\n{json_path.relative_to(REPO_ROOT)}")
    return 0


def git_changed_paths() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    parts = result.stdout.decode("utf-8", errors="replace").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(parts):
        item = parts[index]
        if not item:
            break
        status, path = item[:2], item[3:]
        if status[0] in "RC" or status[1] in "RC":
            index += 1
            path = parts[index] if index < len(parts) else path
        paths.append(path)
        index += 1
    return sorted(set(paths))


def git_head_text(rel: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def semantic_anchor_changes(rel: str) -> dict[str, list[str]]:
    path = REPO_ROOT / rel
    before = anchor_sections(git_head_text(rel))
    after = anchor_sections(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        "added": sorted(set(after) - set(before)),
        "modified": sorted(key for key in set(before) & set(after) if before[key] != after[key]),
        "deleted": sorted(set(before) - set(after)),
    }


def block_open_items(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    result: list[str] = []
    for match in re.finditer(r"^###\s+(OPEN-\d{3,})\s+(.+)$", text, re.MULTILINE):
        tail = text[match.end() :]
        next_open = re.search(r"^###\s+OPEN-\d{3,}\b", tail, re.MULTILINE)
        block = tail[: next_open.start()] if next_open else tail
        if re.search(r"^- 准出影响：`?block`?\s*$", block, re.MULTILINE):
            result.append(f"{match.group(1)} {match.group(2).strip()}")
    return result


def command_change_report(_: argparse.Namespace) -> int:
    nodes = discover_nodes()
    by_dir = {node.directory.resolve(): node for node in nodes}
    changed = git_changed_paths()
    impacted: dict[str, list[str]] = {}
    impacted_nodes: set[Node] = set()
    unowned: list[str] = []
    for rel in changed:
        path = REPO_ROOT / rel
        node = None
        if rel.startswith("specs/feature-tree/"):
            current = path if path.name == "spec.md" else path.parent / "spec.md"
            while current.parent.resolve().is_relative_to(TREE_ROOT.resolve()):
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
        path = REPO_ROOT / rel
        if not path.exists():
            metadata_breaking.append(f"{rel}: 删除 canonical metadata 文件")
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", rel],
            cwd=REPO_ROOT,
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
    print(f"{output.relative_to(REPO_ROOT)}\n{json_output.relative_to(REPO_ROOT)}")
    if release_blockers:
        print(
            "RELEASE_GATES_BLOCKED: 当前变更关联的正式发布准出仍被 OPEN 阻断；"
            "该事实已写入 change report，但不阻断非提升性修复的结构门禁。"
        )
    # `verify-feature-tree --changes` 校验的是目录归属和可追溯性。block OPEN
    # 仍是正式发布门禁，但不能令其本身的非提升性修复无法提交；stackctl release
    # profile 继续消费 change report 中的 release blockers 并如实阻断发布。
    return 2 if unowned else 0


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
            errors.append(f"{path.relative_to(REPO_ROOT)}: 链接目标不存在 `{raw}`")
            continue
        if anchor and target.is_file() and anchor not in headings(target):
            errors.append(f"{path.relative_to(REPO_ROOT)}: 锚点不存在 `{raw}`")
    return errors


def validate_repo_spec_paths(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for raw in REPO_SPEC_PATH_RE.findall(text):
        if not (REPO_ROOT / raw).is_file():
            errors.append(f"{path.relative_to(REPO_ROOT)}: 反引号规格路径不存在 `{raw}`")
    return errors


def validate_journey_bidirection(nodes: list[Node]) -> list[str]:
    errors: list[str] = []
    root_text = (TREE_ROOT / "spec.md").read_text(encoding="utf-8")
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
    root = REPO_ROOT / "quwoquan_ops" / "policies" / "gates"
    if not root.exists():
        return errors
    required = {"owner", "reason", "expires_when"}
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        values: dict[str, object] = {}
        if path.suffix == ".json":
            try:
                values = json.loads(path.read_text(encoding="utf-8")).get("_governance", {})
            except (json.JSONDecodeError, AttributeError):
                errors.append(f"{path.relative_to(REPO_ROOT)}: policy JSON 无法解析")
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
            errors.append(f"{path.relative_to(REPO_ROOT)}: policy governance 缺少 {', '.join(missing)}")
    return errors


def command_verify(args: argparse.Namespace) -> int:
    errors: list[str] = []
    nodes = discover_nodes()
    for required in (TREE_ROOT / "README.md", TREE_ROOT / "spec.md", TREE_ROOT / "design.md"):
        if not required.is_file():
            errors.append(f"缺少 `{required.relative_to(REPO_ROOT)}`")
    for name in FORBIDDEN_GLOBALS:
        if (TREE_ROOT / name).exists():
            errors.append(f"禁止全局注册表回潮：`specs/feature-tree/{name}`")
    for path in (REPO_ROOT / "specs" / "l1_index.yaml", REPO_ROOT / "specs" / "engineering_directory_manifest.yaml"):
        if path.exists():
            errors.append(f"禁止全局注册表回潮：`{path.relative_to(REPO_ROOT)}`")
    for raw in FORBIDDEN_CENTRAL_PATHS:
        if (REPO_ROOT / raw).exists():
            errors.append(f"禁止中央注册/台账/历史目录回潮：`{raw}`")

    node_dirs = {node.directory.resolve() for node in nodes}
    for node in nodes:
        if not node.spec.is_file():
            errors.append(f"{node.directory.relative_to(REPO_ROOT)}: 缺少 spec.md")
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
            errors.append(f"{node.directory.relative_to(REPO_ROOT)}: AppRoot/L1 必须有 design.md")
        if node.level == 3 and node.design.exists():
            errors.append(f"{node.directory.relative_to(REPO_ROOT)}: L3 禁止 design.md")
        if node.level == 2:
            spec_text = node.spec.read_text(encoding="utf-8")
            if node.design.is_file() and "设计触发原因" not in node.design.read_text(encoding="utf-8"):
                errors.append(f"{node.design.relative_to(REPO_ROOT)}: 缺少设计触发原因")
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
                errors.append(f"{item.relative_to(REPO_ROOT)}: 节点禁止文件")
            if node.level == 3 and item.is_dir():
                errors.append(f"{item.relative_to(REPO_ROOT)}: L3 不得嵌套目录")
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
                errors.append(f"{node.design.relative_to(REPO_ROOT)}: ID 重复：{', '.join(design_duplicates)}")
            errors.extend(validate_links(node.design))
            errors.extend(validate_repo_spec_paths(node.design))

    for path in TREE_ROOT.rglob("*"):
        if path.is_file() and path.name not in {"README.md", "spec.md", "design.md"}:
            errors.append(f"{path.relative_to(REPO_ROOT)}: 特性树内存在非规格/设计文件")
        if path.is_dir() and path != TREE_ROOT and path.resolve() not in node_dirs:
            errors.append(f"{path.relative_to(REPO_ROOT)}: 目录不是可识别节点")

    claims: dict[str, list[str]] = {}
    for node in (item for item in nodes if item.level == 1):
        roots = engineering_roots(node)
        if not roots:
            errors.append(f"{node.rel}: 缺少可解析的工程归属路径")
        for root in roots:
            if not (REPO_ROOT / root).exists():
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
    for test, refs in refs_by_test.items():
        for ref in refs:
            target_text, _, anchor = ref.partition("#")
            target = REPO_ROOT / target_text
            if not target.is_file() or anchor not in headings(target):
                errors.append(f"{test}: 无效 spec_ref `{ref}`")
            else:
                referenced.add(ref)
    for node in nodes:
        pending = acceptance_refs_in_open(node.spec)
        for acceptance_id in acceptance_ids(node.spec):
            ref = canonical_spec_ref(node.spec, acceptance_id)
            if ref not in referenced and acceptance_id not in pending:
                errors.append(f"{node.rel}#{acceptance_id.lower()}: 已支持验收缺少真实测试/可执行门 spec_ref")

    if args.changes:
        report_args = argparse.Namespace()
        if command_change_report(report_args) != 0:
            errors.append("当前 Git diff 存在未归属工程变更或命中 block OPEN；见 feature-tree/change-report.md")
    if errors:
        print(f"GATE_BLOCK: feature-tree 发现 {len(errors)} 个问题", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    counts = {level: sum(node.level == level for node in nodes) for level in range(4)}
    print(f"OK: directory-native feature tree verified (AppRoot={counts[0]}, L1={counts[1]}, L2={counts[2]}, L3={counts[3]})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    context_parser = subparsers.add_parser("context", help="生成目标最小完整上下文")
    context_parser.add_argument("--target", required=True)
    context_parser.set_defaults(func=command_context)
    overview_parser = subparsers.add_parser("overview", help="生成动态特性树总览")
    overview_parser.set_defaults(func=command_overview)
    change_parser = subparsers.add_parser("change-report", help="生成当前 Git 增量影响报告")
    change_parser.set_defaults(func=command_change_report)
    verify_parser = subparsers.add_parser("verify", help="校验目录原生特性树")
    verify_parser.add_argument("--changes", action="store_true", help="同时阻断未归属 Git 变更")
    verify_parser.set_defaults(func=command_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
