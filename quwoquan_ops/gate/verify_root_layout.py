#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_output_layout import output_layout_issues  # noqa: E402

#: 仓库根目录的封闭白名单。
#:
#: 这里必须是白名单而不是黑名单：黑名单只能拦下已经出现过的名字，任何新冒出来的
#: 垃圾目录都直接漏过门禁。`v/`、`v0/`、`v360p/`（被截断的 ffmpeg 参数误建）和
#: `.ruff_cache/` 就是这样长期存在而不被发现的。根目录默认封闭之后，新增任何一级
#: 条目都必须在这里显式登记，登记动作本身就是一次归属评审。
ALLOWED_TOP_LEVEL = frozenset(
    {
        # 版本控制与协作配置
        ".git",
        ".github",
        ".gitignore",
        ".dockerignore",
        ".cursor",
        ".cursorignore",
        # Agent harness 入口：技能与角色定义只有 .agents/ 一处真相源，
        # .claude/.codex/CLAUDE.md 是 Claude Code 与 Codex 的桥接投影
        # （目录名由各 harness 固定，不能收进域根）。
        ".agents",
        ".claude",
        ".codex",
        "CLAUDE.md",
        # 本地 IDE 配置：不入库，但开发机上必然存在
        ".vscode",
        # 唯一允许的运行输出根
        ".qwq_output",
        # 四个源域
        "quwoquan_app",
        "quwoquan_service",
        "quwoquan_data",
        "quwoquan_ops",
        # 规格与文档
        "specs",
        "docs",
        "AGENTS.md",
        "README.md",
        "LICENSE",
        # 构建入口与工作区
        "Makefile",
        "quwoquan-workspace.code-workspace",
        # 开发机本地归档：由 .gitignore 挡在版本控制之外，只在这台机器上存在。
        # 登记它是为了让根布局门禁保持封闭且不因它长期假红；它不承载任何仓库
        # 职责，被移走后这两行可以直接删除。
        "cursor（重置额度）",
        "cursor（重置额度）.zip",
    }
)

#: 曾经出现过并已明确退役的根条目。白名单已经能拦下它们，这里只用于给出比
#: 「未登记条目」更具体的处置提示，避免重复走一遍归属排查。
RETIRED_TOP_LEVEL = {
    "agent_ops": "moved into quwoquan_ops",
    "deploy": "moved into per-service deploy/base",
    "artifacts": "runtime output belongs under .qwq_output",
    "releases": "runtime output belongs under .qwq_output",
    "apps": "moved into quwoquan_app",
    "packages": "moved into per-domain package roots",
    "state": "use .qwq_output/env/<env>/local/<target>",
    "contracts": "moved into per-service contracts/",
    "changes": "history lives in git log",
    "openspec": "replaced by specs/feature-tree",
    "app_log": "runtime output belongs under .qwq_output",
    "runtime": "moved into quwoquan_app/lib/runtime",
    "build": "runtime output belongs under .qwq_output",
    "tmp": "runtime output belongs under .qwq_output",
    "tools": "moved into per-domain tool roots",
    "githooks": "moved into quwoquan_ops/hooks",
    "social_content_app": "renamed to quwoquan_app",
    "node_modules": "no root-level npm project",
    ".pytest_cache": "redirect to .qwq_output/env/repo/local/**",
    ".ruff_cache": "redirect to .qwq_output/env/repo/local/**",
    ".mypy_cache": "redirect to .qwq_output/env/repo/local/**",
    ".mainline-release-artifact": "runtime output belongs under .qwq_output",
    ".release-evidence-manifest": "runtime output belongs under .qwq_output",
    ".qwq_state": "use .qwq_output/env/<env>/local/<target>",
    ".DS_Store": "Finder metadata; delete and add to .gitignore",
    ".gitmodules": "submodules are not used",
    ".env": "secrets never live in the repository",
    ".env.local": "secrets never live in the repository",
    ".env.beta.local": "secrets never live in the repository",
    "eval_report_content_feed.json": "runtime output belongs under .qwq_output",
    "eval_report_content_feed_multiobjective.json": (
        "runtime output belongs under .qwq_output"
    ),
    "gate.log": "runtime output belongs under .qwq_output",
    "package-lock.json": "no root-level npm project",
    "package.json": "no root-level npm project",
    "runtime_scale10_ids.txt": "runtime output belongs under .qwq_output",
}
ALLOWED_RUNTIME_ROOTS = (".qwq_output",)
FORBIDDEN_NESTED_DIRS = frozenset(
    {
        "docs/personal-assistant",
        "quwoquan_app/.cursor",
        "quwoquan_app/assistant",
        "quwoquan_app/personal_assistant",
        "quwoquan_app/node_modules",
        "quwoquan_service/.cursor",
        "quwoquan_ops/assistant",
        "quwoquan_ops/avatar",
        "quwoquan_ops/lib",
    }
)
FORBIDDEN_FILES = frozenset(
    {
        "quwoquan_ops/cli/stackctl",
        "quwoquan_ops/cli/stackctl.sh",
        "quwoquan_ops/portal/vite.config.d.ts",
        "quwoquan_ops/portal/vite.config.js",
        "quwoquan_ops/portal/tsconfig.app.tsbuildinfo",
        "quwoquan_ops/portal/tsconfig.node.tsbuildinfo",
    }
)
FORBIDDEN_PORTAL_GENERATED_DIRS = frozenset(
    {
        "quwoquan_ops/portal/dist",
        "quwoquan_ops/portal/.test-dist",
    }
)
SOURCE_DOMAIN_ROOTS = (
    "quwoquan_app",
    "quwoquan_service",
    "quwoquan_data",
    "quwoquan_ops",
)
FORBIDDEN_SOURCE_CACHE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})
FORBIDDEN_SOURCE_CACHE_SUFFIXES = frozenset({".pyc", ".pyo"})


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def source_cache_issues(root: Path = ROOT) -> list[str]:
    """Reject interpreter and test caches that leak back into source domains."""
    issues: list[str] = []
    for domain_name in SOURCE_DOMAIN_ROOTS:
        domain_root = root / domain_name
        if not domain_root.is_dir():
            continue
        for current, dirnames, filenames in os.walk(domain_root):
            current_path = Path(current)
            retained: list[str] = []
            for name in dirnames:
                child = current_path / name
                if name in FORBIDDEN_SOURCE_CACHE_DIR_NAMES:
                    issues.append(
                        f"{_rel(child)}: source cache is forbidden; "
                        "write disposable caches under .qwq_output/env/repo/local/**"
                    )
                    continue
                retained.append(name)
            dirnames[:] = retained
            for name in filenames:
                if Path(name).suffix in FORBIDDEN_SOURCE_CACHE_SUFFIXES:
                    issues.append(
                        f"{_rel(current_path / name)}: Python bytecode is forbidden in source domains; "
                        "write disposable caches under .qwq_output/env/repo/local/**"
                    )
    return issues


def top_level_issues(root: Path = ROOT) -> list[str]:
    """拒绝任何未登记的一级条目。

    遍历真实目录而不是比对固定名单，是这道门能发现 `v/`、`v0/`、`.ruff_cache/`
    这类从未被预见过的条目的唯一原因。
    """
    issues: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        name = entry.name
        if name in ALLOWED_TOP_LEVEL:
            continue
        retired = RETIRED_TOP_LEVEL.get(name)
        if retired:
            issues.append(f"{name}: retired top-level entry; {retired}")
        else:
            issues.append(
                f"{name}: unregistered top-level entry; move ownership to a domain "
                f"root or one of {ALLOWED_RUNTIME_ROOTS}, or register it in "
                "ALLOWED_TOP_LEVEL with a reason"
            )
    return issues


def root_layout_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = list(top_level_issues(root))
    for source_root in ("quwoquan_app", "quwoquan_service", "quwoquan_data", "quwoquan_ops"):
        path = root / source_root / "artifacts"
        if path.exists():
            issues.append(f"{_rel(path)}: source domains must not contain runtime artifacts")
    for rel in sorted(FORBIDDEN_NESTED_DIRS):
        path = root / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired feature island directory; keep owned scripts under ci/, cli/smoke/ or gate/")
    for rel in sorted(FORBIDDEN_FILES):
        path = root / rel
        if path.exists():
            issues.append(f"{_rel(path)}: forbidden generated or shim file")
    for rel in sorted(FORBIDDEN_PORTAL_GENERATED_DIRS):
        path = root / rel
        if path.exists():
            issues.append(f"{_rel(path)}: Portal generated output must not live in source tree")
    issues.extend(source_cache_issues(root))
    issues.extend(output_layout_issues(root / ".qwq_output"))
    return issues


def main() -> int:
    issues = root_layout_issues()
    if issues:
        print("[verify_root_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_root_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
