#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_output_layout import output_layout_issues  # noqa: E402

FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "agent_ops",
        "deploy",
        "artifacts",
        "releases",
        "apps",
        "packages",
        "state",
        "contracts",
        "changes",
        "openspec",
        "app_log",
        "runtime",
        "build",
        "tmp",
        "tools",
        "githooks",
        "social_content_app",
        "node_modules",
        ".pytest_cache",
        ".mainline-release-artifact",
    }
)

FORBIDDEN_TOP_LEVEL_FILES = frozenset(
    {
        ".DS_Store",
        ".env",
        ".env.local",
        ".env.beta.local",
        "eval_report_content_feed.json",
        "eval_report_content_feed_multiobjective.json",
        "gate.log",
        "package-lock.json",
        "package.json",
        "runtime_scale10_ids.txt",
    }
)
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


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def root_layout_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    for name in sorted(FORBIDDEN_TOP_LEVEL):
        path = root / name
        if path.exists():
            issues.append(
                f"{_rel(path)}: forbidden top-level directory; move ownership to "
                f"domain roots or one of {ALLOWED_RUNTIME_ROOTS}"
            )
    for name in sorted(FORBIDDEN_TOP_LEVEL_FILES):
        path = root / name
        if path.exists():
            issues.append(
                f"{_rel(path)}: forbidden top-level file; move ownership to a "
                f"domain root or one of {ALLOWED_RUNTIME_ROOTS}"
            )
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
    if (root / ".qwq_state").exists():
        issues.append(".qwq_state: retired; use .qwq_output/env/<env>/local/<target>")
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
