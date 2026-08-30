#!/usr/bin/env python3
"""Agent 资产垃圾回收报告（报告型 tool，不阻断）。

规则资产只增不删会腐化：死引用让评审静默少维度，harness 分叉制造第二真相源，
AGENTS.md 与特性树重复正文让两处各自漂移。本工具可重复生成三类候选清单，
供 distill / plan-next 轮次裁决回收，报告本身可删可重建：

1. 僵尸 reference：`.agents/skills/**/references/**` 下未被任何技能资产、
   registry、命令或 AGENTS.md 引用的 Markdown 文件。
2. harness 分叉：`.cursor/skills` / `.codex/skills` 中不指向 `.agents/skills/`
   真相源的实体 stub，以及指向不存在真相源的死指针。
3. 重复正文：各级 AGENTS.md 段落与 `specs/feature-tree/**` 正文逐字重复
   （normalize 后 >=120 字符），两处各自漂移的前兆。

用法：
    make asset-gc-report
    python3 -B quwoquan_ops/tools/report_asset_gc.py [--repo-root <root>]

报告落 `.qwq_output/env/repo/runs/asset-gc/report.md`；退出码恒 0。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRUNED_DIR_NAMES = {
    ".git",
    ".qwq_output",
    "node_modules",
    ".dart_tool",
    ".pub-cache",
    "__pycache__",
    ".pytest_cache",
    "build",
}

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#]+)")
_AGENTS_PATH_RE = re.compile(r"\.agents/[\w./\-]+\.md")
_MIN_DUPLICATE_CHARS = 120


def _iter_files(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    if not base.is_dir():
        return found
    for path in sorted(base.rglob("*")):
        if any(part in PRUNED_DIR_NAMES for part in path.parts):
            continue
        if path.is_file() and path.suffix in suffixes:
            found.append(path)
    return found


def _agents_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("AGENTS.md")):
        if any(part in PRUNED_DIR_NAMES for part in path.parts):
            continue
        found.append(path)
    return found


def collect_zombie_references(root: Path) -> list[str]:
    """references/** 下未被任何资产引用的 Markdown 文件（永不被派发/加载）。

    ROLE.md 豁免：它由派发机制按角色名结构性加载，孤儿判定归
    verify_agent_context_budget 的「roles/<name> 未被 registry 引用」检查。
    目录级链接（如 `[references/carriers/](references/carriers/)`）视为
    引用该目录下全部 Markdown。
    """
    skills_root = root / ".agents/skills"
    reference_files = [
        path
        for path in _iter_files(skills_root, (".md",))
        if "references" in path.parts
        and path.name not in ("SKILL.md", "ROLE.md")
    ]
    if not reference_files:
        return []

    scan_files = _iter_files(skills_root, (".md", ".yaml"))
    scan_files += _iter_files(root / ".cursor", (".md", ".mdc"))
    scan_files += _agents_files(root)

    referenced: set[Path] = set()
    referenced_dirs: set[Path] = set()
    for path in scan_files:
        text = path.read_text(encoding="utf-8")
        for target in _LINK_RE.findall(text):
            if target.startswith(("http://", "https://")):
                continue
            resolved = (path.parent / target.strip()).resolve()
            if resolved.is_dir():
                referenced_dirs.add(resolved)
            else:
                referenced.add(resolved)
        for literal in _AGENTS_PATH_RE.findall(text):
            referenced.add((root / literal).resolve())
        # registry.yaml 等以相对 references/ 的裸路径引用 checklist。
        for line in text.splitlines():
            if "roles/" in line:
                tokens = line.split("roles/", 1)[1].split()
                if not tokens:
                    continue
                fragment = tokens[0].strip("`'\"，。")
                referenced.add(
                    (skills_root / "review/references/roles" / fragment).resolve()
                )

    zombies = []
    for path in reference_files:
        resolved = path.resolve()
        if resolved in referenced:
            continue
        if any(parent in referenced_dirs for parent in resolved.parents):
            continue
        zombies.append(path.relative_to(root).as_posix())
    return zombies


def collect_harness_forks(root: Path) -> list[str]:
    """Cursor/Codex skill stub 中不指向真相源的实体与死指针。"""
    issues: list[str] = []
    for pattern in (".cursor/skills/*/SKILL.md", ".codex/skills/*/SKILL.md"):
        for stub in sorted(root.glob(pattern)):
            rel = stub.relative_to(root).as_posix()
            if stub.is_symlink():
                if not stub.resolve().is_file():
                    issues.append(f"{rel}: symlink 指向不存在的真相源（死指针）")
                continue
            text = stub.read_text(encoding="utf-8")
            if ".agents/skills/" not in text:
                issues.append(f"{rel}: 实体 stub 未指向 .agents/skills/ 真相源（分叉候选）")
                continue
            for target in re.findall(r"\.agents/skills/[\w\-]+/SKILL\.md", text):
                if not (root / target).is_file():
                    issues.append(f"{rel}: 指向不存在的真相源 {target}（死指针）")
    return issues


def _paragraphs(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    normalized = []
    for block in text.split("\n\n"):
        paragraph = re.sub(r"\s+", " ", block).strip()
        if len(paragraph) >= _MIN_DUPLICATE_CHARS and not paragraph.startswith("#"):
            normalized.append(paragraph)
    return normalized


def collect_duplicate_bodies(root: Path) -> list[str]:
    """AGENTS.md 段落与特性树正文逐字重复——两处各自漂移的前兆。"""
    tree_owner: dict[str, str] = {}
    for path in _iter_files(root / "specs/feature-tree", (".md",)):
        rel = path.relative_to(root).as_posix()
        for paragraph in _paragraphs(path.read_text(encoding="utf-8")):
            tree_owner.setdefault(paragraph, rel)

    duplicates: list[str] = []
    for path in _agents_files(root):
        rel = path.relative_to(root).as_posix()
        for paragraph in _paragraphs(path.read_text(encoding="utf-8")):
            owner = tree_owner.get(paragraph)
            if owner:
                duplicates.append(f"{rel} 与 {owner} 重复段落（{paragraph[:40]}…）")
    return duplicates


def build_report(root: Path) -> str:
    zombies = collect_zombie_references(root)
    forks = collect_harness_forks(root)
    duplicates = collect_duplicate_bodies(root)

    def _section(title: str, items: list[str]) -> str:
        body = "\n".join(f"- {item}" for item in items) if items else "- 无候选"
        return f"## {title}（{len(items)}）\n\n{body}\n"

    # 报告体不含时间戳：同一物理树两次生成必须字节幂等（生成时刻看文件 mtime）。
    return (
        "# 资产垃圾回收报告\n\n"
        "- 性质：候选清单，回收裁决走 distill / plan-next；本报告可删可重建。\n\n"
        + _section("僵尸 reference（未被任何资产引用）", zombies)
        + "\n"
        + _section("harness 分叉与死指针", forks)
        + "\n"
        + _section("AGENTS.md 与特性树重复正文", duplicates)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    report = build_report(args.repo_root)
    out_dir = args.repo_root / ".qwq_output/env/repo/runs/asset-gc"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"[asset-gc] 报告已生成：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
