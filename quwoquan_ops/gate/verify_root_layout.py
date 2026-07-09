#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

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
        ".mainline-release-artifact",
    }
)

ALLOWED_RUNTIME_ROOT = ".qwq_output"
ALLOWED_OUTPUT_TOP_LEVEL = frozenset({"local", "observability", "release", "runs"})
ALLOWED_RUN_ROOTS = frozenset({"alpha", "beta", "gamma", "prod", "data"})
ALLOWED_RELEASE_ROOTS = frozenset({"app", "service", "data", "legal-static"})
FORBIDDEN_NESTED_DIRS = frozenset(
    {
        "docs/personal-assistant",
        "quwoquan_ops/assistant",
        "quwoquan_ops/avatar",
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
            issues.append(f"{_rel(path)}: forbidden top-level directory; move ownership to domain roots or {ALLOWED_RUNTIME_ROOT}/")
    for source_root in ("quwoquan_app", "quwoquan_service", "quwoquan_data", "quwoquan_ops"):
        path = root / source_root / "artifacts"
        if path.exists():
            issues.append(f"{_rel(path)}: source domains must not contain runtime artifacts")
    for rel in sorted(FORBIDDEN_NESTED_DIRS):
        path = root / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired feature island directory; keep owned scripts under ci/, cli/smoke/ or gate/")
    output_root = root / ALLOWED_RUNTIME_ROOT
    if output_root.is_dir():
        for entry in sorted(p for p in output_root.iterdir() if p.is_dir()):
            if entry.name not in ALLOWED_OUTPUT_TOP_LEVEL:
                issues.append(
                    f"{_rel(entry)}: forbidden .qwq_output top-level directory; use local/, runs/, release/ or observability/"
                )
        runs_root = output_root / "runs"
        if runs_root.is_dir():
            for entry in sorted(p for p in runs_root.iterdir() if p.is_dir()):
                if entry.name not in ALLOWED_RUN_ROOTS:
                    issues.append(
                        f"{_rel(entry)}: run evidence must be grouped by env under .qwq_output/runs/<env>/<runId>"
                    )
        release_root = output_root / "release"
        if release_root.is_dir():
            for entry in sorted(p for p in release_root.iterdir() if p.is_dir()):
                if entry.name not in ALLOWED_RELEASE_ROOTS:
                    issues.append(
                        f"{_rel(entry)}: release output must be grouped by app/, service/, data/ or legal-static/"
                    )
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
