"""Node 与目录原生树发现。"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import context


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
        return self.spec.relative_to(context.REPO_ROOT).as_posix()


def _visible_dirs(path: Path) -> list[Path]:
    return sorted(
        (item for item in path.iterdir() if item.is_dir() and not item.name.startswith(".")),
        key=lambda item: item.name,
    )


def discover_nodes() -> list[Node]:
    nodes = [Node(0, "app-root", context.TREE_ROOT)]
    for l1 in _visible_dirs(context.TREE_ROOT):
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
        # ``by_dir`` 由 CLI 以 ``directory.resolve()`` 建立；macOS 下
        # pytest/tmp 路径可经 ``/var -> /private/var`` 符号链接，父目录也必须
        # 以同一 canonical 形态查找，否则 manifest 会悄然只剩叶节点。
        current = by_dir.get(current.directory.parent.resolve())
    return list(reversed(chain))
